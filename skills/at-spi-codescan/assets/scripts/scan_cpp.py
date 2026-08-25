#!/usr/bin/env python3
"""AT-SPI C++ 源码扫描器 — 独立版，无 at-spi-completion 依赖。

扫描 C++ 源码中的可交互控件实例，统计：
- 期望控件（所有可交互控件）
- 已有名称（已有 setObjectName + setAccessibleName 的控件）
- 覆盖率 = |B| / |A|

输出：pre_scan_gaps.yaml（gap 列表）+ pre_scan_ok.yaml（已有名称的控件）
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("coverage_scan_cpp")

# ── 扫描引擎：纯源码文本（不依赖 libclang / 系统头文件 / compile_commands）─
# 设计目标：只要源码一致，任何环境（multica/CI/本地）扫描结果一致。
# 实现：.h 提取继承链 + 成员声明；.cpp 提取 setObjectName/setAccessibleName
#       调用；按继承链递归分类；跨文件按变量名合并。
import re as _re

_SOURCE_SCAN_VERSION = "2.0"  # 纯源码扫描器版本

# 分类常量单一来源：classify.py（C++ + QML 共用）
from classify import (
    INTERACTIVE_CLASSES as _KNOWN_INTERACTIVE,
    NON_WIDGET_INTERACTIVE as _KNOWN_NON_WIDGET,
    DECORATIVE_CLASSES as _KNOWN_DECORATIVE,
    LAYOUT_CLASSES as _KNOWN_LAYOUT,
)
# ── 纯源码继承链分类 ──────────────────────────────────────────
# 自定义控件类 → 沿 `class X : public Base` 递归 → 已知 Qt/DTK 基类。
# 不依赖 type_db.json / libclang / 系统头文件，源码一致则结果一致。
_CLASS_BASES: dict[str, str] = {}  # 自定义类名 -> 直接基类名


def _collect_class_bases(source_dir: str) -> None:
    """扫描 .h 收集 `class X : public Base` 继承映射（进程内一次）。"""
    global _CLASS_BASES
    if _CLASS_BASES:
        return
    root = Path(source_dir)
    if not root.is_dir():
        return
    _SKIP = {"tests", "test", "autotests", "autotest",
             "build", "Build", "builddir", "_build",
             "cmake-build", "CMakeFiles", ".cmake",
             "debian", ".git", "3rdparty", "thirdparty", "third_party"}
    pat = _re.compile(r"^\s*class\s+(\w+)\s*:\s*public\s+([\w:]+)")
    for h in root.rglob("*"):
        if h.suffix not in (".h", ".hpp", ".hxx"):
            continue
        if any(part in _SKIP for part in h.parts):
            continue
        try:
            content = h.read_text(errors="replace")
        except Exception:
            continue
        for line in content.splitlines():
            m = pat.match(line)
            if m:
                cls = m.group(1)
                base = m.group(2).split("::")[-1].split("<")[0].strip()
                _CLASS_BASES.setdefault(cls, base)


def _classify_type(type_name: str) -> str:
    """沿继承链分类：interactive / nonwidget / decorative / layout / unknown。"""
    base = type_name.replace(" *", "").replace("&", "").split("<")[0].strip()
    # 命名空间限定类型取末段类名（Dtk::Widget::DLineEdit -> DLineEdit）
    if "::" in base:
        base = base.split("::")[-1]
    seen: set[str] = set()
    current = base
    while current and current not in seen:
        seen.add(current)
        if current in _KNOWN_INTERACTIVE:
            return "interactive"
        if current in _KNOWN_NON_WIDGET:
            return "nonwidget"
        if current in _KNOWN_DECORATIVE:
            return "decorative"
        if current in _KNOWN_LAYOUT:
            return "layout"
        current = _CLASS_BASES.get(current)
    return "unknown"


def _is_interactive_type(type_name: str) -> bool:
    return _classify_type(type_name) == "interactive"


def _is_non_widget_interactive(type_name: str) -> bool:
    return _classify_type(type_name) == "nonwidget"


def _is_layout_type(type_name: str) -> bool:
    return _classify_type(type_name) == "layout"


def _is_decorative_type(type_name: str) -> bool:
    return _classify_type(type_name) == "decorative"


# ── 数据结构 ──────────────────────────────────────────────────
@dataclass
class WidgetInstance:
    variable: str = ""
    type_name: str = ""
    source_file: str = ""
    class_name: str = ""
    line: int = 0
    instantiation: str = ""
    has_object_name: bool = False
    has_accessible_name: bool = False
    existing_object_name: str = ""
    existing_accessible_name: str = ""
    display_text: str = ""
    role: str = ""
    context: str = ""
    is_action: bool = False
    action_owner: str = ""


@dataclass
class ScanResult:
    source_dir: str
    total_files: int = 0
    parsed_files: int = 0
    failed_files: int = 0
    widgets: list[WidgetInstance] = field(default_factory=list)
    ok_widgets: list[WidgetInstance] = field(default_factory=list)
    gap_widgets: list[WidgetInstance] = field(default_factory=list)


# ── 角色映射 ──────────────────────────────────────────────────
_TYPE_TO_ROLE: dict[str, str] = {
    "push button": "push button", "tool button": "push button",
    "check box": "check box", "radio button": "radio button",
    "combo box": "combo box", "spin box": "spin box",
    "slider": "slider", "scroll bar": "scroll bar",
    "progress bar": "progress bar",
    "line edit": "text", "text edit": "text",
    "label": "label", "menu": "menu",
    "menu item": "menu item", "menu bar": "menu bar",
    "tool bar": "tool bar", "status bar": "status bar",
    "tab": "page tab", "tab widget": "page tab list",
    "list view": "list", "tree view": "tree",
    "table view": "table",
    "scroll area": "scroll pane", "splitter": "split pane",
    "group box": "grouping", "frame": "frame",
    "stacked widget": "layered pane",
    "action": "push button", "shortcut": "accelerator label",
    "key sequence edit": "text",
}


def _map_role(type_name: str) -> str:
    base = type_name.replace(" *", "").replace("&", "").split("<")[0].strip()
    if base.startswith("D") and len(base) > 1 and base[1].isupper():
        base = base[1:]
    base_nospace = base.lower().replace(" ", "")
    for key, role in _TYPE_TO_ROLE.items():
        key_nospace = key.lower().replace(" ", "")
        if key_nospace in base_nospace:
            return role
    return ""


# ── 纯源码扫描核心 ────────────────────────────────────────────
_SKIP_DIRS = {"tests", "test", "autotests", "autotest",
              "build", "Build", "builddir", "_build",
              "cmake-build", "CMakeFiles", ".cmake",
              "debian", ".git", "3rdparty", "thirdparty", "third_party"}
_HEADER_EXTS = (".h", ".hpp", ".hxx")
_SOURCE_EXTS = (".cpp", ".cxx", ".cc")

# 成员声明：`Type *var;` / `Type *var = nullptr;` / `Type var;`
# 类型可含命名空间（Dtk::Widget::DLineEdit）与模板（QList<foo>）
_MEMBER_RE = _re.compile(
    r"(?m)^\s*(?:(?:mutable|static|const|inline|virtual|explicit)\s+)*([A-Za-z_][\w:]*)\s*\*\s*(\w+)\s*(?:=\s*[^;]*|\{[^}]*\})?\s*;"
)
# 命名调用：`var->setObjectName("x")` / `var->setAccessibleName("x")`
# 也匹配 `this->setObjectName`（成员自身）与 `.setObjectName`（值语义）
# 参数支持直接字符串、tr("...")、QObject::tr("...")、qsTr("...") 包裹
_NAME_CALL_RE = _re.compile(
    r"(?m)(?:[A-Za-z_]\w*\s*->\s*)*([A-Za-z_]\w*)\s*(?:->|\.)\s*(setObjectName|setAccessibleName)\s*\(\s*"
    r"(?:(?:QObject::)?(?:tr|qsTr)\s*\(\s*)?\"([^\"]*)\"\s*\)?\s*\)"
)


def _iter_files(root: Path, exts: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for p in root.rglob("*"):
        if p.suffix not in exts:
            continue
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if p.stem.startswith(("test_", "moc_", "mocs_", "ui_", "qrc_")):
            continue
        files.append(p)
    return sorted(files)


def _extract_members(content: str) -> list[tuple[str, str, int]]:
    """返回 [(type, var, line_no)]，仅取指针成员（控件实例）。"""
    out: list[tuple[str, str, int]] = []
    for m in _MEMBER_RE.finditer(content):
        typ, var = m.group(1), m.group(2)
        # 排除非控件类型（int/char/bool/void/枚举等）
        if typ in {"int", "char", "bool", "void", "float", "double",
                   "long", "short", "unsigned", "signed", "size_t",
                   "qint64", "quint64", "qint32", "quint32"}:
            continue
        line_no = content[:m.start()].count("\n") + 1
        out.append((typ, var, line_no))
    return out


def _extract_name_calls(content: str) -> list[tuple[str, str, str, int]]:
    """返回 [(var, call_type, name_val, line_no)] — 命名调用。"""
    out: list[tuple[str, str, str, int]] = []
    for m in _NAME_CALL_RE.finditer(content):
        var, call_type, name_val = m.group(1), m.group(2), m.group(3)
        line_no = content[:m.start()].count("\n") + 1
        out.append((var, call_type, name_val, line_no))
    return out


def _extract_local_widgets(content: str) -> list[tuple[str, str, int]]:
    """返回 [(type, var, line_no)] — 方法内局部控件变量 `Type *var = new Type(...)`。"""
    out: list[tuple[str, str, int]] = []
    # 匹配 `Type *var = new Type(...)`、`Type *var { nullptr };`（花括号初始化）、
    # `Type *var = 方法调用(...)`（仅已知控件类型，避免误报非控件）
    # 类型可含命名空间/模板
    pat = _re.compile(
        r"(?m)([A-Za-z_][\w:<>]*)\s*\*\s*(\w+)\s*(=\s*new\s+[A-Za-z_][\w:]*|\{[^}]*\}|=\s*[A-Za-z_]\w*\s*\()"
    )
    for m in pat.finditer(content):
        typ, var, init = m.group(1), m.group(2), m.group(3)
        # 排除非控件类型
        if typ in {"int", "char", "bool", "void", "float", "double",
                   "long", "short", "unsigned", "signed", "size_t",
                   "qint64", "quint64", "qint32", "quint32"}:
            continue
        # `= 方法调用(...)` 形式：仅保留已知控件类型（避免误报非控件返回值）
        if init.startswith("=") and "new" not in init and not _is_interactive_type(typ) and not _is_decorative_type(typ):
            continue
        line_no = content[:m.start()].count("\n") + 1
        out.append((typ, var, line_no))
    # `auto var = new Type(...)`：从 new 后的类型推断
    auto_pat = _re.compile(
        r"(?m)\bauto\s+(\w+)\s*=\s*new\s+([A-Za-z_][\w:<>]*)"
    )
    for m in auto_pat.finditer(content):
        var, typ = m.group(1), m.group(2)
        if not _is_interactive_type(typ) and not _is_decorative_type(typ):
            continue
        line_no = content[:m.start()].count("\n") + 1
        out.append((typ, var, line_no))
    return out

def _extract_method_scopes(content: str) -> list[tuple[str, int, int]]:
    """返回 [(class_name, start_line, end_line)] — 方法定义的花括号作用域。

    匹配 `[Ret] Class::method(...)` 行首定义（返回类型可含 * & < > ::），
    花括号平衡到方法体结束。全局函数（无 `::`）不算，避免把类外
    同名变量误归属。构造/析构（`Class::Class` / `Class::~Class`）同样匹配。
    """
    scopes: list[tuple[str, int, int]] = []
    method_re = _re.compile(
        r"(?m)^.*?\b([A-Za-z_]\w*)::([A-Za-z_~]\w*)\s*\("
    )
    for m in method_re.finditer(content):
        # 方法定义 vs 调用：`Class::method(...) {` 是定义，`Class::method(...);` 是调用
        # 在找到 '{' 前若遇到 ';' 则跳过（调用/声明，非定义）
        brace = content.find("{", m.end())
        semi = content.find(";", m.end())
        if brace == -1 or (semi != -1 and semi < brace):
            continue
        depth = 0
        i = brace
        while i < len(content):
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        start_line = content[:brace].count("\n") + 1
        end_line = content[:i].count("\n") + 1
        scopes.append((m.group(1), start_line, end_line))
    return scopes


def _class_for_line(scopes: list[tuple[str, int, int]], line_no: int) -> str:
    """返回 line_no 所在方法的类名；不在任何方法内返回空串。"""
    for cls, start, end in scopes:
        if start <= line_no <= end:
            return cls
    return ""

# ── 纯源码扫描编排（单进程，无 libclang / 系统头文件 / compile_commands）─
def _scan_pure_source(src_dir: str) -> ScanResult:
    """纯文本扫描：.h 成员声明 + .cpp 命名调用 + 继承链分类。

    仅依赖源码文本本身，任何环境结果一致：
    - 成员：正则提取 `Type *var;`（含自定义类型），type 记录原始形态；
    - 分类：`class X : public Base` 递归到已知 Qt/DTK 基类；
    - 命名：`var->setObjectName/setAccessibleName("...")` 跨 .cpp 收集；
    - 合并：成员（.h 声明处）与命名（.cpp 调用处）按变量名匹配。
    """
    root = Path(src_dir)
    if not root.is_dir():
        logger.error("Source directory not found: %s", src_dir)
        return ScanResult(source_dir=src_dir)

    _collect_class_bases(src_dir)

    header_files = _iter_files(root, _HEADER_EXTS)
    source_files = _iter_files(root, _SOURCE_EXTS)

    # Pass 1: 成员声明（.h）。同一变量名在不同类/文件中各自独立实例。
    # 类名 = 声明所在 class 块；用花括号平衡近似定位（声明在 private: 下）。
    widgets: dict[tuple[str, str], WidgetInstance] = {}  # (file, var) -> inst
    header_contents: dict[str, str] = {}

    for hf in header_files:
        rel = str(hf.relative_to(root))
        try:
            content = hf.read_text(errors="replace")
        except Exception:
            continue
        header_contents[rel] = content
        # 当前类名：跟踪最近的 `class X ... {` 块（含嵌套 namespace）
        class_stack: list[str] = []
        for m in _re.finditer(r"(?m)^\s*(class|struct)\s+(\w+)", content):
            class_stack.append(m.group(2))
        # 成员提取：按行定位所属类（声明行号前最近的类声明）
        class_lines: list[tuple[int, str]] = []
        for m in _re.finditer(r"(?m)^\s*(class|struct)\s+(\w+)", content):
            class_lines.append((content[:m.start()].count("\n") + 1, m.group(2)))
        for typ, var, line_no in _extract_members(content):
            # 找到该行之前最近的类声明
            cls = ""
            for cl_line, cl_name in class_lines:
                if cl_line <= line_no:
                    cls = cl_name
                else:
                    break
            if not cls:
                continue
            # 跳过：非控件类型（QList<X> 成员容器等由模板参数决定，跳过非指针）
            inst = WidgetInstance(
                variable=var, type_name=typ + " *",
                source_file=rel, class_name=cls,
                line=line_no, role=_map_role(typ + " *"),
            )
            widgets[(rel, cls, var)] = inst

    # Pass 1b: .cpp 内类成员（PIMPL 模式：类定义在 .cpp，成员在 class 块内）
    # 定位 `class X { ... };` 块，提取块内 `Type *var;` 成员，归属到类 X
    for cf in source_files:
        rel = str(cf.relative_to(root))
        try:
            content = cf.read_text(errors="replace")
        except Exception:
            continue
        for m in _re.finditer(r"(?m)^\s*(?:class|struct)\s+(\w+)[^{]*\{", content):
            cls = m.group(1)
            # 花括号平衡到类块结束
            depth = 1
            i = m.end()
            while i < len(content) and depth > 0:
                if content[i] == "{":
                    depth += 1
                elif content[i] == "}":
                    depth -= 1
                i += 1
            block = content[m.end():i]
            for typ, var, line_no in _extract_members(block):
                abs_line = content[:m.end()].count("\n") + line_no
                key = (rel, cls, var)
                if key in widgets:
                    continue
                inst = WidgetInstance(
                    variable=var, type_name=typ + " *",
                    source_file=rel, class_name=cls,
                    line=abs_line, role=_map_role(typ + " *"),
                )
                widgets[key] = inst
    name_calls: dict[tuple[str, str], set[tuple[str, str]]] = {}
    all_named_vars: set[str] = set()
    class_self_names: dict[str, dict[str, str]] = {}  # class -> {setObjectName/setAccessibleName: value}
    for cf in source_files:
        rel = str(cf.relative_to(root))
        try:
            content = cf.read_text(errors="replace")
        except Exception:
            continue
        scopes = _extract_method_scopes(content)
        # 局部控件变量：`Type *var = new Type(...)`，匹配其命名调用
        local_widgets: dict[str, tuple[str, str]] = {}  # var -> (type, class)
        for ltyp, lvar, lline in _extract_local_widgets(content):
            lcls = _class_for_line(scopes, lline)
            if lcls:
                local_widgets[lvar] = (ltyp, lcls)
        for var, call_type, name_val, line_no in _extract_name_calls(content):
            all_named_vars.add(var)
            # 找到调用所在方法的类；不在任何方法内（全局作用域）则不归属
            cls = _class_for_line(scopes, line_no)
            if not cls:
                continue
            # this->setXxx：给当前对象自身设名 → 类级命名
            if var == "this":
                class_self_names.setdefault(cls, {})[call_type] = name_val
                continue
            # 局部控件变量：匹配当前方法内的局部声明
            if var in local_widgets and local_widgets[var][1] == cls:
                ltyp, _ = local_widgets[var]
                key = ("<local>", cls, var)
                if key not in name_calls:
                    name_calls[key] = set()
                name_calls[key].add((call_type, name_val))
                continue
            # 只匹配当前类的同名成员
            for (hf, cls_name, var_name), inst in widgets.items():
                if var_name == var and cls_name == cls:
                    key = (hf, cls, var)
                    if key not in name_calls:
                        name_calls[key] = set()
                    name_calls[key].add((call_type, name_val))

    # Pass 3: 分类
    all_ok: list[WidgetInstance] = []
    all_gaps: list[WidgetInstance] = []
    for key, inst in widgets.items():
        if key in name_calls:
            for call_type, name_val in name_calls[key]:
                if call_type == "setObjectName":
                    inst.has_object_name = True
                    inst.existing_object_name = name_val
                elif call_type == "setAccessibleName":
                    inst.has_accessible_name = True
                    inst.existing_accessible_name = name_val
        is_interactive = _is_interactive_type(inst.type_name)
        is_decorative = _is_decorative_type(inst.type_name)
        is_layout = _is_layout_type(inst.type_name)
        inst.is_action = _is_non_widget_interactive(inst.type_name)
        if is_layout:
            continue
        # 装饰类型（Label/Frame/Widget 等）：未命名则过滤（非可交互 AT 节点）
        # 设了 accessible_name 则算 ok（显式命名暴露为 AT 节点）
        if is_decorative:
            if inst.has_accessible_name:
                all_ok.append(inst)
            continue
        if inst.has_object_name or inst.has_accessible_name:
            if is_interactive and not _is_non_widget_interactive(inst.type_name):
                # 有 accessible_name 即算已命名（AT-SPI 命名）；只有 object_name 无 accessible_name → gap
                if inst.has_accessible_name:
                    all_ok.append(inst)
                else:
                    all_gaps.append(inst)
            else:
                all_ok.append(inst)
        elif is_interactive:
            all_gaps.append(inst)

    # Pass 3b: 类自身命名（this->setObjectName/setAccessibleName）
    # 类实例自身是 AT-SPI 节点，设了 accessible name 即算已命名。
    for cls, names in class_self_names.items():
        has_obj = "setObjectName" in names
        has_acc = "setAccessibleName" in names
        # 类自身命名：有 accessibleName 即 ok（窗口/控件自身）
        if has_acc:
            inst = WidgetInstance(
                variable=cls, type_name=cls,
                source_file="", class_name=cls,
                line=0, has_object_name=has_obj,
                has_accessible_name=True,
                existing_object_name=names.get("setObjectName", ""),
                existing_accessible_name=names["setAccessibleName"],
                role="window",
            )
            all_ok.append(inst)

    # Pass 3c: 局部控件变量（方法内 `Type *var = new Type(...)`）
    # 局部控件也是 AT-SPI 节点，设了 accessible name 即算已命名。
    for (hf, cls, var), calls in name_calls.items():
        if hf != "<local>":
            continue
        has_obj = any(ct == "setObjectName" for ct, _ in calls)
        has_acc = any(ct == "setAccessibleName" for ct, _ in calls)
        if has_acc:
            acc_val = next(v for ct, v in calls if ct == "setAccessibleName")
            obj_val = next((v for ct, v in calls if ct == "setObjectName"), "")
            inst = WidgetInstance(
                variable=var, type_name="",
                source_file="", class_name=cls,
                line=0, has_object_name=has_obj,
                has_accessible_name=True,
                existing_object_name=obj_val,
                existing_accessible_name=acc_val,
                role="menu",
            )
            all_ok.append(inst)
    all_ok.sort(key=lambda w: (w.source_file, w.line, w.variable))
    all_gaps.sort(key=lambda w: (w.source_file, w.line, w.variable))

    result = ScanResult(
        source_dir=src_dir,
        total_files=len(header_files) + len(source_files),
        parsed_files=len(header_files) + len(source_files),
        widgets=all_ok + all_gaps, ok_widgets=all_ok, gap_widgets=all_gaps,
    )
    return result


# ── 主扫描入口 ──────────────────────────────────────────────────
def scan_source(src_dir: str, output_dir: str = ".",
                build_dir: str | None = None,
                compile_commands: str | None = None,
                mode: str | None = None) -> ScanResult:
    """Scan C++ source for AT-SPI name coverage — 纯源码文本，单一模式。

    不依赖 libclang / 系统头文件 / compile_commands.json：
    - .h 提取继承链 + 成员声明；
    - .cpp 提取 setObjectName/setAccessibleName 调用；
    - 继承链递归分类；跨文件按变量名合并。
    同一源码 → 同一结果（任何环境）。旧参数 build_dir/compile_commands/mode
    保留仅为兼容调用方，不再影响行为。
    """
    result = _scan_pure_source(src_dir)
    _write_outputs(result, output_dir)
    return result




def _widget_to_dict(w: WidgetInstance) -> dict[str, Any]:
    return {
        "variable": w.variable, "type": w.type_name,
        "source_file": w.source_file, "class_name": w.class_name,
        "line": w.line, "instantiation": w.instantiation,
        "has_object_name": w.has_object_name,
        "has_accessible_name": w.has_accessible_name,
        "existing_object_name": w.existing_object_name,
        "existing_accessible_name": w.existing_accessible_name,
        "display_text": w.display_text, "role": w.role,
        "context": w.context, "is_action": w.is_action,
        "action_owner": w.action_owner,
    }


def _write_outputs(result: ScanResult, output_dir: str) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # pre_scan_gaps.yaml
    gaps_data = {
        "version": "1.0",
        "source_dir": result.source_dir,
        "total_files": result.total_files,
        "parsed_files": result.parsed_files,
        "failed_files": result.failed_files,
        "gaps": [_widget_to_dict(w) for w in result.gap_widgets],
    }
    gaps_path = out / "pre_scan_gaps.yaml"
    import yaml
    with open(gaps_path, "w", encoding="utf-8") as f:
        yaml.dump(gaps_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    logger.info("Written %s (%d gaps)", gaps_path, len(result.gap_widgets))

    # pre_scan_ok.yaml
    ok_data = {
        "version": "1.0",
        "source_dir": result.source_dir,
        "widgets": [_widget_to_dict(w) for w in result.ok_widgets],
    }
    ok_path = out / "pre_scan_ok.yaml"
    with open(ok_path, "w", encoding="utf-8") as f:
        yaml.dump(ok_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    logger.info("Written %s (%d ok)", ok_path, len(result.ok_widgets))

    # coverage summary
    total = len(result.widgets)
    ok_count = len(result.ok_widgets)
    gap_count = len(result.gap_widgets)
    coverage = (ok_count / total * 100) if total else 0.0
    logger.info("Coverage: %d/%d = %.1f%% (%d gaps)", ok_count, total, coverage, gap_count)


# ── CLI ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="AT-SPI C++ coverage scanner — 纯源码文本，单一模式，"
                    "不依赖 libclang / 系统头文件 / compile_commands")
    parser.add_argument("--src", required=True, help="Source directory")
    parser.add_argument("--output", "-o", default=".", help="Output directory")
    args = parser.parse_args()

    result = scan_source(src_dir=args.src, output_dir=args.output)
    return 0 if result.parsed_files > 0 else 1


if __name__ == "__main__":
    sys.exit(main())