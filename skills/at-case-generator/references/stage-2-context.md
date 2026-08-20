# Stage 2: Context Bundle Generation (AI Session)

**由子 agent 执行**。主 agent 按以下模板启动一个子 agent 完成此阶段。

## 输入

- `at-tree-annotated.yaml` — 已标注的 AT 树
- `ui-map.md`（若存在）— 组件图、控件表、菜单索引
- `expected-at-spi-elements.md`（若存在）— 预期元素清单
- `docs/modules/*.md`（若存在）— 帮助手册章节
- `context-bundle.md`（若存在）— 覆盖它

## 输出

`tests/at/context-bundle.md` — 三张表：

1. **元素-功能对照表**: element name → Role → 功能描述 → 可见条件
2. **界面-元素映射**: 界面 → 包含的元素
3. **功能-操作-断言映射**: 功能 → 操作 → 断言目标

## 子 agent 任务模板

```
# 任务：生成 context-bundle.md

## 输入
- at-tree-annotated.yaml（已标注的 AT 树）
- ui-map.md（组件图，若有）
- expected-at-spi-elements.md（预期元素，若有）
- docs/modules/*.md（帮助手册，若有）

## 输出
生成 tests/at/context-bundle.md，包含三张表格：

### 1. 元素-功能对照表
| 元素名 | Role | 功能描述 | 可见条件 |

每行一个交互元素。从 at-tree-annotated.yaml 的 comment 字段提取功能描述。
覆盖行数 >= AT 树交互节点的 80%。

### 2. 界面-元素映射
| 界面 | 包含元素 |

按 GUI 界面分组（主窗口、工具栏、设置对话框、右键菜单等）。

### 3. 功能-操作-断言映射
| 功能 | 操作 | 断言目标 |

**这是最重要的表**。每行描述一个测试功能：
- 功能：具体的测试目标（如"开启深色模式"、"切换双页视图"）
- 操作：达到该功能需要的操作序列（如"菜单 → 设置 → 勾选深色模式"）
- 断言目标：操作后应该验证的 AT 元素（如"Form_Setting" 表示断言设置窗口出现）

## 格式要求
- 只写表格，不写散文段落
- 每行一个事实，无模糊描述
- 断言目标必须引用 at-tree-annotated.yaml 中存在的元素名
- 元素名必须与 at-tree-annotated.yaml 中的 name 字段完全一致

## 验证
- 元素-功能对照表行数 >= AT 树交互节点数的 80%
- 所有断言目标在 at-tree-annotated.yaml 中有对应元素
```

## 主 agent 执行

```python
# 读输入
at_tree = read("tests/at/at-tree-annotated.yaml")
ui_map = read("tests/at/ui-map.md") if exists("tests/at/ui-map.md") else ""
expected = read("tests/at/expected-at-spi-elements.md") if exists("tests/at/expected-at-spi-elements.md") else ""

# 创建子 agent 执行映射
result = agent(
    prompt="""context-bundle 生成任务模板（见上方）""",
    files={"at-tree-annotated.yaml": at_tree, "ui-map.md": ui_map, "expected-at-spi-elements.md": expected}
)
```

## 不支持的动作

| 动作 | 原因 |
|------|------|
| 跳过此阶段 | context-bundle.md 是 Stage 3 的断言质量保障 |
| 合并到 Stage 3 | 子 agent 上下文混杂，降低断言映射质量 |