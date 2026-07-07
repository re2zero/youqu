# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import os
import re

_VAR_PATTERN = re.compile(r"\$\{(\w+)}")


def substitute(text: str, variables: dict[str, str]) -> str:
    def _replace(match):
        key = match.group(1)
        if key in variables:
            return str(variables[key])
        env_val = os.environ.get(f"YOUQU_{key}", os.environ.get(key, ""))
        if env_val:
            return env_val
        return match.group(0)

    return _VAR_PATTERN.sub(_replace, text)


def substitute_dict(data: dict, variables: dict[str, str]) -> dict:
    return _walk(data, variables)


def _walk(obj, variables: dict[str, str]):
    if isinstance(obj, str):
        return substitute(obj, variables)
    if isinstance(obj, dict):
        return {k: _walk(v, variables) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk(item, variables) for item in obj]
    return obj
