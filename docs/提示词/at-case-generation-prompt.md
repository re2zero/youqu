# AT 用例生成

## 关联文件
- PROJECT_ROOT: 当前项目
- XLSX_PAH: $PROJECT_ROOT/tests/casefile/
  存放xlsx原始的测试用例表，如果不存在，则暂停并提示用户。
- TEST_FILES_DIR: $PROJECT_ROOT/tests/files/
  如果存在测试文件，需要在解析用例前了解有哪些测试文件，在对应的测试用例中使用。


## 步骤

1. 加载 at-case-generator 技能，阅读 references/ 下 pipeline-reference.md、suite-format.md、pitfalls.md
2. `youqu at parse --input <xlsx> --output tests/at/cases_raw.yaml`
3. tmux 启动应用 → `youqu at dump dtk --app <app> --src <project_root> --output tests/at/`（timeout 300s）
   - dump 自动执行去噪过滤，生成 `tests/at/at-tree.yaml`（已去噪）和 `tests/at/element_gaps.yaml`（缺 accessible_id 的元素清单）
4. `youqu at tree-info --at-tree tests/at/at-tree.yaml --output tests/at/at-tree-annotated.yaml --format yaml`
   - 输出结构化 YAML（含 comment/annotation_status/classification 字段），替代旧 compact_tree.txt
5. **AT 树注释阶段**（AI session）：逐个为 `classification: interactive` 的元素填写 `comment` 字段
   - 注释格式：`GUI位置: <界面位置描述> | 功能: <功能描述>`
   - 例如：`GUI位置: 工具栏第一个按钮 | 功能: 打开文件`
   - 填写后设 `annotation_status: draft`
   - 人工审核修正后设 `annotation_status: reviewed`
   - `element_gaps.yaml` 中列出的缺 accessible_id 的元素，需在应用源码中补充 `setAccessibleName()`
6. `youqu at validate --gate 1 --at-tree-annotated tests/at/at-tree-annotated.yaml --element-gaps tests/at/element_gaps.yaml`
   - 验证去噪和注释完整性，通过后才继续
7. **用例规范化阶段**（AI session）：理解 cases_raw.yaml，整理生成 suite-cases.yaml
   - 非 GUI 用例（终端命令、DBus 无 UI、HTTP 请求）分离到 `cases_non_gui.yaml`
   - 按 GUI 界面分组（不是 xlsx module），同一界面的用例放一个 suite，每 suite 最多 15 条
   - 每个 suite 必须有 4 字段注释：`测试界面`、`测试功能`、`前置条件`、`AT元素引用`
   - `AT元素引用` 列出本 suite 使用的 AT 树元素名称（用于前向追溯）
   - 拆分复合步骤（一个步骤含多个操作 → 拆成原子步骤），setup 动作移到 `前置条件`
8. `youqu at validate --gate 2 --suite-cases tests/at/suite-cases.yaml --at-tree-annotated tests/at/at-tree-annotated.yaml`
   - 验证规范化和 suite 注释完整性，通过后才继续
9. **AI 语义映射**：逐条分析 suite-cases.yaml 中的用例，将每个步骤映射到 at-tree-annotated.yaml 中的元素
   - 生成 `cases_mapped.yaml`，文件头部必须包含 `=== 格式范例 ===` 格式说明
   - 每个 suite 保留注释（测试界面、测试功能、AT元素引用）
   - active（操作可 AT-SPI 执行 + 有 assert）和 unsupported（写具体原因）
   - 右键菜单用 `dtk_context_menu`（不依赖 AT-SPI 树），文件路径用 `${TEST_FILES_DIR}/`中的具体文件
   - selector 的 `name` 必须能在 at-tree-annotated.yaml 中找到对应元素（交叉引用）
10. Assertion Coverage Gate：所有 active case 必须有 assert 步骤
11. `youqu at validate --gate 3 --cases-mapped tests/at/cases_mapped.yaml --at-tree-annotated tests/at/at-tree-annotated.yaml`
    - 验证映射格式、selector 交叉引用，通过后才继续
12. `youqu at generate --cases tests/at/cases_mapped.yaml --output tests/at/yaml --app <app> --at-tree tests/at/at-tree.yaml`
13. `youqu at validate --gate 4 --generate-output tests/at/yaml`
    - 验证生成产物
14. `find tests/at/yaml -type d -empty -delete`

## 可追溯性链

三层注释驱动设计，支持正向和反向追溯：
- Layer 1: `at-tree-annotated.yaml` 的 `comment` → 元素身份和功能
- Layer 2: `suite-cases.yaml` 的 `AT元素引用` → suite 使用哪些元素
- Layer 3: `cases_mapped.yaml` 的 `selector.name` → 最终映射到哪个元素

追溯链：`at-tree.comment ↔ suite-cases.AT元素引用 ↔ cases_mapped.selector.name`
