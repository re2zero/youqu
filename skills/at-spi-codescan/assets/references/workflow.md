# Workflow: AT-SPI 覆盖率评估

流程：静态扫描 → （可选）代码图谱 → 报告。

## 1. 静态扫描（纯源码，环境无关）

按项目源码类型选择扫描器：

| 条件 | 运行 | 跳过 |
|------|------|------|
| 有 `.cpp`/`.cc` 文件 | `scan_cpp.py` | — |
| 有 `.qml` 文件 | `scan_qml.py` | — |
| 只有 C++ | 只跑 C++ | QML 跳过 |
| 只有 QML | 只跑 QML | C++ 跳过 |

```bash
# 记录源码 commit（供报告比对）
COMMIT_HASH=$(git -C <root> rev-parse --short HEAD 2>/dev/null || echo "unknown")

# C++ 扫描（纯源码文本，单一模式，无环境依赖）
python3 assets/scripts/scan_cpp.py --src <root> --output <dir>

# QML 扫描
python3 assets/scripts/scan_qml.py --src <root> --output <dir>
```

**环境一致性**：`scan_cpp.py` 只解析源码文本（`.h` 继承链 + 成员声明，`.cpp` 命名调用），
不依赖 libclang / 系统头文件 / compile_commands / MCP。只要源码 commit 一致，
任何环境（multica/CI/本地）结果一致。报告记录 `source commit` 即可比对。

## 2. 代码图谱（可选）— AI 直接调用 MCP 工具

MCP 服务是动态的（可能换成其它代码图谱），**不用脚本封装**。由 AI 直接调用
MCP 工具，先检查服务存在 + 项目已索引，满足才实施：

1. `list_tools` 探测实际可用工具（不假设固定工具名）。
2. `list_projects` 确认目标项目已索引（按路径/名称匹配）。
3. 图谱查询工具查 QWidget/DWidget 子类 + setAccessibleName/setObjectName 调用。
4. 产出 `b_data.json`（`available: true` + 类级覆盖率）。

未索引 / MCP 不可达 → 跳过，报告标注"不可用"，不影响静态扫描结果。

**注意**：代码图谱是类级、静态扫描是实例级，两者覆盖率**不可直接数值对比**；
静态扫描是唯一可信基线，代码图谱仅作类级缺口参考。若对比，先确认 MCP 索引
commit 与本地 HEAD 一致。

## 3. 报告

```bash
python3 assets/scripts/generate_report.py \
  --project-name <name> --project-path <root> \
  --pipeline-a-dir <dir> \
  [--pipeline-b-data <dir>/b_data.json] \
  --output <dir>
```

产出 `coverage-report.md`（汇总）+ `coverage-data.json`（结构化）。

## 产出文件

| 文件 | 生成者 | 内容 |
|------|--------|------|
| `pre_scan_ok.yaml` / `pre_scan_gaps.yaml` | scan_cpp.py | C++ ok/gap 列表 |
| `qml_ok.yaml` / `qml_gaps.yaml` | scan_qml.py | QML ok/gap 列表 |
| `b_data.json` | AI 调用 MCP 工具 | 代码图谱类级数据（可选） |
| `coverage-report.md` | generate_report.py | 汇总报告 |
| `coverage-data.json` | generate_report.py | 结构化数据 |