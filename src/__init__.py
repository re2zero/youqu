#!/usr/bin/env python3
# _*_ coding:utf-8 _*_

# SPDX-FileCopyrightText: 2023 UnionTech Software Technology Co., Ltd.

# SPDX-License-Identifier: GPL-2.0-only
# pylint: disable=C0114
# pylint: disable=R0913,C0413,E0401
import sys

from funnylog import log as log
from funnylog import logger as logger
from funnylog.conf import setting as log_setting
from setting.globalconfig import GlobalConfig

log_setting.LOG_FILE_PATH = GlobalConfig.REPORT_PATH

from setting.globalconfig import SystemPath

for i in SystemPath:
    if i.value not in sys.path:
        sys.path.append(i.value)

from src.dbus_utils import DbusUtils as DbusUtils
from src.calculate import Calculate as Calculate
from src.cmdctl import CmdCtl as CmdCtl
from src.filectl import FileCtl as FileCtl
from src.shortcut import ShortCut as ShortCut
from src.sleepx import sleep as sleep
from src.custom_exception import *

# ── Lazy display-dependent imports ──
# These can fail in sandboxed/headless environments (e.g. multica agent).
# The framework feature they provide (mouse/keyboard simulation) is not
# needed by headless pipelines like AT-SPI YAML generation.
try:
    from src.assert_common import AssertCommon as AssertCommon
except Exception:
    AssertCommon = object  # type: ignore

try:
    from src.dogtail_utils import DogtailUtils as DogtailUtils
except Exception:
    DogtailUtils = object  # type: ignore

try:
    from src.image_utils import ImageUtils as ImageUtils
except Exception:
    ImageUtils = object  # type: ignore

try:
    from src.ocr_utils import OCRUtils as OCR
except Exception:
    OCR = object  # type: ignore

try:
    from src.button_center import ButtonCenter as ButtonCenter
except Exception:
    ButtonCenter = object  # type: ignore

try:
    from src.mouse_key import MouseKey as MouseKey
except Exception:
    MouseKey = object  # type: ignore

try:
    from src.video_utils import VideoUtils as VideoUtils
except Exception:
    VideoUtils = object  # type: ignore

try:
    from src.read_csv import ReadCsv as ReadCsv
except Exception:
    ReadCsv = object  # type: ignore

try:
    from src.pinyin import pinyin as pinyin
except Exception:
    pinyin = object  # type: ignore

try:
    from src.vlm.config import VLMConfig as VLMConfig
    from src.vlm.vlm_executor import VLMExecutor as VLMExecutor
    from src.vlm.vlm_agent import VLMAgent as VLMAgent
    from src.vlm.vlm_locator import (
        create_vlm_locator as create_vlm_locator,
        ClickTarget as ClickTarget,
        VLMAssertResult as VLMAssertResult,
    )
except ImportError:
    VLMConfig = None
    VLMExecutor = None
    VLMAgent = None
    create_vlm_locator = None
    ClickTarget = None
    VLMAssertResult = None


class Src(
    CmdCtl,
    ImageUtils,
    FileCtl,
    ShortCut,
    Calculate,
    OCR,
):
    """src"""

    def __init__(
        self,
        name=None,
        description=None,
        config_path=None,
        number=-1,
        check_start=True,
        ui_name=None,
        **kwargs,
    ):
        """dogtail or button center param
        :param kwargs: app_name, desc, number
        """
        self.dog = DogtailUtils(
            name=name,
            description=description,
            number=number,
            check_start=check_start,
            **kwargs,
        )
        ui_name = ui_name if ui_name else name
        # pylint: disable=invalid-name
        self.ui = ButtonCenter(app_name=ui_name, config_path=config_path, number=number)
        self._vlm_executor = None
        self._vlm_agent = None

    @property
    def vlm(self):
        config = VLMConfig()
        if VLMExecutor is None or not config.is_available():
            return None
        if self._vlm_executor is None:
            locator = create_vlm_locator(config)
            self._vlm_executor = VLMExecutor(locator, config)
        return self._vlm_executor

    @property
    def vlm_agent(self):
        config = VLMConfig()
        if VLMAgent is None or not config.is_available():
            return None
        if self._vlm_agent is None:
            locator = create_vlm_locator(config)
            self._vlm_agent = VLMAgent(locator, config)
        return self._vlm_agent
