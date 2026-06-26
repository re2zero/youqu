# Baseline JSON Format

## 持久化格式

Baseline 结果保存为 JSON 文件，路径: `autotest/report/baseline/<timestamp>.json`

文件名格式: `<YYYYMMDD_HHMMSS>.json`

```json
{
  "version": 1,
  "timestamp": "2026-06-24T10:30:00+08:00",
  "mode": "incremental",
  "since": "HEAD",
  "branch": "master",
  "commit": "abc1234def5678",
  "change_analysis": {
    "modules": ["播放", "播放列表"],
    "change_type": "bug_fix",
    "affected_features": ["拖拽排序", "播放控制"],
    "needs_new_cases": false
  },
  "selected_tests": ["test_play_001", "test_play_005", "test_play_012"],
  "total": 15,
  "passed": 13,
  "failed": 1,
  "timeout": 1,
  "skipped": 0,
  "duration_seconds": 420,
  "failures": [
    {
      "test_id": "test_play_005",
      "error": "AssertionError: playlist index out of bounds after drag"
    }
  ],
  "new_cases_generated": []
}
```

## 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | int | 格式版本号，当前为 1 |
| `timestamp` | string | ISO 8601 格式，含时区 |
| `mode` | string | `incremental` (部分用例) 或 `full` (全量) |
| `since` | string | git 对比起点 (commit / tag / HEAD~N) |
| `branch` | string | 对比的分支名 |
| `commit` | string | 对比目标 commit SHA |
| `change_analysis` | object | Step 2 LLM 分析结果快照 |
| `selected_tests` | array | 实际执行的用例 ID 列表 |
| `total` | int | 总用例数 |
| `passed` | int | 通过数 |
| `failed` | int | 失败数 |
| `timeout` | int | 超时数 |
| `skipped` | int | 跳过数 |
| `duration_seconds` | int | 总执行耗时（秒） |
| `failures` | array | 失败用例详情列表 |
| `failures[].test_id` | string | 失败用例 ID |
| `failures[].error` | string | 错误信息摘要 |
| `new_cases_generated` | array | 本次新增生成的用例 ID 列表 |

## 对比逻辑

取最近的两个 baseline 文件做对比：

```
1. 列出 autotest/report/baseline/*.json，按文件名（时间戳）排序
2. 取最近两个文件: current.json 和 previous.json
3. 生成对比报告
```

### 对比报告格式

```
## 基线对比 (vs <previous_timestamp>)

| 指标 | 上次 | 本次 | 变化 |
|------|------|------|------|
| 总数 | 15 | 15 | — |
| 通过 | 12 | 13 | +1 ✅ |
| 失败 | 2 | 1 | -1 ✅ |
| 超时 | 1 | 1 | — |
| 通过率 | 80.0% | 86.7% | +6.7% ✅ |

### 回归 (上次通过 → 本次失败/超时)
- test_play_005: failed (上次: passed) — playlist index out of bounds after drag

### 修复 (上次失败/超时 → 本次通过)
- test_play_018: passed (上次: Element 'playlist_item' not found)

### 新失败 (上次不在执行列表中，首次失败)
无
```

### 对比规则

| 变化类型 | 判定条件 | 标记 |
|----------|----------|------|
| 回归 | 上次 passed，本次 failed 或 timeout | ❌ |
| 修复 | 上次 failed 或 timeout，本次 passed | ✅ |
| 新失败 | 上次不在 selected_tests 中，本次 failed | ⚠️ |
| 稳定通过 | 两次都 passed | —（不列出） |
| 持续失败 | 两次都 failed | —（不列出） |
