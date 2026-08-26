# C++ Apply Fixes — 详细补全规则

Read this when doing Phase 3 (Apply Fixes, C++). SKILL.md Phase 3 gives the
default path; this file holds the patterns, gap-field semantics, insertion
rules, examples, and the parallel-apply strategy.

## Phase 3a — Automated Apply (`apply_fixes.py`)

**覆盖 80% 常见 C++ 模式**，剩余 20% 交给 Phase 3b LLM 处理。

自动处理以下模式：

| 模式 | 匹配条件 | 插入位置 |
|------|---------|---------|
| 成员指针初始化 | `m_var = new Type(this)` | `new` 表达式下一行 |
| `Ui_*` 模式 | `ui->setupUi(this)` | `setupUi()` 调用之后 |
| `addAction(...)` | `->addAction(...)` | `addAction` 调用之后 |
| `QShortcut` | `new QShortcut(...)` | `new` 表达式之后 |
| `QAction` 创建 | `new QAction(...)` | `new` 表达式之后 |

**用法：**

```bash
# Step 1: 生成规范名称映射
python3 scripts/naming.py tests/at/spi/pre_scan_gaps.yaml -o tests/at/spi/name_map.txt

# Step 2: 自动修复（--dry-run 预览）
python3 scripts/apply_fixes.py tests/at/spi/pre_scan_gaps.yaml \
  --name-map tests/at/spi/name_map.txt --src-dir . --dry-run

# Step 3: 确认无误后执行
python3 scripts/apply_fixes.py tests/at/spi/pre_scan_gaps.yaml \
  --name-map tests/at/spi/name_map.txt --src-dir .

# Step 4: 查看报告
cat apply_fixes_report.json | python3 -m json.tool
```

**输出：** `apply_fixes_report.json`

```json
{
  "fixed": 42,
  "unsupported": 5,
  "skipped": 0,
  "already_ok": 3,
  "total": 50,
  "results": [
    {"variable": "m_nameEdit", "file": "src/widget.cpp", "status": "fixed", "inserted_lines": 2, "inserted_after_line": 42}
  ]
}
```

**未支持（unsupported）的 gap 交给 Phase 3b LLM 处理：**

- 找不到插入点（`new` 表达式不在当前文件或 `.cpp` 中）
- 变量没有在 `name_map.txt` 中对应
- 特殊的构造函数模式（如 `QMenu *menu = new QMenu(tr("File"), this);` 中 `menu` 变量）

## Phase 3b — Apply Fixes (LLM)

处理 Phase 3a 自动化脚本无法覆盖的 gap（`apply_fixes_report.json` 中
`status: "unsupported"` 的项）。

**核心原则：增量补全，不修改已有代码。**

1. 打开 `source_file` 定位到 `line` 行（`pre_scan_gaps.yaml` 中的行号，指向 `.h` 文件中的 FIELD_DECL）
2. **注意：`line` 指向 `.h` 文件中的变量声明行，`new` 表达式通常在 `.cpp` 文件中**。到 `.cpp` 文件中搜索 `variable = new Type(...)` 或 `ui->variable = new Type(...)` 或 `ui->setupUi(this)` 作为插入点
3. 检查插入点附近**是否已有** `setObjectName()` / `setAccessibleName()` 调用
4. **只补缺的**，已有的**不动**
5. 不修改任何已有代码——不调缩进、不删空行、不改注释、不碰括号风格

### `pre_scan_gaps.yaml` 中每个 gap 的字段说明

| 字段 | 含义 | 判断依据 |
|------|------|---------|
| `has_object_name` | 是否已有 `setObjectName()` 调用 | `false` → 需要补 |
| `has_accessible_name` | 是否已有 `setAccessibleName()` 调用 | `false` → 需要补 |
| `is_action` | 是否为 `QAction` 类型 | `true` → 只能补 `setObjectName()` |
| `type` | 控件类型 | 含 `QAction`/`QShortcut`/`DAction` → 只能补 `setObjectName()` |
| `variable` | 变量名 | 用于 `name_map.txt` 查找规范名称 |
| `existing_object_name` | 已有的 `setObjectName("...")` 值 | 已有的话直接复用 |

### 插入位置规则

| 模式 | 插入位置 | 调用前缀 |
|------|---------|---------|
| 成员指针 `m_var = new Type(this)` | 在 `new` 表达式**之后** | `m_var->` |
| `Ui_*` 模式 `ui->setupUi(this)` | 在 `setupUi()` 调用**之后** | `ui->variable->` |
| `addAction(...)` | 在 `addAction` 调用**之后** | `variable->` |
| `new QShortcut(...)` | 在 `new QShortcut` 表达式**之后** | `variable->` |

**名称来源：** 必须使用 `name_map.txt` 中的规范名称，不能自行发明名称。

### 增量补全示例

```cpp
// 已有 objectName，缺 accessibleName → 只补后者
// BEFORE:
m_nameLineEdit = new DLineEdit(this);
m_nameLineEdit->setObjectName("NameLineEdit");

// AFTER: 只追加缺失的 setAccessibleName()
m_nameLineEdit = new DLineEdit(this);
m_nameLineEdit->setObjectName("NameLineEdit");          // ← 已有，不动
m_nameLineEdit->setAccessibleName("NameLineEdit");       // ← 新增
```

```cpp
// 已有 accessibleName，缺 objectName → 只补前者
// BEFORE:
ui->setupUi(this);
ui->nameEdit->setAccessibleName("NameEdit");

// AFTER:
ui->setupUi(this);
ui->nameEdit->setObjectName("NameEdit");                 // ← 新增
ui->nameEdit->setAccessibleName("NameEdit");             // ← 已有，不动
```

```cpp
// 两者都缺 → 在 new 表达式之后追加
// BEFORE:
m_nameLineEdit = new DLineEdit(this);

// AFTER:
m_nameLineEdit = new DLineEdit(this);
m_nameLineEdit->setObjectName("NameLineEdit");           // ← 新增
m_nameLineEdit->setAccessibleName("NameLineEdit");       // ← 新增
```

```cpp
// QAction: 只有 setObjectName()
// BEFORE:
m_newAction = new QAction(tr("New Window"), this);

// AFTER:
m_newAction = new QAction(tr("New Window"), this);
m_newAction->setObjectName("NewWindowAction");           // ← 新增
// 注意：不添加 setAccessibleName() — QAction 没有此方法
```

### 关键警告

> ⚠️ **Only QWidget subclasses have `setAccessibleName()`.** QAction, QShortcut,
> and other pure-QObject types compile with `setObjectName()` only — adding
> `setAccessibleName()` to them is a **compile error**. Verify the widget type in
> `pre_scan_gaps.yaml` (`type` field) before inserting. Common non-widget types:
> `QAction *`, `QShortcut *`, `QMenu *` (QMenu IS a widget, OK), `DMenu *` (OK).

> ⚠️ **不要贪多。** 只补 `pre_scan_gaps.yaml` 中列出的 gap。如果一个 gap 同时有
> `has_object_name=true` 和 `has_accessible_name=true`，说明它已被修复——跳过。

> ⚠️ **不能修改代码格式。** 不动缩进、空行、注释、括号风格、分号风格、命名风格。
> 只做纯增量插入。

> ⚠️ **Phase 3 全部完成后，必须重新扫描验证**（Phase 5）：
> 执行 `quality_gate.py`（命令见 SKILL.md Phase 5），验证 `quality_report.json`
> 覆盖率达标、无新增 gap。

## Parallel Apply Strategy (for large projects)

当 gaps 跨越 20 个以上文件时，使用自动脚本 + 并行子代理（路径统一用
`tests/at/spi/` 前缀，与 Pipeline 一致）：

1. **生成规范名称映射** — `python3 scripts/naming.py tests/at/spi/pre_scan_gaps.yaml -o tests/at/spi/name_map.txt`
2. **运行自动化修复** — `python3 scripts/apply_fixes.py tests/at/spi/pre_scan_gaps.yaml --name-map tests/at/spi/name_map.txt --src-dir .`
3. **重新扫描** — 运行 Phase 5 的 `quality_gate.py`（不是 `coverage_stats.py`；补全后验证统一走 quality_gate）获取剩余 unsupported gap
4. **按文件分配残余 gap** — 将无关联的文件组分配给不同的子代理（同一个文件内的 gap 不分给多个代理）
5. **子代理读取名称映射** — 每个代理必须读取 `tests/at/spi/name_map.txt` 并使用精确名称，通过 `# {src}:{line}` 键匹配
6. **全部完成后重新扫描** — 再次运行 Phase 5 的 `quality_gate.py` 检查命名冲突
7. **修复残余冲突** — 如果仍有重复名称，使用 `ClassName_Role` 格式（如 `CompactCpuMonitor_DetailButton`、`CpuMonitor_DetailButton`）
