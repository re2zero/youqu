# AT 管线未来优化方向

> 日期: 2026-07-24
> 状态: 构想阶段，未排期
> 来源: AT 管线代码审查 + 脑洞

## A. 管线编排层

### A1. 单命令管线
`youqu at pipeline --module xxx` 自动串联 record → merge → tree-info → map → generate，减少手动步骤。

### A2. Plan 状态机
pending → recording → recorded → merged → mapped → generated → verified
每步自动更新 plan.yaml，`youqu at status` 显示全局进度。

### A3. Dry-run 模式
模拟管线流程不执行测试，预检 selector 覆盖率和元素匹配率。

### A4. 进度看板
`youqu at status` 显示所有模块当前处于哪个阶段，类似看板视图。

## B. Scan 增强

### B1. 增量扫描
按文件 hash 缓存结果，只重扫变更文件。dde-file-manager 2133 文件全量扫太慢。

### B2. connect() 信号槽捕获
从源码理解 button → slot 关系，生成更智能的断言（如"点击按钮后某信号被触发"）。

### B3. QMenu 层次重建
从 addAction 调用链构建菜单树结构，不完全依赖运行时录制。

### B4. 并行 .ui/.ts 解析
当前在 C++ 扫描完成后串行执行 ui_parser 和 ts_translator，可以并行。

## C. Record 增强

### C1. 智能分段命名
用 plan module slug + 事件上下文自动命名 segment，而非 unnamed_NNN。

### C2. 录制质量评分
空元素点击比例高时警告用户，提示可能需要重建 extents cache 或检查 AT-SPI 可见性。

### C3. 空闲自动停止
N 秒无事件时提示用户是否结束录制，避免忘记停止导致大量空数据。

### C4. 操作回放
录制完成后可回放事件序列，让用户确认操作是否正确。

## D. Merge 增强

### D1. Diff 合并
只合并上次 merge 之后新增的 state snapshot，避免全量重复合并。

### D2. 瞬态上下文去重
同一右键菜单出现多次时合并为一个 transient context，标注出现次数。

### D3. 冲突检测
static 和 runtime 对同一元素有不同 name 时发出警告，帮助发现命名不一致。

## E. 质量门禁

### E1. 录制覆盖率检查
验证所有用例步骤都有对应的录制事件，找出"录了但没用上"或"用例有但没录到"的步骤。

### E2. Selector 置信度评分
用录制数据交叉验证 selector 选择——如果录制时点击的是元素 A，但 selector 选了元素 B，降低置信度。

### E3. element_gaps 增强
结合 scan gaps + runtime gaps 给出精准修复建议：哪些控件需要在源码中加 setAccessibleName。
