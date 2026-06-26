# YouQu 自动化测试编排 — 全量一次性执行 Issue 提示词

## 标题与标签

- 标题：`[自动化测试] {应用名} 全量 YAML 用例一次性执行`
- labels：`automation`, `youqu`

---

## 目标

对 **{应用名}** 的全量 YAML 用例进行一次性回归执行：通过单一命令完成所有用例的分批执行与进度上报，无需拆分子 Issue。

## 环境信息

| 配置项 | 值 |
|--------|-----|
| 项目路径 | `{PROJECT_ROOT}/` |

## 职责

本 Issue 只做一件事：**一条命令，全量执行**。不拆分模块，不创建子 Issue。

---

## 执行参数

| 参数 | 值 |
|------|-----|
| APP_BINARY | {APP_BINARY} |
| APP_NAME | {APP_NAME} |
| AUTOTEST_PATH | {PROJECT_ROOT}/autotest/ |

> 执行 Agent 必须加载 `youqu-case-runner` 技能，知晓完整执行流程和约束。
> 框架自动完成分批执行、进度评论和结果上报，无需手动干预。
