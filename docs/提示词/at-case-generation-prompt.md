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
4. `youqu at tree-info --at-tree tests/at/at-tree.yaml --output tests/at/compact_tree.txt`
5. AI 语义映射：逐条分析 所有 用例，分 active（操作可 AT-SPI 执行 + 有 assert）和 unsupported（写具体原因）。右键菜单用 `dtk_context_menu`（不依赖 AT-SPI 树），文件路径用 `${TEST_FILES_DIR}/`中的具体文件
6. Assertion Coverage Gate：所有 active case 必须有 assert 步骤
7. `youqu at generate --cases tests/at/cases_mapped.yaml --output tests/at/yaml --app <app> --at-tree tests/at/at-tree.yaml`
8. `find tests/at/yaml -type d -empty -delete`
