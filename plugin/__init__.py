# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""YouQu pytest plugin — sys.path injection and environment setup.

Registered via [project.entry-points.pytest11] in pyproject.toml.
"""

import os
import sys
from pathlib import Path

# site-packages/youqu/
_YOUQU_PKG = Path(__file__).resolve().parent.parent

# Paths to inject into sys.path
_INJECT_PATHS = (
    _YOUQU_PKG,                        # "from src import ...", "from setting import ..."
    _YOUQU_PKG / "setting",            # "from setting.globalconfig import GlobalConfig"
    _YOUQU_PKG / "src" / "depends",    # "from dogtail.tree import ..." etc.
)


def pytest_configure(config):
    _inject_paths()
    _setup_env()


def _inject_paths():
    for p in _INJECT_PATHS:
        p_str = str(p)
        if p_str not in sys.path:
            sys.path.insert(0, p_str)


def _setup_env():
    os.environ.setdefault("DISPLAY", ":0")
    os.environ.setdefault(
        "XAUTHORITY", f"{os.path.expanduser('~')}/.Xauthority"
    )
