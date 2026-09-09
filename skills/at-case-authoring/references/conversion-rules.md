# 转换规则：xlsx → 标准 YAML（机械转换 + 切分 + element-map 初稿 + AI 初步生成）

存量 xlsx 的「用例」sheet 转成规范格式。**转换不改变用例语义**：
- 第 1 步机械转换（`convert_xlsx.py`）：保留**原始描述**（raw_* 字段）→ `cases_standard.yaml`
- 第 1b 步切分：按模块分组 + token 预算 → `slices/`（供 AI 逐片处理，2000+ 条用例必需）
- 第 1c 步 element-map 初稿：机械提取步骤中 UI 目标 → `element-map.yaml`（id_name/role=TBD）
- 第 2 步 AI 初步生成规范字段 + 精修 element-map
- 最终以**测试人员校对**为准

## 第 1 步：机械转换（convert_xlsx.py）

### 目标格式（cases_standard.yaml）

```yaml
# cases_standard.yaml — 原始描述 + 规范字段
app: deepin-reader
source: 文档查看器V25-用例.xlsx
converted_at: 2026-09-01
cases:
  - id: "1653625"                  # 保留原始用例编号，可追溯
    # ── 原始描述（逐字保留，测试人员校对对照用）──
    raw_title: 查找显示
    raw_precondition: ""           # 原始前置条件整段文本
    raw_steps: "1. 打开终端...\n2. 使用快捷键..."   # 原始步骤整段（含行号）
    raw_expected: "1. 在右上角显示...\n2. ..."
    # ── 机械预处理字段（AI 在此基础上规范化）──
    title: 查找显示
    module: 查找                   # 从「所属模块」取最后一段
    priority: "2"
    precondition: []               # 拆行去行号
    steps: ["打开终端，右键菜单选择搜索，检查搜索显示", ...]
    expected: ["在右上角显示：放大镜、搜索输入框...", ...]
    case_type: 功能测试
    manual: false
```

### 机械转换规则（不改变语义）

| 原始列 | 转换后字段 | 规则 |
|---|---|---|
| 用例编号 | id | 原样保留（字符串，含前导零） |
| 用例标题 | raw_title + title | raw 原样；title 也原样（AI 后续规范化） |
| 所属模块 | module | 取路径最后一段（`/.../查找(#116101)` → `查找`） |
| 用例级别/优先级 | priority | 原样 |
| 前置条件 | raw_precondition + precondition | raw 整段；precondition 按 `\n` 拆行去行号 |
| 步骤 | raw_steps + steps | raw 整段；steps 按 `\n` 拆行去行号 |
| 预期 | raw_expected + expected | raw 整段；expected 按 `\n` 拆行去行号 |
| 用例类型 | case_type | 原样（可选） |

### 1b. 切分（slices/）

按 `所属模块` 分组，组内按 token 预算切分（默认 16000，与 at-suite-generator 一致）。每片含 `app/module/seq/case_count/cases`。

```
slices/
├── 工作区_001.yaml    # 工作区模块第 1 片
├── 工作区_002.yaml    # 工作区模块第 2 片（超预算才拆）
├── 主菜单_001.yaml
└── ...
```

**为什么切分**：150 条用例生成约 4000 行 YAML；2000+ 条会达 5 万+ 行，超出 AI 上下文。切分后 AI 初步生成**逐片处理**，每片独立规范化，互不干扰。

> 单条用例 token 超预算仍独立成片（不丢弃、不拆分）。切分仅按模块自然边界 + 预算，不改用例语义。

- `ui_name`：从动作上下文（点击/选择/勾选后的引号文本）和控件词（X按钮/输入框/菜单）提取的**候选**中文名
- `id_name`/`object_name`/`role`：`TBD`（待开发填充）；**不生成 menu_type 字段**
  （已废弃，executor 运行时按 popup aid 段自动分类，见 spec §8）
- `object_name` 是 QObject::objectName（setObjectName 的值），Qt6 bridge 编码进
  accessible_id 点分路径后缀，运行时经 `get_accessible_id()` 读取，executor 后缀
  匹配定位，selector 用 `selector.accessible_id`（见 spec §8）
## 第 2 步：AI 初步生成（减少人工工作量）

基于 raw_* 对每条用例做**规范化草稿**：

1. **标题**：补 `【模块】` 前缀；`功能_场景` 化（如 `查找显示` → `【查找】查找显示`）；不可自动化用例标 `【人工】`（见 spec §7）
2. **前置条件**：动作句 → 移走或改状态；构造不了的标 `[手工]`
3. **步骤**：
   - 含断言词的行 → 移到预期列（断言词清单见 spec §3.1）
   - 一行多动作（分号/多个"点击"）→ 拆成多行
   - 无具体输入 → 补具体值或占位符 `test_input_001`
   - 位置无文本锚点 → 补 UI 文本或容器
4. **预期**：
   - "操作正常/无异常" → 换成可断言目标
   - 不可自动化目标（颜色/光标/硬件/性能）→ 标题标 `【人工】` **且** 整条标 `manual: true`（两者必须同时，见 spec §7）
5. **element-map 初稿**：收集所有步骤里的 UI 目标，生成 `element-map.yaml`
   - `id_name`/`object_name`/`role`（开发人员填）：标记为 `TBD`（待开发填充）；
     不生成 menu_type（已废弃）
### element-map 初稿示例
# element-map.yaml — 初稿（ui_name 已提取，id_name/object_name/role 待开发填；无 menu_type）
app: deepin-reader
version: "0.1"
updated: 2026-09-01
elements:
  - desc: TBD                  # 测试人员可补：功能说明
    ui_name: 查找输入框         # AI 从步骤提取
    id_name: TBD                # 开发人员填（AccessibleName）
    object_name: TBD            # 开发人员填（objectName，无则留空）
    role: TBD                   # 开发人员填
  - desc: TBD
    ui_name: 向上搜索
    id_name: TBD
    object_name: TBD
    role: TBD
## 校对规则（测试人员逐条，最终裁决）

1. 对照 `raw_*` 确认 AI 规范化**未改变用例语义**
2. 确认 element-map 的 `ui_name` 与步骤目标一致；把 `TBD` 的
   id_name/object_name/role 交给开发人员（不生成 menu_type，见 spec §8）

- 原始用例数 = 转换后数（`convert_xlsx.py` 会记录 case_count）
- 每条 id 保留 + raw_* 保留原始描述，可从标准 yaml 追溯/还原回 xlsx
