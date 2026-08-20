# Stage 5: Verification + Delivery

## 模式判定

| 条件 | 模式 |
|------|------|
| 有 DISPLAY，有 at-tree | 完整验证（Gate 3/4/5 + 运行） |
| headless 或无 DISPLAY | 仅 Gate 3/5 校验 |
| 无 at-tree | 仅 Gate 3/5 校验 |

## 校验流程

### 1. Gate 3 — 映射格式校验

```bash
youqu at validate --gate 3 \
    --cases-mapped tests/at/cases_mapped.yaml \
    --at-tree-annotated tests/at/at-tree-annotated.yaml
```

检查项：
- 格式范例存在（文件头的 `=== 格式范例 ===` 注释块）
- selector 交叉引用 at-tree-annotated.yaml
- 无噪声 selector（不在 at-tree 中的元素名）

### 2. Gate 5 — 语义安全阀

```bash
youqu at validate --gate 5 \
    --cases-mapped tests/at/cases_mapped.yaml
```

检查项：
- C1: 无描述文本作为键盘输入
- C2: 无 keyboard_press / file_dialog 没有前置触发
- C3: 无 selector 同时缺少 name 和 accessible_id
- C4: 所有 step 必须有 action 映射
- C5: 右键菜单场景使用 `dtk_context_menu` 而非 `dtk_main_menu`

### 3. Gate 4 — 生成产物校验

```bash
youqu at validate --gate 4 \
    --generate-output tests/at/yaml/ \
    --at-tree tests/at/at-tree.yaml
```

检查项：
- Suite 文件使用 `suites:` 而非 `specs:`
- `session_start.command` 有效
- wait 值使用秒为单位（float: 0, 1.0, 3.0）
- 菜单操作使用 `dtk_main_menu`/`dtk_context_menu`

### 4. 运行时验证（有 DISPLAY 时）

```bash
# L2 烟雾测试：每模块一个代表用例
youqu at smoke --modules-dir tests/at/yaml/

# L3 单用例深度验证（指定 spec-id）
youqu at verify --suite tests/at/yaml/<module>/<module>.suite.yaml --spec-id <id>

# 或运行全部
youqu at run --testdir tests/at/yaml/
```

### 5. 覆盖率报告

```bash
python3 skills/at-case-generator/scripts/coverage_report.py \
    --testdir tests/at/yaml/ \
    [--expected-names tests/at/spi/expected_names.yaml] \
    [--cases-mapped tests/at/cases_mapped.yaml]
```


## 交付说明

产物清单（位于 `tests/at/` 下）：
- `cases_mapped.yaml` — 合并后的映射文件
- `yaml/` — 生成的 suite YAML 目录
- `at-tree-annotated.yaml` — 标注后的 AT 树
- `context-bundle.md` — 上下文包

`modules/`、`scan/`、`dump/` 是中间产物，不纳入交付物。

## 错误处理

| 失败点 | 行为 |
|--------|------|
| Gate 3 失败 | 停止，检查 cases_mapped.yaml 格式 |
| Gate 5 失败 | 停止，检查语义映射问题 |
| Gate 4 失败 | 停止，检查生成产物 |
| 运行时验证失败 | 降级：标记套件为 `status: unstable`，说明原因 |
| 覆盖率报告异常 | 不阻塞，继续 |
| 无 DISPLAY 无法运行 | 降级：跳过运行时验证，后续通知人工验证 |