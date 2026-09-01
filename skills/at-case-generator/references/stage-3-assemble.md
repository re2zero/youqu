# Stage 3: Assembly + Coverage Gate

> 本阶段由确定性脚本自动执行，主 agent 不参与。
> 产物目录固定 `tests/at/`（见 stage-1）。

## 执行

```bash
# 1. 组装
python3 <skill>/scripts/pipeline_assemble.py \
    --modules tests/at/modules/ \
    --output tests/at/ \
    --manifest tests/at/element-coverage-manifest.yaml \
    --generate-mapped tests/at/cases_mapped.yaml

# 2. 覆盖门禁（硬性 100%）
python3 <skill>/scripts/cover.py \
    --element-map tests/casefile/out/element-map.yaml \
    --testdir tests/at/yaml/ \
    --coverage-report tests/at/coverage-report.yaml \
    --threshold 100
# 如有已确认的人工豁免：追加 --unreachable tests/at/unreachable.yaml
```

## 组装（pipeline_assemble.py，与 at-suite-generator 同源）

1. 读取 `tests/at/modules/*.output.json`
2. 语义校验（Gate 5 语义安全阀）：step_type / action 白名单 / 断言 / 菜单 items
3. 校验通过后按模块组装
4. 生成 `tests/at/yaml/elements.yaml` + `tests/at/yaml/<module>/<module>.suite.yaml`
5. 从 `element-coverage-manifest.yaml` 补充元素到 elements.yaml（权威白名单）
6. 收集每个 suite 的 `annotation.AT元素引用` 声明覆盖元素

> **unsupported suite 的处置**：`status: "unsupported"` 的 suite 校验通过但不
> 产生可执行 case——不写 suite 文件、不记入 cases_mapped.yaml。这是设计行为：
> 规范技能已判定不可自动化的用例（manual: true）不再生成可运行测试。若某模块
> 全部用例都 unsupported，则该模块**不产生任何 yaml 产物**（elements.yaml 仍
> 由清单补充）。补漏时这些元素仍需通过其它模块的用例覆盖，或列入
> unreachable.yaml 豁免。

## 覆盖门禁（cover.py）

硬性目标：**element-map 中每个非 TBD、非菜单的持久 `id_name` 必须被至少一个
suite 的持久 `selector.name` 引用**。

```
coverage = covered / (denominator - unreachable) × 100%
```

- **denominator** = element-map `elements` 键（持久命名元素，运行时名）
- **covered** = 持久 `selector.name`（去重，剔文件名噪音）
- **unreachable** = `unreachable.yaml` 中的人工豁免（`unresolved` 即 id_name
  TBD/空 已在本阶段 1 被清单排除，不在此列）
- **瞬态菜单项不计入分母**（`transient_items` 单列，用 dtk_main_menu 文本操作）
- 退出码 0 = 达标，1 = 未达标

## 校验规则

| 检查项 | 失败行为 |
|--------|----------|
| step_type 不是 action/assert | 跳过该 suite |
| action 不在 VALID_ACTIONS | 跳过该 suite |
| assert 步骤 action 不以 assert_ 开头 | 跳过该 suite |
| 菜单动作缺少 items | 跳过该 suite |
| keyboard_type 缺少 text | 跳过该 suite |
| suite 没有断言步骤 | 跳过该 suite（unsupported 除外） |

## 产物

| 产物 | 生成者 | 谁读 |
|------|--------|------|
| `tests/at/yaml/elements.yaml` | pipeline_assemble.py | AT-SPI 执行器 |
| `tests/at/yaml/<module>/*.suite.yaml` | pipeline_assemble.py | AT-SPI 执行器 |
| `tests/at/cases_mapped.yaml` | pipeline_assemble.py | 校验/查看 |
| `tests/at/coverage-report.yaml` | cover.py | 主 agent（补漏输入） |
