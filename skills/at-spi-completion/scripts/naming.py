#!/usr/bin/env python3
"""Naming rule engine for AT-SPI name generation.

Generates English PascalCase AT-SPI names for widget instances
based on display text, variable name, type, or role.

Usage:
    from naming import generate_name, batch_generate
    name = generate_name(instance_dict, existing_names)

CLI:
    python3 naming.py pre_scan_gaps.yaml          # stdout only
    python3 naming.py pre_scan_gaps.yaml -o map.txt  # to file
"""

from __future__ import annotations

import re
from typing import Any


def _strip_m_prefix(var: str) -> str:
    """Strip common Hungarian notation prefixes."""
    for prefix in ("m_", "_"):
        if var.startswith(prefix):
            return var[len(prefix):]
    return var


def _to_pascal_case(text: str) -> str:
    """Convert arbitrary text to PascalCase."""
    # Replace non-alphanumeric with spaces
    text = re.sub(r'[^a-zA-Z0-9]', ' ', text)
    # Split on camelCase boundaries too
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    # Title case each word
    words = text.split()
    return ''.join(w.capitalize() for w in words if w)


def _from_display_text(instance: dict) -> str | None:
    """Generate name from display_text (tr() calls)."""
    text = instance.get("display_text", "")
    if not text:
        return None
    # Strip non-alphanumeric, PascalCase
    return _to_pascal_case(text)


def _from_variable_name(instance: dict) -> str | None:
    """Generate name from variable name."""
    var = instance.get("variable", "")
    if not var:
        return None
    stripped = _strip_m_prefix(var)
    if not stripped:
        return None
    return _to_pascal_case(stripped)


def _from_type_and_class(instance: dict) -> str | None:
    """Generate name from class name + widget type."""
    class_name = instance.get("class_name", "")
    type_name = instance.get("type", "")
    if not class_name and not type_name:
        return None

    # Extract base type (strip pointer, template params)
    base_type = type_name.replace(" *", "").replace("&", "").split("<")[0].strip()
    # Strip D prefix for DTK types
    if base_type.startswith("D") and len(base_type) > 1 and base_type[1].isupper():
        base_type = base_type[1:]
    # Strip Q prefix for Qt types
    if base_type.startswith("Q") and len(base_type) > 1 and base_type[1].isupper():
        base_type = base_type[1:]

    # Map to role-like name
    role_map = {
        "PushButton": "Button",
        "ToolButton": "Button",
        "LineEdit": "Input",
        "TextEdit": "Input",
        "ComboBox": "Combo",
        "CheckBox": "Check",
        "RadioButton": "Radio",
        "SpinBox": "Spin",
        "Slider": "Slider",
        "Action": "Action",
        "Label": "Label",
        "Menu": "Menu",
        "MenuItem": "MenuItem",
        "TabBar": "TabBar",
        "ListView": "List",
        "TreeView": "Tree",
        "TableView": "Table",
        "ScrollBar": "ScrollBar",
        "ProgressBar": "Progress",
        "GroupBox": "Group",
        "ScrollArea": "Scroll",
        "Splitter": "Split",
        "StackedWidget": "Stack",
        "KeySequenceEdit": "Shortcut",
    }

    suffix = role_map.get(base_type, base_type)
    if class_name:
        return f"{_to_pascal_case(class_name)}_{suffix}"
    return suffix


def _from_role(instance: dict, counter: int = 1) -> str:
    """Generate name from AT-SPI role as last resort."""
    role = instance.get("role", "widget")
    if not role:
        role = "widget"
    # PascalCase the role
    role_pascal = _to_pascal_case(role)
    return f"Unnamed{role_pascal}{counter}"


def generate_name(instance: dict, existing_names: set[str] | None = None) -> str:
    """Generate a unique AT-SPI name for a widget instance.

    Priority: display_text > variable_name > type_and_class > role_based
    """
    if existing_names is None:
        existing_names = set()

    # Try each strategy in priority order
    name: str | None = None

    name = _from_display_text(instance)
    if not name:
        name = _from_variable_name(instance)
    if not name:
        name = _from_type_and_class(instance)
    if not name:
        name = _from_role(instance)

    # Ensure uniqueness
    if name in existing_names:
        counter = 2
        while f"{name}_{counter}" in existing_names:
            counter += 1
        name = f"{name}_{counter}"

    # Truncate to 64 chars, then re-check uniqueness
    if len(name) > 64:
        name = name[:64]
        if name in existing_names:
            counter = 2
            while f"{name}_{counter}" in existing_names:
                counter += 1
            name = f"{name}_{counter}"

    return name


def batch_generate(
    instances: list[dict],
    existing_names: set[str] | None = None,
) -> list[tuple[str, str]]:
    """Generate names for multiple instances, handling dedup.

    Returns [(variable, suggested_name), ...]
    """
    if existing_names is None:
        existing_names = set()

    results: list[tuple[str, str]] = []
    for inst in instances:
        name = generate_name(inst, existing_names)
        existing_names.add(name)
        var = inst.get("variable", "")
        src = inst.get("source_file", "")
        line = inst.get("line", 0)
        results.append((var, name, src, line))

    return results


if __name__ == "__main__":
    import json
    import sys
    from typing import Any

    def _load_data(path: str) -> Any:
        """Load JSON or YAML file."""
        try:
            import yaml
            with open(path) as f:
                return yaml.safe_load(f)
        except ImportError:
            pass
        with open(path) as f:
            return json.load(f)

    import argparse
    parser = argparse.ArgumentParser(description="Generate PascalCase AT-SPI names")
    parser.add_argument("input", nargs="?", help="Input YAML/JSON (stdin if omitted)")
    parser.add_argument("-o", "--output", help="Write name mappings to file (stdout if omitted)")
    args = parser.parse_args()

    if args.input:
        data = _load_data(args.input)
    else:
        data = json.load(sys.stdin)

    instances = data if isinstance(data, list) else data.get("gaps", data.get("widgets", [data]))
    # QML gaps carry scan-time suggested_name (tokenizer-scoped naming).
    # Honor it: regenerate only as a fallback when absent.
    resolved = []
    for inst in instances:
        suggested = inst.get("suggested_name", "")
        if suggested:
            resolved.append((inst.get("id") or inst.get("variable", ""),
                             suggested, inst.get("source_file", ""), inst.get("line", 0)))
        else:
            resolved.extend(batch_generate([inst]))
    results = resolved
    output = "\n".join(f"{var:<30} -> {name:<30}  # {src}:{line}"
                       for var, name, src, line in results)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output + "\n")
        print(f"Written {len(results)} name(s) to {args.output}")
    else:
        print(output)