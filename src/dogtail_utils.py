#!/usr/bin/env python3
# _*_ coding:utf-8 _*_

# SPDX-FileCopyrightText: 2023 UnionTech Software Technology Co., Ltd.

# SPDX-License-Identifier: GPL-2.0-only
# pylint: disable=C0114,C0103
import re
from typing import Union

from setting.globalconfig import GlobalConfig
from src import logger
from src.cmdctl import CmdCtl
from src.custom_exception import ElementNotFound
from src.custom_exception import ApplicationStartError

try:
    from src.depends.dogtail.tree import SearchError
    from src.depends.dogtail.tree import root
    from src.depends.dogtail.tree import predicate
    from src.depends.dogtail.tree import config
    from src.depends.dogtail.tree import Node

    config.childrenLimit = 1000
    # config.logDebugToStdOut = False
    config.logDebugToFile = False
    config.searchCutoffCount = 2
    config.actionDelay = 0.2
    GlobalConfig.NO_DOGTAIL = False
except ModuleNotFoundError:
    GlobalConfig.NO_DOGTAIL = True
    Node = None

from src.mouse_key import MouseKey


def _node_matches_accessible_id(node, accessible_id: str) -> bool:
    """Check whether an AT-SPI node's accessible-id matches (exact or suffix).

    Qt bridge encodes objectName into a dotted path via
    QAccessibleBridgeUtils::accessibleId(), e.g.
    "EditorApplication.Window...UnixAction". The requested id may be the
    full path or the objectName suffix.
    """
    try:
        node_id = node.get_accessible_id()
    except Exception:
        return False
    if not node_id:
        return False
    return node_id == accessible_id or node_id.endswith("." + accessible_id)


def _active_frame_extents(app_node):
    """当前活动窗口的屏幕边界 (x, y, w, h)，无则 None。

    多窗口时 application 节点下有多个 frame，find 返回的坐标可能来自非
    活动窗口（新窗口在别的位置，操作却用旧窗口坐标）。这里用 AT-SPI
    自身的活动状态判定：找出 role=frame 且 state 含 ACTIVE 的顶层窗口，
    返回其 extents（与 get_extents(SCREEN) 同一坐标系，用于按 frame 归属
    过滤，而非坐标点判定）。

    注意: 部分环境 AT-SPI 不暴露 ACTIVE state（所有 frame 均非 ACTIVE，
    如模态对话框场景），此时返回 None，调用方据此回退为不过滤，避免
    误删子窗口/主窗口元素。
    """
    try:
        from gi.repository import Atspi
    except BaseException:
        return None
    try:
        count = app_node.get_child_count()
        for i in range(count):
            frame = app_node.get_child_at_index(i)
            if (frame.get_role_name() or "") != "frame":
                continue
            if not frame.get_state_set().contains(Atspi.StateType.ACTIVE):
                continue
            ext = frame.get_extents(Atspi.CoordType.SCREEN)
            if ext.width > 0 and ext.height > 0:
                return (ext.x, ext.y, ext.width, ext.height)
    except BaseException:
        return None
    return None


def _gi_find_descendants(root, name=None, role=None, recursive=True, accessible_id=None):
    """gi AT-SPI 递归查找（替代失效的 dogtail findChildren）。

    dogtail 的 findChildren 底层走 pyatspi.utils.findAllDescendants，其用
    ``for child in acc`` 迭代；但 gi Atspi.Accessible 普通子节点没有
    ``__iter__``（只有 Root/Application 有），递归到第一层子节点即失败，
    返回空。这里用 gi 的 get_child_count/get_child_at_index 递归。

    多窗口时只保留活动窗口（AT-SPI ACTIVE frame）内的节点，避免新窗口在
    别的位置却操作旧窗口坐标。按 frame 归属过滤（非坐标点判定），滚动
    区域外（y 超出可视区）的控件仍属于当前窗口，不会被误删；活动 frame
    判定失败时不过滤（宽松回退），避免设置对话框等子窗口元素被误删。
    """
    results = []
    active_ext = _active_frame_extents(root)

    def _match(node):
        try:
            if name is not None and (node.get_name() or "") != name:
                return False
            if role is not None and (node.get_role_name() or "") != role:
                return False
            if accessible_id is not None and not _node_matches_accessible_id(
                node, accessible_id
            ):
                return False
            # 过滤幽灵节点: 进程被 SIGKILL 后 AT-SPI 残留 app 的节点
            # extents 为 (0,0,0,0) (窗口已销毁), 坐标点击必然失败且可能
            # 点到屏幕左上角把目标窗口切到后台。extents 全 0 的节点
            # 无法交互, 直接丢弃; 滚动区域外元素 extents 有效不受影响。
            ext = node.get_extents(
                __import__("gi").repository.Atspi.CoordType.SCREEN
            )
            if ext.width <= 0 or ext.height <= 0:
                return False
            return True
        except BaseException:
            return False

    def _walk(node, depth=0, in_active=None):
        # in_active: None=未知(不过滤), True=活动 frame 内, False=非活动 frame 内
        if depth > 64:
            return
        try:
            if _match(node):
                # 仅丢弃明确属于非活动 frame 的节点。找不到活动 frame
                # (active_ext None) / 节点属于 dialog 等非 frame 顶层 /
                # 无法归属 → 保留, 避免设置对话框等子窗口元素被误删。
                if in_active is False:
                    return
                results.append(node)
                return
        except BaseException:
            pass
        if not recursive:
            return
        try:
            count = node.get_child_count()
        except BaseException:
            return
        for i in range(count):
            try:
                child = node.get_child_at_index(i)
            except BaseException:
                continue
            child_active = in_active
            if depth == 0:
                # 顶层 frame 归属判定: 只有 role=frame 的顶层参与过滤,
                # dialog 等其它顶层窗口不参与(保留)。
                try:
                    if (child.get_role_name() or "") == "frame":
                        if active_ext is None:
                            child_active = None
                        else:
                            ext = child.get_extents(
                                __import__("gi").repository.Atspi.CoordType.SCREEN
                            )
                            child_active = (
                                ext.x, ext.y, ext.width, ext.height
                            ) == active_ext
                except BaseException:
                    child_active = None
            _walk(child, depth + 1, child_active)

    try:
        _walk(root)
    except BaseException:
        return []
    return results
class DogtailUtils(MouseKey):
    """
    通过属性进行元素定位和操作。
    """

    # pylint: disable=too-many-arguments,too-many-locals,too-many-public-methods
    __author__ = "Mikigo <huangmingqiang@uniontech.com>, Litao <litaoa@uniontech.com>"

    def __init__(self, name=None, description=None, number=-1, check_start=True, key: dict = None):
        if GlobalConfig.NO_DOGTAIL:
            raise EnvironmentError("Dogtail 及其相关依赖存在问题,调用相关方法失败~")
        config.logDebugToStdOut = False
        self.name = name
        self.description = description
        try:
            if name:
                self.obj = root.application(self.name, self.description)
            else:
                self.obj = root
            if number > 0:
                self.obj = self.obj.findChildren(predicate.GenericPredicate(**key))[number]

        except SearchError:
            if check_start:
                search_app = CmdCtl.run_cmd(f"ps -ef | grep {self.name}")
                logger.error(search_app)
                raise ApplicationStartError(self.name) from SearchError

    def app_element(self, *args, **kwargs) -> Node:
        """
         获取app元素的对象
        :return: 元素的对象
        """
        try:
            element = self.obj.child(*args, **kwargs, retry=False)
            logger.debug(f"{args, kwargs} 获取元素对象 <{element}>")
            return element
        except SearchError:
            raise ElementNotFound(*args, **kwargs) from SearchError

    def get_element_children_text(self, element):
        element = self.app_element(element)
        all_children = element.children
        text = []
        for i in range(len(all_children)):
            text.append(all_children[i].name)
        return text

    def left_upper_corner_position(self, element) -> tuple:
        """
         获取元素左上角的坐标
        :param element: 元素名称
        :return: 元素左上角坐标
        """
        position = self.app_element(element).position
        logger.debug(f"获取元素 {element}元素左上角坐标 {position}")
        return position

    def element_size(self, *args, **kwargs) -> tuple:
        """
         获取元素的大小
        :return: 元素大小
        """
        size = self.app_element(*args, **kwargs).size
        logger.debug(f"元素{args, kwargs} 的大小 {size}")
        return size

    def right_upper_corner_position(self, element) -> tuple:
        """
         获取元素右上角的坐标
        :param element: 元素名称
        :return: 元素右上角坐标
        """
        _x = self.left_upper_corner_position(element)[0] + self.element_size(element)[0]
        _y = self.left_upper_corner_position(element)[1]
        logger.debug(f"获取元素 {element}, 右上角坐标 ({_x, _y})")
        return int(_x), int(_y)

    def element_center(self, element) -> tuple:
        """
         获取元素的中心位置
        :param element:
        :return: 元素中心坐标
        """
        _x, _y, _w, _h = self.app_element(element).extents
        _x = _x + _w / 2
        _y = _y + _h / 2
        logger.debug(f"获取元素中心坐标 ({_x, _y})")
        return _x, _y

    def element_click(self, element, button=1):
        """
         元素点击
        :param element: 应用的元素
        :param button: 1>left,2>middle,3>right
        :return: None
        """
        logger.debug(
            f"""{"左键" if button == 1 else f"{'右键' if button == 3 else '鼠标中健'}"} 点击元素 {element}"""
        )
        mouse_click = (
            self.click if button == 1 else self.right_click if button == 3 else self.middle_click
        )
        mouse_click(*self.element_center(element))

    def element_double_click(self, element):
        """
         元素双击
        :return: None
        """
        logger.debug(f"双击元素 {element}")
        self.double_click(*self.element_center(element))

    def element_point(self, element):
        """
         鼠标移动到元素上（位置是在元素的中心）
        :param element: 应用的元素
        :return: None
        """
        logger.debug(f"鼠标移至元素 {element} 中心")
        self.move_to(*self.element_center(element))
    @staticmethod
    def __evalx(expr, element, recursive):
        """evalx"""
        node = re.match(".*?[^\\\\]/", expr)
        if node:
            name = node.group().replace("\\/", "/")[:-1]
        else:
            return None, []
        # 解析 name[@role='xxx'] 后缀（youqu at 断言表达式格式）
        role_name = None
        match_role = re.match(r"^(.*?)\[@role='([^']*)'\]$", name)
        if match_role:
            name = match_role.group(1)
            role_name = match_role.group(2)
        # 纯 role 形式: [role='xxx']
        match_role_only = re.match(r"^\[role='([^']*)'\]$", name)
        if match_role_only:
            name = None
            role_name = match_role_only.group(1)
        # accessible-id 形式: [accessible-id='xxx'] 或 name[@accessible-id='xxx']
        accessible_id = None
        match_aid = re.match(r"^(.*?)\[@accessible-id='([^']*)'\]$", name)
        if match_aid:
            name = match_aid.group(1)
            accessible_id = match_aid.group(2)
        match_aid_only = re.match(r"^\[accessible-id='([^']*)'\]$", name)
        if match_aid_only:
            name = None
            accessible_id = match_aid_only.group(1)
        if accessible_id:
            elements = _gi_find_descendants(
                element,
                name=name or None,
                role=role_name,
                recursive=recursive,
                accessible_id=accessible_id,
            )
            return node, elements
        if name == "*":
            try:
                element = list(element.children)
            except BaseException:
                element = []
        else:
            element = _gi_find_descendants(
                element,
                name=name or None,
                role=role_name,
                recursive=recursive,
            )
        return node, element

    def __trace(self, element, result, expr):
        if expr.startswith("//"):
            name = expr[2:]
            node, element = self.__evalx(name, element, recursive=True)
        elif expr.startswith("/"):
            name = expr[1:]
            node, element = self.__evalx(name, element, recursive=False)
        else:
            return False
        if node is None:
            return result
        try:
            next_node = name[node.end() - 1 :]
            if next_node != "/":
                for i in element:
                    self.__trace(i, result, next_node)
            else:
                result += element
        except SearchError:
            raise ElementNotFound(expr) from SearchError
        return result

    def find_elements_by_attr(self, expr) -> Union[list, bool]:
        """
         通过层级获取元素
        :param expr: 元素定位 $/xx.xxx//xxx,  $根节点  /当前子节点， //递归查找子节点
        :return: 元素对象
        """
        logger.debug(f"查找元素 expr={expr}")
        if expr == "$":
            return self.obj if isinstance(self.obj, list) else [self.obj]
        if not expr.startswith("$"):
            return False
        if not expr.endswith("/") or expr.endswith(r"\/"):
            expr = expr + "/"
        result = self.__trace(self.obj, [], expr[1:])
        logger.debug(f"元素 {result}")
        return result

    def find_element_by_attr(self, expr, index=0) -> Node:
        """
         查找界面元素
        :param expr: 匹配格式 元素定位 $/xxx//xxx,  $根节点  /当前子节点， //递归查找子节点
        :param index: 匹配结果索引
        :return: 元素对象
        """
        elements = self.find_elements_by_attr(expr)
        if not elements:
            raise ElementNotFound(expr)
        try:
            return elements[index]
        except IndexError:
            raise ElementNotFound(f"{expr}, index:{index}") from IndexError

    def find_element_by_attr_and_click(self, expr, index=0):
        self.find_element_by_attr(expr, index).click()

    def find_element_by_attr_and_right_click(self, expr, index=0):
        self.find_element_by_attr(expr, index).click(3)

    def find_elements_by_accessible_id(self, accessible_id):
        """通过 AT-SPI accessible-id 查找元素。

        Qt/DTK (Qt5/Qt6) 的 at-spi bridge 把 QObject::objectName 编码进
        QAccessibleBridgeUtils::accessibleId() 返回的点分路径，例如
        "EditorApplication.Window.Dtk::Widget::DTitlebar.AddButton"。
        该 id 通过 pyatspi 的 get_accessible_id() 读取，不在
        get_attributes() 中。

        匹配规则：支持完整路径精确匹配，也支持 objectName 后缀匹配
        （element-map 常只记录源码 setObjectName("X") 的短名，运行时
        id 是 "父链.X" 长路径）。
        """
        if not accessible_id:
            return []
        target = str(accessible_id)
        logger.debug(f"查找元素 accessible_id={target}")

        def _match(node):
            try:
                node_id = node.get_accessible_id()
            except Exception:
                return False
            if not node_id:
                return False
            if node_id == target:
                return True
            # 后缀匹配: 真实 id "EditorApplication...UnixAction",
            # element-map 存 "UnixAction"
            return node_id.endswith("." + target)

        # findChildren 对 gi Atspi.Accessible 失效 (pyatspi.utils.
        # findAllDescendants 依赖 __iter__, 普通子节点没有) → 返回空。
        # 用 gi 递归遍历替代 (内部已含活动窗口过滤)。
        return _gi_find_descendants(
            self.obj, accessible_id=target, recursive=True
        )

    def find_element_by_accessible_id(self, accessible_id, index=0):
        """通过 accessible_id 查找单个元素。"""
        elements = self.find_elements_by_accessible_id(accessible_id)
        if not elements:
            raise ElementNotFound(f"accessible_id={accessible_id}")
        try:
            return elements[index]
        except IndexError:
            raise ElementNotFound(f"accessible_id={accessible_id}, index:{index}") from IndexError

    def find_elements_to_the_end(self, ele_name):
        """
         递归查找应用界面的元素(适用于查找多个同名称元素)
        :param ele_name: 需要查找的元素名称
        :return: 查找到的元素对象的列表
        """
        eles = []
        root_ele = self.obj

        def recur_inter(node=None):
            if not node:
                node = root_ele
            children = node.children
            if children:
                for i in children:
                    if i.combovalue == ele_name:
                        eles.append(i)
                    recur_inter(i)

        recur_inter()
        return eles
