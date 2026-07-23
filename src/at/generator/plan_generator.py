# SPDX-FileCopyrightText: 2026 Uniontech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Generate module-by-module recording plan from cases_raw + docs.

Produces:
- plan.yaml — machine-readable module list with recording guides and status
- plan.md  — human-readable recording instructions per module

The plan drives the module-by-module workflow:
  plan → record(module) → merge → tree-info → map → generate → run(verify)
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", text).strip("_")
    return cleaned.lower()[:64] or "misc"


def _load_cases(cases_path: str) -> dict[str, Any]:
    with open(cases_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _group_by_module(cases_doc: dict[str, Any]) -> list[dict[str, Any]]:
    cases = cases_doc.get("cases", [])
    by_module: dict[str, list[dict]] = {}
    for case in cases:
        module = case.get("module", "").strip()
        if not module:
            module = "misc"
        by_module.setdefault(module, []).append(case)

    modules = []
    for module_name, case_list in by_module.items():
        modules.append(
            {
                "name": module_name,
                "slug": _slugify(module_name),
                "case_count": len(case_list),
                "case_ids": [c.get("id", "") for c in case_list],
            }
        )
    return modules


def _load_docs(docs_dir: str) -> dict[str, str]:
    """Load manual section docs keyed by slug filename.

    Docs are expected in <docs_dir>/modules/<slug>.md format
    (as produced by ``youqu at docs``).
    """
    docs: dict[str, str] = {}
    docs_path = Path(docs_dir)

    modules_dir = docs_path / "modules"
    if modules_dir.is_dir():
        for md in modules_dir.glob("*.md"):
            slug = md.stem
            docs[slug] = md.read_text(encoding="utf-8")
            continue

    # Fallback: scan docs_dir directly for *.md
    if not docs and docs_path.is_dir():
        for md in docs_path.glob("*.md"):
            slug = md.stem
            docs[slug] = md.read_text(encoding="utf-8")

    return docs


def _match_doc_to_module(
    module_slug: str,
    module_name: str,
    docs: dict[str, str],
) -> str:
    """Find best matching doc section for a module.

    Tries exact slug match first, then partial name match.
    Returns the doc body or empty string.
    """
    if module_slug in docs:
        return docs[module_slug]

    for slug, body in docs.items():
        if module_name.lower() in slug.lower() or slug.lower() in module_name.lower():
            return body

    return ""


def _build_recording_guide(
    module_name: str,
    case_count: int,
    doc_body: str,
) -> str:
    """Generate a recording guide for the user."""
    lines = [f"模块: {module_name}", f"用例数: {case_count}", ""]

    if doc_body:
        lines.append("操作指引 (来自帮助手册):")
        lines.append(doc_body.strip())
    else:
        lines.append("操作指引: 请参考用例步骤手动操作该模块的功能。")

    lines.append("")
    lines.append("录制提示: 打开应用 → 按用例步骤操作 → 每个操作后等待界面稳定 → 完成后按 q 结束")
    return "\n".join(lines)


def generate_plan(
    cases_path: str,
    docs_dir: str,
    output_dir: str,
    app_name: str = "",
) -> tuple[str, str]:
    """Generate plan.yaml and plan.md.

    Parameters
    ----------
    cases_path
        Path to cases_raw.yaml.
    docs_dir
        Path to docs output directory (from ``youqu at docs``).
    output_dir
        Directory to write plan.yaml and plan.md.
    app_name
        Application name (fallback: read from cases metadata).

    Returns
    -------
    (plan_yaml_path, plan_md_path)
    """
    cases_doc = _load_cases(cases_path)
    if app_name:
        resolved_app = app_name
    else:
        resolved_app = cases_doc.get("metadata", {}).get("source", "") or "unknown"

    modules_raw = _group_by_module(cases_doc)
    docs = _load_docs(docs_dir)

    now = datetime.now().isoformat()
    modules = []
    for m in modules_raw:
        doc_body = _match_doc_to_module(m["slug"], m["name"], docs)
        guide = _build_recording_guide(m["name"], m["case_count"], doc_body)
        modules.append(
            {
                "slug": m["slug"],
                "name": m["name"],
                "case_count": m["case_count"],
                "case_ids": m["case_ids"],
                "recording_guide": guide,
                "status": "pending",
            }
        )

    plan_data = {
        "app": resolved_app,
        "created_at": now,
        "modules": modules,
    }

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    yaml_path = out / "plan.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(plan_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    md_lines = [
        f"# AT 录制计划: {resolved_app}",
        f"",
        f"生成时间: {now}",
        f"模块数: {len(modules)}",
        f"总用例数: {sum(m['case_count'] for m in modules)}",
        "",
        "---",
        "",
    ]

    for i, m in enumerate(modules, 1):
        md_lines.extend(
            [
                f"## {i}. {m['name']}",
                f"",
                f"- slug: `{m['slug']}`",
                f"- 用例数: {m['case_count']}",
                f"- 状态: {m['status']}",
                f"",
                f"### 录制指引",
                f"",
                m["recording_guide"],
                "",
                "---",
                "",
            ]
        )

    md_path = out / "plan.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"  Plan generated: {len(modules)} modules")
    print(f"  -> {yaml_path}")
    print(f"  -> {md_path}")

    return str(yaml_path), str(md_path)


def load_plan(plan_path: str) -> dict[str, Any]:
    """Load a plan.yaml file."""
    with open(plan_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_module_guide(plan_path: str, module_slug: str) -> str | None:
    """Get recording guide for a specific module from plan.yaml."""
    plan = load_plan(plan_path)
    for m in plan.get("modules", []):
        if m.get("slug") == module_slug:
            return m.get("recording_guide", "")
    return None


def update_module_status(plan_path: str, module_slug: str, status: str) -> bool:
    """Update a module's status in plan.yaml.

    Returns True if the module was found and updated.
    """
    plan = load_plan(plan_path)
    found = False
    for m in plan.get("modules", []):
        if m.get("slug") == module_slug:
            m["status"] = status
            found = True
            break
    if found:
        with open(plan_path, "w", encoding="utf-8") as f:
            yaml.dump(plan, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return found
