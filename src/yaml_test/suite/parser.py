from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from src.yaml_test.suite.models import SuiteSpec


class SuiteValidationError(Exception):
    """Raised when a .suite.yaml file fails parsing or validation."""


def parse_suite(path: str | Path) -> SuiteSpec:
    file_path = Path(path)
    raw_text = file_path.read_text(encoding="utf-8")

    try:
        raw_data: dict[str, Any] | None = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise SuiteValidationError(
            f"[{file_path}] YAML parse failed: {exc}"
        ) from exc

    if raw_data is None:
        raise SuiteValidationError(f"[{file_path}] suite file is empty")
    if not isinstance(raw_data, dict):
        raise SuiteValidationError(
            f"[{file_path}] suite root must be a mapping, got {type(raw_data).__name__}"
        )

    specs_val = raw_data.get("specs")
    if not specs_val or not isinstance(specs_val, list) or len(specs_val) == 0:
        raise SuiteValidationError(
            f"[{file_path}] 'specs' is required and must be a non-empty list"
        )

    try:
        return SuiteSpec.model_validate(raw_data)
    except ValidationError as exc:
        raise SuiteValidationError(
            f"[{file_path}] schema validation failed: {exc}"
        ) from exc
