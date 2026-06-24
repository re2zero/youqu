# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Static checks for Web spec files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from web_spec.kind import WebSpecFileKind, detect_web_spec_kind, is_config_file, is_legacy_suite_file, is_suite_file
from web_spec.loader import SpecValidationError, load_spec
from web_spec.models import ActionSpec, ActionType, AssertionSpec, Locator, LocatorStrategy, TestSpec
from web_spec.suite import load_suite


@dataclass
class CheckIssue:
    """One static check issue."""

    severity: str
    file: str
    message: str
    code: str = "general"
    step: int | None = None
    item: str = ""
    suggestion: str = ""


@dataclass
class CheckReport:
    """Aggregated static check result."""

    checked: int = 0
    skipped: int = 0
    cases: int = 0
    suites: int = 0
    issues: list[CheckIssue] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "ERROR")

    @property
    def warnings(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "WARN")

    @property
    def ok(self) -> bool:
        return self.errors == 0


def check_specs(path: str | Path) -> CheckReport:
    """Check one Web spec file or a directory recursively."""
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(f"spec 路径不存在: {root}")

    report = CheckReport()
    files = _iter_yaml_files(root)
    for file_path in files:
        if _is_non_spec_yaml(file_path):
            report.skipped += 1
            continue
        if is_legacy_suite_file(file_path):
            report.checked += 1
            report.issues.append(CheckIssue(
                severity="ERROR",
                file=str(file_path),
                code="suite_naming",
                message="外部 suite 文件不再支持。",
                suggestion="将 suite 改为文件夹组织，并在文件夹内创建 suite.yaml 或 suite.yml。",
            ))
            continue
        try:
            raw = _read_yaml_mapping(file_path)
        except SpecValidationError as exc:
            report.checked += 1
            report.issues.append(CheckIssue(
                severity="ERROR",
                file=str(file_path),
                code="yaml_parse",
                message=str(exc),
                suggestion="修复 YAML 语法或确认该文件不是 Web spec。",
            ))
            continue

        kind = detect_web_spec_kind(raw)
        if kind == WebSpecFileKind.UNKNOWN:
            if not _looks_like_web_yaml(raw):
                report.skipped += 1
                continue
        if kind == WebSpecFileKind.INVALID:
            report.checked += 1
            report.issues.append(CheckIssue(
                severity="ERROR",
                file=str(file_path),
                code="mixed_kind",
                message="同一个 YAML 不能同时包含 specs 和 steps。",
                suggestion="suite 使用 specs 字段，普通 case 使用 steps 字段，请拆分为两个文件。",
            ))
            continue
        if kind == WebSpecFileKind.SUITE:
            report.checked += 1
            report.suites += 1
            has_valid_suite_name = is_suite_file(file_path)
            if not has_valid_suite_name:
                report.issues.append(CheckIssue(
                    severity="ERROR",
                    file=str(file_path),
                    code="suite_naming",
                    message="suite 文件名不符合命名规范。",
                    suggestion="suite 必须以文件夹组织，并在文件夹内使用 suite.yaml 或 suite.yml。",
                ))
            try:
                load_suite(file_path, require_suite_name=has_valid_suite_name)
            except SpecValidationError as exc:
                report.issues.append(CheckIssue(
                    severity="ERROR",
                    file=str(file_path),
                    code="suite_schema",
                    message=str(exc),
                    suggestion="按 suite schema 补齐 specs、setup、teardown 等字段，并确认引用的 case 存在。",
                ))
            continue

        try:
            spec = load_spec(file_path)
        except SpecValidationError as exc:
            if not _looks_like_web_yaml(raw):
                report.skipped += 1
                continue
            report.checked += 1
            report.cases += 1
            report.issues.append(CheckIssue(
                severity="ERROR",
                file=str(file_path),
                code="schema",
                message=str(exc),
                suggestion="按 Web Spec schema 补齐 title、steps、action/assertion、locator 等字段。",
            ))
            continue

        report.checked += 1
        report.cases += 1
        report.issues.extend(_check_raw_fields(file_path, raw))
        report.issues.extend(_check_spec_quality(file_path, spec))

    return report


def _iter_yaml_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(
        path for path in root.rglob("*.y*ml")
        if path.is_file() and path.name != "index.yaml"
    )


def _is_non_spec_yaml(file_path: Path) -> bool:
    return file_path.name in {"index.yaml", "elements.yaml"} or is_config_file(file_path)


def _read_yaml_mapping(file_path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SpecValidationError(f"[{file_path}] YAML 解析失败: {exc}") from exc
    if raw is None:
        raise SpecValidationError(f"[{file_path}] spec 文件为空")
    if not isinstance(raw, dict):
        raise SpecValidationError(f"[{file_path}] spec 根节点必须是 mapping")
    return raw


def _looks_like_web_yaml(raw: dict[str, Any]) -> bool:
    if any(key in raw for key in ("title", "entry_page", "entry_url", "setup", "teardown", "execution", "specs")):
        return True
    steps = raw.get("steps")
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue
            if any(key in step for key in ("actions", "assertions", "assert", "expected")):
                return True
            if "locator" in step and "type" in step:
                return True
    return False


def _check_raw_fields(file_path: Path, raw: dict[str, Any]) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    if "name" in raw and "title" not in raw:
        issues.append(CheckIssue(
            severity="WARN",
            file=str(file_path),
            code="legacy_name",
            message="使用了兼容字段 name 作为标题。",
            suggestion="建议改为 title，减少迁移歧义。",
        ))
    for step_index, step in enumerate(raw.get("steps", []) or [], start=1):
        if not isinstance(step, dict):
            continue
        if "assert" in step and "assertions" not in step:
            issues.append(CheckIssue(
                severity="WARN",
                file=str(file_path),
                step=step_index,
                item="step",
                code="legacy_assert",
                message="使用了兼容字段 assert。",
                suggestion="建议改为 assertions。",
            ))
    return issues


def _check_spec_quality(file_path: Path, spec: TestSpec) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    for action_index, action in enumerate(spec.setup, start=1):
        issues.extend(_check_action(file_path, action, 0, action_index, setup=True))
    for step_index, step in enumerate(spec.steps, start=1):
        for action_index, action in enumerate(step.actions, start=1):
            issues.extend(_check_action(file_path, action, step_index, action_index))
        for assertion_index, assertion in enumerate(step.assertions, start=1):
            issues.extend(_check_assertion(file_path, assertion, step_index, assertion_index))
    return issues


def _check_action(
    file_path: Path,
    action: ActionSpec,
    step_order: int,
    index: int,
    setup: bool = False,
) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    item = f"{'setup ' if setup else ''}action {index}: {action.type.value}"
    if action.locator:
        issues.extend(_check_locator(file_path, action.locator, step_order, item, interactive=True))
    if action.target:
        issues.extend(_check_locator(file_path, action.target, step_order, f"{item} target", interactive=True))
    if action.type == ActionType.WAIT_FOR and not action.locator and action.timeout_ms > 10000:
        issues.append(CheckIssue(
            severity="WARN",
            file=str(file_path),
            step=step_order or None,
            item=item,
            code="long_static_wait",
            message=f"wait_for 未指定 locator 且 timeout_ms={action.timeout_ms}，会退化为固定等待。",
            suggestion="优先提供 locator 或 wait_for_text；确需固定等待时缩短 timeout。",
        ))
    return issues


def _check_assertion(
    file_path: Path,
    assertion: AssertionSpec,
    step_order: int,
    index: int,
) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    item = f"assertion {index}: {assertion.type.value}"
    if assertion.locator:
        issues.extend(_check_locator(file_path, assertion.locator, step_order, item, interactive=False))
    if assertion.type.value.startswith("attribute_") and not assertion.attribute:
        issues.append(CheckIssue(
            severity="ERROR",
            file=str(file_path),
            step=step_order,
            item=item,
            code="missing_attribute",
            message=f"{assertion.type.value} 缺少 attribute 字段。",
            suggestion="补充需要读取的属性名，例如 aria-label、disabled。",
        ))
    if _requires_expected(assertion) and assertion.expected is None:
        issues.append(CheckIssue(
            severity="ERROR",
            file=str(file_path),
            step=step_order,
            item=item,
            code="missing_expected",
            message=f"{assertion.type.value} 缺少 expected 字段。",
            suggestion="补充期望值，避免运行时断言失败或脚本异常。",
        ))
    if assertion.type.value in {"url_equals", "url_contains"} and assertion.locator:
        issues.append(CheckIssue(
            severity="WARN",
            file=str(file_path),
            step=step_order,
            item=item,
            code="unused_locator",
            message=f"{assertion.type.value} 不需要 locator。",
            suggestion="删除 locator，直接使用 expected 校验当前页面 URL。",
        ))
    return issues


def _requires_expected(assertion: AssertionSpec) -> bool:
    return assertion.type.value in {
        "text_contains",
        "text_equals",
        "html_contains",
        "html_equals",
        "count",
        "input_value_equals",
        "input_value_contains",
        "attribute_equals",
        "attribute_contains",
        "class_contains",
        "url_equals",
        "url_contains",
        "text_sequence",
    }


def _check_locator(
    file_path: Path,
    locator: Locator,
    step_order: int,
    item: str,
    interactive: bool,
) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    if locator.strategy in (LocatorStrategy.CSS, LocatorStrategy.BEM_CSS):
        issues.extend(_check_css_locator(file_path, locator, step_order, item))
    if locator.strategy == LocatorStrategy.TEXT and not locator.exact:
        issues.append(CheckIssue(
            severity="WARN",
            file=str(file_path),
            step=step_order or None,
            item=item,
            code="broad_text_locator",
            message=f"text locator '{locator.value}' 未设置 exact，可能匹配过宽。",
            suggestion="若文本稳定，建议设置 exact: true；否则改用 role/test_id/css。",
        ))
    if interactive and locator.strategy == LocatorStrategy.TEXT and locator.value.strip() in {"删除", "确定", "取消", "提交"} and not locator.exact:
        issues.append(CheckIssue(
            severity="WARN",
            file=str(file_path),
            step=step_order or None,
            item=item,
            code="ambiguous_action_text",
            message=f"交互动作使用常见文本 '{locator.value}'，容易多匹配。",
            suggestion="建议补充 exact: true，或改用 role/test_id。",
        ))
    if locator.scope:
        issues.extend(_check_locator(file_path, locator.scope, step_order, f"{item} scope", interactive=False))
    return issues


def _check_css_locator(file_path: Path, locator: Locator, step_order: int, item: str) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    value = locator.value
    risky_tokens = [":nth-child", ":last-child", "div > div > div"]
    for token in risky_tokens:
        if token in value:
            issues.append(CheckIssue(
                severity="WARN",
                file=str(file_path),
                step=step_order or None,
                item=item,
                code="fragile_selector",
                message=f"selector '{value}' 包含脆弱片段 '{token}'。",
                suggestion="优先使用 test_id、role，或使用更稳定的业务 class。",
            ))
            break
    if value.strip() in {"div", "span", "button", "input", "textarea", "a"}:
        issues.append(CheckIssue(
            severity="WARN",
            file=str(file_path),
            step=step_order or None,
            item=item,
            code="broad_css_locator",
            message=f"css locator '{value}' 过宽，可能匹配大量元素。",
            suggestion="使用更具体 selector，例如 data-testid、class、属性选择器。",
        ))
    return issues
