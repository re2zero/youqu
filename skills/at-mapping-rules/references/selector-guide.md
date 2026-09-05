# AT Selector 编写指南

本指南基于 deepin-editor（Qt6/DTK6）AT-SPI YAML 测试的实测经验，解决一个核心问题：**selector 怎么写才能在运行时真正定位到目标控件**。尤其针对"只有 ObjectName 的控件"（QAction/QShortcut 等无法 setAccessibleName 的控件）。

## 1. 定位键总览（按优先级）

| 优先级 | 键 | 含义 | 适用场景 |
|---|---|---|---|
| 1 | `accessible_id` | AT-SPI `get_accessible_id()` 的点分路径**后缀**（如 `UnixAction`、`PToolButton`） | 有 ObjectName 的控件；最稳定（objectName 是开发者意图名，改文本不变） |
| 2 | `name` | AT-SPI 可见名（`get_name()`，通常来自 accessibleName 或控件文本） | 可见文本/accessibleName 的控件 |
| 3 | `role` | AT-SPI 角色（push button / menu item / text...） | 仅 name 为空时的兜底 |
| 4 | `parent` + `parent_role` | 层级消歧 | 同名元素多个时 |
| 5 | `index` / `child_index` | 索引 | 容器内子元素导航 |

**关键规则**：`accessible_id` 匹配的是 **id 末尾后缀**（`node_id.endswith("." + target)`），不是完整路径、也不是节点的 name。写元素映射表里的裸 objectName（如 `UnixAction`）即可。

## 2. Qt6 ObjectName → accessible_id 机制

Qt6 的 at-spi bridge 通过 `QAccessibleBridgeUtils::accessibleId()` 递归生成每个节点的 id：

- **有 ObjectName 的控件** → id 末尾 = objectName（如 `EditorApplication.DropdownMenu.UnixAction`）
- **无 ObjectName 的控件** → id 末尾 = 类名（如 `...DDropdownMenu.PToolButton`、`...QMenu.QAction`）
- **完整 id 是父链点分路径**，但 selector 只写**末尾后缀**即可（引擎做后缀匹配）

实测（deepin-editor 全树 1082 节点）：
```
name='DropdownToolButton'  accessible_id='...BottomBar.DDropdownMenu.PToolButton'
                            ↑ name（DTK accessibleName）  ↑ id 后缀（类名 PToolButton）
```

**陷阱**：name 与 accessible_id 后缀**经常不同**！`DropdownToolButton` 是 name，`PToolButton` 才是 id 后缀。写 `accessible_id: DropdownToolButton` 找不到，必须写 `accessible_id: PToolButton`。

## 3. 只有 ObjectName 的控件（QAction 家族）怎么定位

QAction/DAction/QShortcut 是纯 QObject，**没有 setAccessibleName 方法**（那是 QWidget 的 API）。它们只有 objectName。

### 3.1 判断是否可定位

| 挂载位置 | AT-SPI 形态 | 可用定位方式 |
|---|---|---|
| QToolBar（tool button） | 有可见文本时 name=text；无文本时 name=objectName fallback | `name` 或 `accessible_id` |
| QMenu / DMenu（菜单项） | name=QAction text（瞬态，菜单关闭时 showing=False） | **菜单导航**（见 §5），不可裸 element_action |
| DDropdownMenu（DTK 下拉） | name=DDropdownMenu 的 accessibleName；菜单项 name=text，id 后缀=objectName | 先点触发按钮开菜单，再操作菜单项 |

### 3.2 例子（deepin-editor 实测）

```yaml
# QAction 只有 setObjectName("UnixAction")，addAction("Unix")
- action: element_action
  selector:
    accessible_id: UnixAction     # ← 后缀匹配，运行时 id 是 ...DropdownMenu.UnixAction
  do: click
```

## 4. element-map 的 id_name 语义

- element-map 的 `id_name` 若是源码 `setObjectName("X")` 抄来的**短名**，可直接用作 `selector.accessible_id`（后缀匹配兜底）
- **但注意**：静态扫描的 objectName 未必等于运行时 AT-SPI name。运行时 `name` 来自 text/accessibleName，`accessible_id` 来自 objectName/类名。二者不是一回事，映射时先确认目标控件在哪个键上

## 5. DTK 菜单操作（瞬态菜单项）

**菜单项是瞬态节点**：菜单关闭时 showing=False、extents 是假坐标 (0,y)。直接 `element_action` 点击会点屏幕左上角（误点其他应用）。

### 5.1 正确流程

```yaml
# 1. 先点父触发按钮（持久节点，showing=True）打开菜单
- action: element_action
  selector:
    accessible_id: PToolButton    # DDropdownMenu 的触发按钮
  do: click
  wait: 2.0
# 2. 键盘导航选择菜单项（DMenu 键盘路径可靠）
- action: keyboard_press
  key: Up                          # 方向需实测！见 §5.2
- action: keyboard_press
  key: Return
  wait: 1.0
```

### 5.2 键盘导航方向（实测陷阱）

**DDropdownMenu 菜单向上展开**（deepin-editor 底部栏，菜单弹出在按钮上方）：
- `Unix` = index 0（菜单**底部**），`Windows` = index 1（菜单**上方**）
- 从 Unix 切到 Windows 用 **Up**（不是 Down！）
- 常规菜单向下展开时才是 Down。**方向必须实测确认**，不能靠猜

### 5.3 AT-SPI 状态滞后

DMenu 弹出后菜单项 AT-SPI 状态可能滞后：
- `showing=False` 但菜单实际可见（引擎守卫已适配：坐标有效即放行）
- extents 可能仍是 (0,y) 假坐标 → **不能依赖坐标点击菜单项**
- 键盘导航（Up/Down + Return）是菜单项选择的最可靠路径

### 5.4 其他 DTK 菜单类型

| 菜单类型 | 推荐方式 |
|---|---|
| 主菜单（标题栏） | `dtk_main_menu` + `items`（键盘导航，menu_nav 处理） |
| 右键菜单 | `dtk_context_menu` + selector（定位右键位置）+ `items` |
| DDropdownMenu 下拉 | 点触发按钮（element_action PToolButton）→ 键盘导航菜单项 |

## 6. 幽灵节点与定位歧义

**实测问题**：同名 accessible_id 可能匹配到**隐藏幽灵节点**（残留窗口实例），extents=(0,0,0,0)：

```yaml
# PToolButton 可能返回 8 个：4 个 showing=False (0,0,0,0) + 4 个 showing=True
# 引擎已修复：accessible_id 分支优先返回 showing 节点
```

- 引擎 `_find_parent_element` 对 accessible_id 优先返回 **showing 节点**（过滤幽灵）
- 若仍有歧义（多个 showing 同名），用 `index` 或 `parent` 消歧

## 7. 断言写法

```yaml
- action: assert_element
  selector:
    accessible_id: UnixAction      # 存在性断言，同样支持后缀匹配
```

注意：菜单项断言也要在菜单弹出后进行（瞬态节点）。

## 8. 常见错误速查

| 错误写法 | 原因 | 正确写法 |
|---|---|---|
| `accessible_id: DropdownToolButton` | 那是 name，不是 id 后缀 | `accessible_id: PToolButton` 或 `name: DropdownToolButton` |
| 菜单项直接 `element_action click` | 瞬态节点，菜单关闭时假坐标 | 先点触发按钮 + 键盘导航 |
| `key: Down` 选上方菜单项 | DDropdownMenu 向上展开，方向相反 | 实测确认方向（Up） |
| 依赖菜单项 extents 坐标点击 | AT-SPI 滞后，假坐标 | 键盘导航或 AT-SPI action |
| selector 只写 `role` | 定位模糊 | 优先 accessible_id 或 name |

## 9. 验证清单

- [ ] 目标控件有 ObjectName → 用 `accessible_id`（后缀匹配）
- [ ] 目标控件无 ObjectName 但可见文本 → 用 `name`
- [ ] 菜单项 → 先开菜单（父触发按钮或 dtk_main_menu），再键盘导航
- [ ] 键盘导航方向已实测（向上展开用 Up，向下用 Down）
- [ ] 同名歧义 → 加 `parent` / `index`
- [ ] 运行后确认点击落在目标（无窗口切后台、无左上角误点）
