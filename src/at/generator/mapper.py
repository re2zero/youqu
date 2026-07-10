# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import warnings
from pathlib import Path

from src.at.parser.models import ElementMappingsDoc, MappingsMetadata


def map_elements(at_tree_path: str, cases_path: str, output_path: str) -> None:
    warnings.warn(
        "'youqu at map' is deprecated. Element mapping is now done by the AI "
        "in the session. Use 'youqu at parse' + 'youqu at tree-info' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc = ElementMappingsDoc(
        metadata=MappingsMetadata(at_tree_source=at_tree_path),
        mappings=[],
    )

    try:
        import yaml as pyyaml

        data = doc.model_dump(mode="json")
        with open(output_path, "w", encoding="utf-8") as f:
            pyyaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    except ImportError:
        import json

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(doc.model_dump(mode="json"), f, ensure_ascii=False, indent=2)

    print(f"Wrote {output_path} (empty, 'youqu at map' is deprecated)")
