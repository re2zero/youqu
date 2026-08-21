# Stage 1: Pipeline A — 静态源码扫描

## 用途
在子 agent 中运行 C++ 和/或 QML 静态扫描，产出覆盖率数据。

## 模式判定

| 条件 | 模式 | 跳过 |
|------|------|------|
| 项目有 `.cpp`/`.cc` 文件 | C++ 扫描 | — |
| 项目有 `.qml` 文件 | QML 扫描 | — |
| 只有 C++ | 只跑 C++ | QML 跳过 |
| 只有 QML | 只跑 QML | C++ 跳过 |
| 两者都有 | 全跑 | — |

## 前置：生成 compile_commands.json（CMake 项目）

libclang 模式需要 `compile_commands.json` 获取正确的 include 路径。CMake 项目可在**配置阶段**生成，不需要编译。

```bash
# 检查是否已有
if [ -f build/compile_commands.json ]; then
    echo "compile_commands.json 已存在"
else
    # 尝试生成（不编译）
    cmake -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON 2>&1 | tail -5
    if [ -f build/compile_commands.json ]; then
        echo "成功生成"
    else
        echo "无法生成，回退到 grep 模式"
    fi
fi
```

判断：
| 结果 | 后续 |
|------|------|
| 已有或生成成功 | `--mode auto`（libclang 优先，自动回退 grep） |
| 生成失败或非 CMake 项目 | `--mode grep`（零依赖） |

## 执行

```bash
# 1. 记录当前源码 commit hash（供报告比对）
COMMIT_HASH=$(git -C <project_root> rev-parse --short HEAD 2>/dev/null || echo "unknown")

# 2. C++ 扫描（自动模式：libclang 优先，失败回退 grep）
python3 assets/scripts/scan_cpp.py --mode auto --src <project_root> --build <build_dir> --output <output_dir>

# 3. 如果前置步骤确认无法生成 compile_commands.json，直接 grep 模式
python3 assets/scripts/scan_cpp.py --mode grep --src <project_root> --output <output_dir>

# 4. QML 扫描
python3 assets/scripts/scan_qml.py --src <project_root> --output <output_dir>
```

## 产出

| 文件 | 内容 |
|------|------|
| `pre_scan_gaps.yaml` | C++ gap 列表（缺 AT-SPI 名称的控件） |
| `pre_scan_ok.yaml` | C++ ok 列表（已有完整名称的控件） |
| `qml_gaps.yaml` | QML gap 列表 |
| `qml_ok.yaml` | QML ok 列表 |

## 覆盖率计算

```
覆盖率 = len(ok_widgets) / (len(ok_widgets) + len(gap_widgets)) * 100
```

## 输出格式

子 agent 将报告写入 `local://a_report.md`，必须包含 commit hash，格式：

```markdown
# Pipeline A Report

## 项目
- 路径: {project_path}
- Commit: {commit_hash}
- C++ 文件: {parsed_files}/{total_files}

## C++ 覆盖率
- 元素 A（可交互控件总数）: {total}
- 元素 B（已有名称）: {ok}
- 覆盖率: {coverage}%

## 按模块覆盖率
| 模块 | A | B | 覆盖率 | Gap 数 |
|------|---|---|--------|--------|
| ... | ... | ... | ... | ... |

## Gap 列表
| 变量 | 类型 | 文件 | 行号 | 缺 objectName | 缺 accessibleName |
|------|------|------|------|--------------|------------------|
| ... | ... | ... | ... | ... | ... |

## QML 覆盖率（如有）
...
```