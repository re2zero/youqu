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
        found = [False]
        iteration = [0]
        start_name = [None]
        mk = self._get_mk()

        def on_focus_event(event):
            try:
                if event.type == "object:state-changed:focused" and event.detail1 == 1:
                    src = event.source
                    role = src.get_role_name() if src else ""
                    if "menu" in role.lower():
                        focused_name[0] = src.get_name() or ""
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
                    if not self._enumerate_and_navigate(target, exact):
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
        self.navigate_to(items, exact)
        self._get_mk().press_key("Return")
        time.sleep(0.3)

    def cancel(self):
        self._get_mk().press_key("Escape")
