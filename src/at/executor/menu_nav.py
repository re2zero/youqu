import time
import logging

logger = logging.getLogger(__name__)


class AtMenuNotFoundError(Exception):
    pass


class AtMenuNavigator:
    MAX_LOOP = 30

    def __init__(self, app_name: str = "", desc: str = "", button_name: str = ""):
        self.app_name = app_name
        self.desc = desc
        self.button_name = button_name
        self._mk_inst = None
        self._app_node = None
        self._clicked = False

    def _get_mk(self):
        if self._mk_inst is None:
            from src.mouse_key import MouseKey
            self._mk_inst = MouseKey()
        return self._mk_inst

    def _app(self):
        if self._app_node is None:
            from src.dogtail_utils import DogtailUtils
            dog = DogtailUtils(self.app_name, self.desc) if self.app_name else DogtailUtils()
            self._app_node = dog.obj
        return self._app_node

    def open_main_menu(self):
        self._get_mk().press_key("Alt")
        time.sleep(0.1)
        # 主菜单按钮可被应用自定义 AccessibleName 覆盖默认的
        # "DTitlebarDWindowOptionButton"。优先尝试用例 selector.name
        # 指定的别名，再回退到默认名。
        candidates = []
        if self.button_name:
            candidates.append(self.button_name)
        if "DTitlebarDWindowOptionButton" not in candidates:
            candidates.append("DTitlebarDWindowOptionButton")
        for btn_name in candidates:
            try:
                from src.dogtail_utils import DogtailUtils
                dog = DogtailUtils(self.app_name, self.desc) if self.app_name else DogtailUtils()
                btns = dog.find_elements_by_attr(f"$//{btn_name}/")
                if btns:
                    btn = btns[-1]
                    if "Press" in getattr(btn, "actions", {}):
                        btn.doActionNamed("Press")
                    else:
                        btn.click()
                    time.sleep(0.15)
                    return
            except BaseException:
                continue
        # Fallback: QML TitleBar has unnamed WindowButton as menu button.
        try:
            import pyatspi
            desktop = pyatspi.Registry.getDesktop(0)
            for i in range(desktop.childCount):
                app = desktop[i]
                if self.app_name and self.app_name.lower() in (app.name or "").lower():
                    for j in range(app.childCount):
                        child = app[j]
                        if child.getRoleName() == "frame":
                            for k in range(child.childCount):
                                btn = child[k]
                                if btn.getRoleName() == "button" and not btn.name:
                                    action = btn.queryAction()
                                    if action.get_nActions() > 0:
                                        action.doAction(0)
                                        time.sleep(0.5)
                                        return
        except Exception:
            pass

    def open_context_menu(self, x: int, y: int):
        self._get_mk().right_click(x, y)
        time.sleep(0.1)

    def _collect_menu_items(self, node, max_depth=3):
        items = []
        if max_depth <= 0:
            return items
        try:
            children = node.children
        except Exception:
            return items
        for child in children:
            try:
                role = getattr(child, "roleName", "").lower()
            except Exception:
                continue
            if role in (
                "menu item", "menu", "check menu item",
                "radio menu item", "push button",
            ):
                name = getattr(child, "name", "") or ""
                if name:
                    items.append((name, child))
            items.extend(self._collect_menu_items(child, max_depth - 1))
        return items

    def _scan_focused(self, node, max_depth=3):
        items = self._collect_menu_items(node, max_depth)
        for _, child in items:
            try:
                states = set(
                    s.lower() for s in getattr(child, "states", [])
                    if hasattr(child, "states")
                )
            except Exception:
                continue
            if "focused" in states or "selected" in states:
                return getattr(child, "name", "") or ""
        return ""

    def _all_menu_items(self, from_root=False):
        items = self._collect_menu_items(self._app(), max_depth=3)
        if not items and from_root:
            try:
                from src.depends.dogtail.tree import root as atspi_root
                items = self._collect_menu_items(atspi_root, max_depth=4)
            except Exception:
                pass
        return items

    def _enumerate_and_navigate(self, target, exact=False):
        items = self._all_menu_items(from_root=True)
        if not items:
            return False
        for idx, (name, _) in enumerate(items):
            matched = name == target if exact else target.lower() in name.lower()
            if matched:
                for _ in range(idx):
                    self._get_mk().press_key("Down")
                    time.sleep(0.1)
                return True
        return False

    def _find_menu_item_node(self, target, exact=False):
        """遍历 AT-SPI 树，找到名称匹配且可见的菜单项节点。

        用于键盘导航失效时的兜底：DTK 右键菜单(DMenu::exec())是 transient
        popup，dogtail 静态树扫描不到，但 gi Atspi 遍历 desktop 树可见。
        返回 [(name, extents), ...]，extents 为屏幕坐标。
        target 为空时收集所有 role 含 menu 的节点(诊断用)。
        限制遍历深度/节点数，避免 AT-SPI 树异常时全树扫描卡住。
        """
        try:
            import gi
            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi
            root = Atspi.get_desktop(0)
            matches = []
            count = [0]

            def walk(node, depth=0):
                if depth > 6 or count[0] > 300:
                    return
                count[0] += 1
                try:
                    role = node.get_role_name() or ""
                    name = node.get_name() or ""
                    if "menu" in role.lower() and name:
                        if not target:
                            ext = node.get_extents(Atspi.CoordType.SCREEN)
                            matches.append((name, ext))
                        elif "menu item" in role.lower():
                            matched = (
                                name == target if exact else target.lower() in name.lower()
                            )
                            if matched:
                                ext = node.get_extents(Atspi.CoordType.SCREEN)
                                if ext.width > 0 and ext.height > 0:
                                    matches.append((name, ext))
                    for i in range(node.get_child_count()):
                        walk(node.get_child_at_index(i), depth + 1)
                except Exception:
                    pass

            walk(root)
            return matches
        except Exception:
            return []

    def _click_menu_item(self, target, exact=False, focused_node=None):
        """键盘导航失效时, 定位菜单项并鼠标点击。

        优先从当前 AT-SPI 焦点菜单项向上找菜单容器, 只遍历当前菜单
        (子节点少, 避免全树扫描在 AT-SPI 树异常时卡住); focused_node
        缺省时回退到受限的全树扫描(_find_menu_item_node)。
        """
        try:
            import gi
            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi

            node = focused_node
            if node is None:
                matches = self._find_menu_item_node(target, exact)
                if not matches:
                    return False
                name, ext = matches[0]
                cx, cy = ext.x + ext.width / 2, ext.y + ext.height / 2
                self._get_mk().click(cx, cy)
                time.sleep(0.3)
                return True

            # 向上找菜单容器(role 含 menu), 最多 5 层
            found_menu = False
            for _ in range(5):
                try:
                    node = node.get_parent()
                except Exception:
                    return False
                if not node:
                    return False
                role = node.get_role_name() or ""
                if "menu" in role.lower():
                    found_menu = True
                    break
            if not found_menu:
                return False

            # 遍历菜单容器内菜单项, 点击目标
            # 注意: get_child_at_index 可能返回 None(AT-SPI 树不稳定),
            # 跳过无效子节点继续遍历
            try:
                child_count = node.get_child_count()
                for i in range(child_count):
                    try:
                        child = node.get_child_at_index(i)
                        role = child.get_role_name() or ""
                        name = child.get_name() or ""
                    except Exception:
                        continue
                    if "menu item" in role.lower() and name:
                        matched = name == target if exact else target.lower() in name.lower()
                        if matched:
                            ext = child.get_extents(Atspi.CoordType.SCREEN)
                            if ext.width > 0 and ext.height > 0:
                                cx, cy = ext.x + ext.width / 2, ext.y + ext.height / 2
                                self._get_mk().click(cx, cy)
                                time.sleep(0.3)
                                return True
            except Exception:
                return False
            return False
        except Exception:
            return False

    def _read_focused_item(self, from_root=False):
        result = self._scan_focused(self._app(), max_depth=3)
        if not result and from_root:
            try:
                from src.depends.dogtail.tree import root as atspi_root
                result = self._scan_focused(atspi_root, max_depth=4)
            except Exception:
                pass
        return result

    def _navigate_by_focus(self, target, exact=False):
        start_text = self._read_focused_item()
        if not start_text:
            return False, ""

        for iteration in range(self.MAX_LOOP):
            current = self._scan_focused(self._app(), max_depth=3)
            if not current:
                current = self._read_focused_item(from_root=True)

            if not current and not start_text and iteration > 0:
                return False, "menu closed"

            matched = (
                (current == target)
                if exact
                else (target.lower() in current.lower() if current else False)
            )
            if matched:
                return True, current

            if iteration > 0 and current == start_text:
                return False, f"menu item '{target}' not found"

            self._get_mk().press_key("Down")
            time.sleep(0.1)

        return False, f"menu item '{target}' not found after {self.MAX_LOOP} iterations"

    def _navigate_by_events(self, target, exact=False):
        import gi
        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi, GLib

        try:
            Atspi.init()
        except Exception:
            pass

        focused_name = [""]
        focused_node = [None]
        found = [False]
        iteration = [0]
        start_name = [None]
        stall = [False]
        mk = self._get_mk()

        def on_focus_event(event):
            try:
                if event.type == "object:state-changed:focused" and event.detail1 == 1:
                    src = event.source
                    role = src.get_role_name() if src else ""
                    if "menu" in role.lower():
                        focused_name[0] = src.get_name() or ""
                        focused_node[0] = src
            except Exception:
                pass

        listener = Atspi.EventListener.new(on_focus_event)
        listener.register("object:state-changed:focused")

        loop = GLib.MainLoop()

        def step():
            iteration[0] += 1
            current = focused_name[0]

            if start_name[0] is None and current:
                start_name[0] = current

            matched = False
            if current:
                matched = (current == target) if exact else (target.lower() in current.lower())

            if matched:
                found[0] = True
                loop.quit()
                return False

            if iteration[0] >= self.MAX_LOOP:
                loop.quit()
                return False

            if iteration[0] > 2 and current and current == start_name[0]:
                # 键盘导航失效(焦点卡住, 常见于连续右键菜单: 菜单未 grab
                # 键盘焦点, Down 键不移动菜单项焦点)。只标记 stall 并退出
                # 主循环, 阻塞的 AT-SPI 定位 + 鼠标点击兜底在 loop.run()
                # 之后执行, 避免在 GLib 回调中阻塞导致死锁。
                stall[0] = True
                loop.quit()
                return False

            mk.press_key("Down")
            GLib.timeout_add(100, step)
            return False

        watchdog_fired = [False]

        def _watchdog():
            watchdog_fired[0] = True
            loop.quit()
            return False

        watchdog_ms = max(self.MAX_LOOP * 150, 5000)
        GLib.timeout_add(watchdog_ms, _watchdog)
        GLib.timeout_add(50, step)
        try:
            loop.run()
        finally:
            listener.deregister("object:state-changed:focused")

        if watchdog_fired[0]:
            return False, f"menu navigation timed out after {watchdog_ms}ms"
        if found[0]:
            return True, focused_name[0]
        if stall[0]:
            # 键盘导航失效, 主循环已退出, 在此做阻塞的 AT-SPI 定位 + 点击
            if self._click_menu_item(target, exact, focused_node[0]):
                self._clicked = True
                return True, target
        return False, f"menu item '{target}' not found"

    def navigate_to(self, items, exact=False):
        event_mode = False
        for i, target in enumerate(items):
            ok = False
            err = ""
            if event_mode:
                ok, err = self._navigate_by_events(target, exact)
            else:
                ok, err = self._navigate_by_focus(target, exact)
                if not ok:
                    # 焦点模式失败(如弹出菜单不在 dogtail 树中)时, 回退到
                    # AT-SPI focus 事件模式(按键导航触发菜单项聚焦事件)
                    ok, err = self._navigate_by_events(target, exact)
                if not ok:
                    # 键盘导航全部失败时: 最后一层菜单项用 AT-SPI 定位 +
                    # 鼠标点击兜底(覆盖连续右键菜单键盘导航失效的场景);
                    # 其余层保持枚举导航
                    if i == len(items) - 1 and self._click_menu_item(target, exact):
                        ok = True
                        self._clicked = True
                    elif self._enumerate_and_navigate(target, exact):
                        ok = True
                    else:
                        raise AtMenuNotFoundError(err or f"menu item '{target}' not found")

            if ok:
                event_mode = True
            elif not event_mode:
                raise AtMenuNotFoundError(err or f"menu item '{target}' not found")
            else:
                raise AtMenuNotFoundError(err or f"menu item '{target}' not found")

            if i < len(items) - 1:
                self._get_mk().press_key("Right")
                time.sleep(0.3)

    def select(self, items, exact=False):
        self._clicked = False
        self.navigate_to(items, exact)
        if not self._clicked:
            self._get_mk().press_key("Return")
        time.sleep(0.3)

    def cancel(self):
        self._get_mk().press_key("Escape")
