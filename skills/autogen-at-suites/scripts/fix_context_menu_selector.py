"""Post-process cases_mapped.yaml: inject selector for dtk_context_menu.

Runs after ai_mapper, before yaml_generator.
"""
import argparse
import re
import sys
from pathlib import Path
import yaml

APP_DEFAULT_TARGETS = {
    "deepin-terminal": "TermWidgetPage",
    "deepin-reader": "Form_CentralDocPage",
    "dde-file-manager": "MainWindow",
    "deepin-album": "MainWindow",
    "deepin-music": "MainWindow",
}

def load_at_tree_names(at_tree_path):
    try:
        data = yaml.safe_load(Path(at_tree_path).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError):
        return set()
    names = set()
    def walk(nodes):
        for n in (nodes or []):
            if n.get("name"): names.add(n["name"])
            walk(n.get("children", []))
    tree = data.get("tree", []) if isinstance(data, dict) else data
    if isinstance(tree, list): walk(tree)
    return names

def find_best_selector(step, at_tree_names, app_name):
    items = step.get("items", [])
    default = APP_DEFAULT_TARGETS.get(app_name)
    if default and default in at_tree_names:
        return {"name": default}
    for name in sorted(at_tree_names):
        if name and name not in ("TabBar", "TitleBar"):
            return {"name": name}
    return None

def fix_cases(cases_path, at_tree_path, output_path, app_name=""):
    data = yaml.safe_load(Path(cases_path).read_text(encoding="utf-8"))
    if not app_name:
        app_name = data.get("metadata", {}).get("app", "unknown")
    at_tree_names = load_at_tree_names(at_tree_path)
    
    fixed = 0
    for case in data.get("cases", []):
        for step in case.get("steps", []):
            if step.get("action") != "dtk_context_menu":
                continue
            sel = step.get("selector") or {}
            if sel.get("name"): continue
            if step.get("ref"): continue
            selector = find_best_selector(step, at_tree_names, app_name)
            if selector:
                step["selector"] = selector
                fixed += 1
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return {"fixed": fixed}

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--cases", required=True)
    p.add_argument("--at-tree", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--app", default="")
    args = p.parse_args()
    r = fix_cases(args.cases, args.at_tree, args.output, args.app)
    print(f"Fixed {r['fixed']} dtk_context_menu selectors")
