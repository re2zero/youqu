# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Parse xlsx/csv test case files into structured cases.yaml via LLM.

Pipeline:
1. Read xlsx/csv -> normalized case list
2. Build prompt with cases + at-tree context (optional)
3. Call OpenAI-compatible LLM
4. Parse LLM output -> CasesDoc (Pydantic validation)
5. Write cases.yaml
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path

COLUMN_ALIASES = {
    "id": ["用例编号", "ID", "编号", "序号"],
    "title": ["用例标题", "标题", "用例名称", "测试点"],
    "module": ["所属模块", "模块", "功能模块", "测试模块"],
    "priority": ["用例级别", "优先级", "级别", "重要程度"],
    "precondition": ["前置条件", "前提条件", "预置条件"],
    "steps": ["步骤", "测试步骤", "操作步骤", "用例步骤"],
    "expected": ["预期", "预期结果", "期望结果", "预期输出"],
    "case_type": ["用例类型", "类型", "测试类型"],
}


def find_column(record: dict, aliases: list[str]) -> str:
    for alias in aliases:
        if alias in record:
            val = record[alias]
            if val:
                return val
    for key in record:
        if any(a.lower() in key.lower() for a in aliases):
            return record[key]
    return ""


def read_xlsx(filepath: str) -> list[dict]:
    try:
        from openpyxl import load_workbook
    except ImportError:
        print("Error: openpyxl not installed. pip install openpyxl")
        sys.exit(1)
    wb = load_workbook(filepath, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(h).strip() if h else "" for h in rows[0]]
    data = []
    for row_idx, row in enumerate(rows[1:], start=2):
        record = {"source_row": row_idx}
        for col_idx, value in enumerate(row):
            if col_idx < len(headers) and headers[col_idx]:
                record[headers[col_idx]] = str(value).strip() if value is not None else ""
        data.append(record)
    return data


def read_csv_file(filepath: str) -> list[dict]:
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        data = []
        for row_idx, row in enumerate(reader, start=2):
            record = {"source_row": row_idx}
            record.update({k.strip(): v.strip() if v else "" for k, v in row.items() if k})
            data.append(record)
        return data


def normalize_cases(raw_data: list[dict]) -> list[dict]:
    cases = []
    for idx, record in enumerate(raw_data):
        cases.append({
            "id": find_column(record, COLUMN_ALIASES["id"]) or str(idx).zfill(3),
            "title": find_column(record, COLUMN_ALIASES["title"]),
            "module": find_column(record, COLUMN_ALIASES["module"]),
            "priority": find_column(record, COLUMN_ALIASES["priority"]),
            "precondition": find_column(record, COLUMN_ALIASES["precondition"]),
            "steps": find_column(record, COLUMN_ALIASES["steps"]),
            "expected": find_column(record, COLUMN_ALIASES["expected"]),
            "case_type": find_column(record, COLUMN_ALIASES["case_type"]),
            "source_row": record.get("source_row", 0),
        })
    return cases


def _get_llm_config() -> dict:
    """Read LLM config from globalconfig.ini [vlm] section with env var overrides."""
    try:
        from setting.globalconfig import GetCfg, GlobalConfig

        cfg_file = GlobalConfig.GLOBAL_CONFIG_FILE_PATH
        cfg = GetCfg(cfg_file, "vlm")
        return {
            "base_url": cfg.get("VLM_BASE_URL", default="http://localhost:8000/v1"),
            "model": os.environ.get(
                "YOUQU_AT_MODEL",
                cfg.get("VLM_MODEL", default="Qwen/Qwen2.5-VL-7B-Instruct"),
            ),
            "api_key": cfg.get("VLM_API_KEY", default="not-needed"),
            "timeout": int(cfg.get("VLM_TIMEOUT", default=30)),
            "max_retries": int(cfg.get("VLM_MAX_RETRIES", default=3)),
            "retry_delay": int(cfg.get("VLM_RETRY_DELAY", default=1)),
        }
    except Exception:
        return {
            "base_url": os.environ.get("YOUQU_AT_BASE_URL", "http://localhost:8000/v1"),
            "model": os.environ.get("YOUQU_AT_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct"),
            "api_key": os.environ.get("YOUQU_AT_API_KEY", "not-needed"),
            "timeout": 30,
            "max_retries": 3,
            "retry_delay": 1,
        }


# JSON schema description embedded in prompt — LLM outputs this structure
_SCHEMA_DESCRIPTION = """{
  "metadata": {
    "generated_at": "ISO8601",
    "source": "input file name"
  },
  "suites": [
    {
      "id": "suite_id",
      "name": "suite名称",
      "module": "模块名",
      "description": "suite描述",
      "status": "active",
      "reason": "",
      "steps": [
        {
          "step_type": "action|assert|navigate",
          "description": "步骤描述",
          "element_hint": "main_menu_comb|context_menu_comb|titlebar|toolbar|sidebar|tab_bar|dialog|tooltip|dock|null",
          "menu_path": ["菜单项1", "菜单项2"]
        }
      ]
    }
  ]
}"""

_PARSE_PROMPT_TEMPLATE = """角色：测试用例整理专家

输入：
1. 原始测试用例列表（xlsx解析结果）
2. at-tree.yaml（UI结构上下文，可能为空）

任务：
- 将相关用例整合为 suites（共享 session 的用例归为一组）
- 过滤不可自动化用例（标记 status: "skipped" + reason）
- 为每个步骤生成 step_type（action/assert/navigate）
- 为每个步骤生成 element_hint
- 确保步骤粒度：每步对应一个可映射的 UI 操作

过滤规则：
- 需要 AT-SPI/键鼠/DBus/CLI 能模拟的 -> 保留（status: "active"）
- 需要人工视觉主观判断的 -> status: "skipped"
- 需要物理设备交互的 -> status: "skipped"
- 需要跨设备协调的 -> status: "skipped"
- 玲珑环境、性能压测、触摸操作、重启类 -> status: "skipped"

element_hint 枚举值：
main_menu_comb, context_menu_comb, titlebar, toolbar, sidebar, tab_bar, dialog, tooltip, dock, null

step_type 说明：
- navigate: 导航类操作（打开菜单、切换tab等）
- action: 执行类操作（点击按钮、输入文本、右键等）
- assert: 验证类操作（检查弹窗、验证状态等）

menu_path：仅 main_menu_comb 和 context_menu_comb 需要填写，其他为 null

输出格式（严格遵循，输出纯JSON，不要markdown代码块）：
{schema}

原始用例数据：
{cases_json}

UI结构上下文（at-tree.yaml）：
{at_tree_context}
"""


def build_parse_prompt(cases: list[dict], at_tree_context: str = "") -> str:
    cases_json = json.dumps(cases, ensure_ascii=False, indent=2)
    return _PARSE_PROMPT_TEMPLATE.format(
        schema=_SCHEMA_DESCRIPTION,
        cases_json=cases_json,
        at_tree_context=at_tree_context or "（无UI上下文）",
    )


def call_llm(prompt: str, config: Optional[dict] = None) -> str:
    if config is None:
        config = _get_llm_config()
    try:
        import httpx
    except ImportError:
        print("Error: httpx not installed. pip install httpx")
        sys.exit(1)
    url = "{}/chat/completions".format(config["base_url"].rstrip("/"))
    headers = {
        "Authorization": "Bearer {}".format(config["api_key"]),
        "Content-Type": "application/json",
    }
    payload = {
        "model": config["model"],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 16384,
        "temperature": 0.1,
    }
    for attempt in range(config["max_retries"]):
        try:
            with httpx.Client(timeout=config["timeout"]) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                if "choices" in data and data["choices"]:
                    return data["choices"][0].get("message", {}).get("content", "")
                return ""
        except httpx.HTTPStatusError as e:
            if attempt == config["max_retries"] - 1:
                print("Error: HTTP {} calling LLM API".format(e.response.status_code))
                return ""
            time.sleep(config["retry_delay"])
        except Exception as e:
            if attempt == config["max_retries"] - 1:
                print("Error calling LLM API: {}".format(e))
                return ""
            time.sleep(config["retry_delay"])
    return ""


def _extract_json(text: str) -> Any:
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        json_lines = []
        in_block = False
        for line in lines:
            if line.startswith("```"):
                in_block = not in_block
                continue
            if in_block:
                json_lines.append(line)
        text = "\n".join(json_lines)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def parse_to_cases(input_path: str, output_path: str, at_tree_path: str = "") -> None:
    """Parse xlsx/csv input into structured cases.yaml via LLM.

    Args:
        input_path: Path to xlsx or csv file.
        output_path: Path to write cases.yaml.
        at_tree_path: Optional path to at-tree.yaml for UI context.
    """
    path = Path(input_path)
    if not path.exists():
        print("Error: input file not found: {}".format(input_path))
        sys.exit(1)

    ext = path.suffix.lower()
    if ext in (".xlsx", ".xls"):
        raw_data = read_xlsx(input_path)
    elif ext == ".csv":
        raw_data = read_csv_file(input_path)
    else:
        print("Error: unsupported format: {}. Use .xlsx or .csv".format(ext))
        sys.exit(1)

    if not raw_data:
        print("Error: no data rows found in {}".format(input_path))
        sys.exit(1)

    cases = normalize_cases(raw_data)
    print("Read {} cases from {}".format(len(cases), input_path))

    at_tree_context = ""
    if at_tree_path:
        tree_path = Path(at_tree_path)
        if tree_path.exists():
            at_tree_context = tree_path.read_text(encoding="utf-8")
            print("Loaded at-tree context ({} bytes)".format(len(at_tree_context)))
        else:
            print("Warning: at-tree file not found: {}".format(at_tree_path))

    prompt = build_parse_prompt(cases, at_tree_context)
    print("Calling LLM API...")
    response = call_llm(prompt)
    if not response:
        print("Error: LLM returned empty response")
        sys.exit(1)

    data = _extract_json(response)
    if data is None:
        print("Error: failed to parse LLM response as JSON")
        sys.exit(1)

    from src.at.parser.models import CasesDoc

    try:
        doc = CasesDoc.model_validate(data)
    except Exception as e:
        print("Error: LLM output failed schema validation: {}".format(e))
        sys.exit(1)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        import yaml

        content = yaml.dump(
            doc.model_dump(by_alias=False, exclude_none=True),
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
    except ImportError:
        content = json.dumps(
            doc.model_dump(by_alias=False, exclude_none=True),
            ensure_ascii=False,
            indent=2,
        )

    out.write_text(content, encoding="utf-8")
    total_steps = sum(len(s.steps) for s in doc.suites)
    skipped = sum(1 for s in doc.suites if s.status == "skipped")
    print(
        "Wrote {} ({} suites, {} steps, {} skipped)".format(
            output_path, len(doc.suites), total_steps, skipped
        )
    )
