# youqu 2.18.5 框架修改说明（供 review）

## 修改范围

仅修改本机安装版 youqu-ai 2.18.5 中 **3 个文件**（其余文件与官方 wheel
`/home/zero/work/research/youqu/dist/youqu_ai-2.18.5-py3-none-any.whl` 完全一致）：

| 文件 | 位置 | 修改 | 目的 |
|------|------|------|------|
| `src/dogtail_utils.py` | `__evalx` 方法 | +15 行 | 支持 `name[@role='xxx']` 与 `[role='xxx']` 谓词解析 |
| `src/at/executor/menu_nav.py` | `AtMenuNavigator.navigate_to` | +4 行 | 焦点导航失败时回退到 AT-SPI 事件导航 |
| `src/at/executor/handlers.py` | `handle_dtk_context_menu` | +6 行 | 支持 `popup: click`（左键点击按钮弹出菜单） |

Patch 文件（基于官方 wheel 基线 `git diff`）：
- `/tmp/patches/youqu-2.18.5-dogtail_utils.patch`
- `/tmp/patches/youqu-2.18.5-menu_nav.patch`
- `/tmp/patches/youqu-2.18.5-handlers.patch`


## 修改 1：dogtail_utils.py — role 谓词支持

**背景**：youqu at 生成器 `_attrs_to_expr`（handlers.py:625）对含 `role` 的
selector 生成表达式 `$//name[@role='role']/`（见 `suite_tab_management` 中
`$//normal.pdf[@role='page tab']/`）。但执行端 `__evalx` 只按
`predicate.GenericPredicate(name)` 查找，`[@role='...']` 被当作名字字面量，
导致带 role 的断言**恒失败**（元素找不到）。

**修复**：`__evalx` 解析 name 中的 `[@role='xxx']` 后缀，拆出 name 与
roleName，构造 `GenericPredicate(name=..., roleName=...)`。同时支持纯
`[role='xxx']` 形式（name 为 None）。

**风险**：极小。`GenericPredicate(name=None, roleName=...)` 是 dogtail
标准用法；`name or None` 保证空名不会匹配空串。只影响含 `[@role=` 后缀的
表达式，既有 name-only 表达式行为不变。

## 修改 2：menu_nav.py — 事件导航 fallback

**背景**：`navigate_to` 原逻辑：

```python
ok, err = self._navigate_by_focus(target, exact)
if not ok and not err:
    ok, err = self._navigate_by_events(target, exact)
elif not ok:
    if not self._enumerate_and_navigate(...): raise ...
```

对 **DTK 弹出式菜单**（`DMenu::exec()` 的 BrowserMenu、缩放菜单等临时
窗口）`_navigate_by_focus` 失败且 **err 非空**，走 `elif` 分支直接
`_enumerate_and_navigate`——该分支同样依赖 dogtail 树（临时菜单不在树中），
故**永远失败**。这是"右键弹不出菜单导航"的根因。

**修复**：把 `if not ok and not err` / `elif not ok` 合并为
`if not ok`（两次 `_navigate_by_events` 调用合并为一次），保证
`_navigate_by_focus` 失败后**无条件**先回退到 `_navigate_by_events`
（AT-SPI focus 事件监听，对不在 dogtail 树中的临时菜单有效），仍失败才
走 `_enumerate_and_navigate`。

**风险**：低。`_navigate_by_events` 是原框架已实现的能力（用于
`event_mode` 分支），本次只是让失败路径也使用它。回退顺序变为
focus → events → enumerate，覆盖能力严格变大。

## 验证

- `youqu at smoke --modules-dir tests/at/yaml`：**14/14 通过**（修改前 0/14）
- `youqu at validate --gate all`：**Gate 1-5 全 PASS**
- 缩放套件从"5 次纯点击"（假过）修复为"点箭头弹菜单 + 5 项菜单导航"（真过）
- 去重后源 `suite-cases.yaml` 与 `cases_mapped.yaml` case id 完全对齐（14 个）


## 修改 3：handlers.py — dtk_context_menu 支持 popup: click

**背景**：`handle_dtk_context_menu` 固定用**右键**弹菜单（`open_context_menu`
= `mk.right_click`）。但部分 DTK 菜单（如 `ScaleWidget` 的缩放菜单）由
**箭头按钮左键点击**弹出（`onArrowBtnlicked` → `scaleMenu.exec()`），右键
不弹。因此缩放套件无法用 `dtk_context_menu` 导航菜单项（之前测试是
`mouse_click` 纯点击，不导航菜单项——假过）。

**修复**：`handle_dtk_context_menu` 支持 selector 中 `popup: click` 字段——
若存在则用左键 `mk.click` 替代右键，随后仍走既有 `nav.select(items)` 导航
（该导航已含 `_navigate_by_events` 回退，能处理临时 DMenu）。

```python
nav = AtMenuNavigator(context.get("app", ""))
if attrs.get("popup") == "click":
    mk = get_mk(context)
    mk.click(x, y)
    time.sleep(0.2)
else:
    nav.open_context_menu(x, y)
```

**风险**：低。`popup: click` 是显式 opt-in 字段，不传则行为与原来完全一致
（仍走 `open_context_menu` 右键）。该字段随 selector 透传（
`resolve_step_attrs` 并入 attrs），生成器保留 selector 原样。

**注意**：`popup` 必须写在 **selector 内**而非步骤顶层——生成器
`_step_to_action` 对 `dtk_context_menu` 只保留 `items/ref/selector`，
顶层 `popup` 会被丢弃。

## 建议

- 修改 1（role 谓词）与 handlers.py 的 `_attrs_to_expr` 是配套的：
  **生成器产出 role 表达式，执行端必须能解析**。建议上游统一确认该语法。
- 修改 2 建议作为通用菜单导航增强合入（对 DMenu::exec 临时菜单普遍有效）。
