#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Multica 智能体 — 自动生成 AT-SPI YAML 测试用例。

核心思路：**scan + dump + merge** 自动化获取 AT 元树，语义映射由 AI 智能体
按照 `at-case-generator` 技能完成；本模块只负责可脚本化的数据准备与生成/验证。

  Pipeline:
  1. scan     — 源码扫描（Clang），提取全部 UI 控件类骨架
  2. dump     — 启动应用，dump 运行时 AT-SPI 树
  3. merge    — merge_trees() 合并，静态无运行时无法渲染的也作为占位节点加入
  4. parse    — 解析 xlsx/csv 用例为 cases_raw.yaml
  5. AI 映射  — 由 AI 智能体按 at-case-generator Step 3 生成 cases_mapped.yaml
  6. generate — 使用 AI 映射结果生成可执行 YAML 套件（输出到 tests/at/yaml/）
  7. run      — 执行生成的测试
  8. report   — 汇总结果

  合并策略（merge_trees 原生逻辑）：
  - 静态有 + 运行时也有 → 富化节点（class_name, object_name, accessible_id 注入）
  - 静态有 + 运行时没有 → _add_unmatched_static_nodes 作为占位节点加入
  - 静态没有 + 运行时才有 → 保留（动态创建或非 Qt 控件）

  不依赖：
  - ❌ youqu at record（事件驱动录制，Multica 环境不可用）
  - ❌ explore 乱点（不可靠，遗漏控件）
  - ❌ 脚本正则映射（ai_mapper 等）：映射必须是 AI 对 AT 元树 + 用例描述的理解
"""

from __future__ import annotations

import copy
import json
import logging
import os
import subprocess
import sys
import time
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("youqu.multica_agent")

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_AT_TREE_VERSION = "1.0"
_LAUNCH_TIMEOUT = 15.0  # 秒，等待应用启动
_APP_READY_POLL = 0.5  # 秒，轮询间隔

# ---------------------------------------------------------------------------
# MulticaAgent
# ---------------------------------------------------------------------------


class MulticaAgent:
    """Multica 智能体 — 自动生成 AT-SPI YAML 测试用例。

    核心：scan + dump + merge，确定性覆盖全部 UI 控件。

    Args:
        app_name: 应用名（AT-SPI 名称，如 'deepin-music'）
        app_binary: 应用二进制路径（可选，用于启动）
        app_package: 应用包名（可选，用于版本检测）
        src_dir: 应用源码目录（可选，用于 Clang 静态扫描）
        output_dir: 输出目录，默认 tests/at/
        issue_id: Multica issue ID（可选，用于报告）
        report_interval: 心跳报告间隔（秒）
    """

    def __init__(
        self,
        app_name: str,
        app_binary: str = "",
        app_package: str = "",
        src_dir: str = "",
        output_dir: str = "",
        issue_id: str = "",
        report_interval: int = 300,
    ):
        self.app_name = app_name
        self.app_binary = app_binary or app_name
        self.app_package = app_package or app_name
        self.src_dir = src_dir
        self.issue_id = issue_id
        self.report_interval = report_interval

        # 输出目录默认到 project_root/tests/at/
        if output_dir:
            self.output_dir = Path(output_dir).resolve()
        else:
            self.output_dir = Path(os.getcwd()) / "tests" / "at"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # YAML 套件输出目录 tests/at/yaml/
        self.yaml_dir = self.output_dir / "yaml"
        self.yaml_dir.mkdir(parents=True, exist_ok=True)

        # 管线产物
        self._scan_result: Any = None  # ScanResult from clang_scanner
        self._runtime_tree: list[dict] = []  # 运行时 dump
        self._app_process: subprocess.Popen | None = None
        self._reporter: Any | None = None

        # 设置日志
        log_path = self.output_dir / "agent.log"
        fh = logging.FileHandler(str(log_path), encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        logger.setLevel(logging.DEBUG)

        # 初始化 multica reporter（如果传了 issue_id）
        if issue_id:
            self._init_reporter()

    # ------------------------------------------------------------------
    # 报告
    # ------------------------------------------------------------------

    def _init_reporter(self) -> None:
        """初始化 multica 进度报告器。"""
        try:
            from cli.multica import MulticaReporter
            self._reporter = MulticaReporter(
                issue_id=self.issue_id,
                app_name=self.app_name,
                app_command=self.app_binary,
                report_interval=self.report_interval,
            )
        except ImportError:
            logger.warning("MulticaReporter 不可用，跳过进度报告")
            self._reporter = None

    def _report_progress(self, message: str) -> None:
        """记录进度（日志 + 可选 multica 心跳）。"""
        logger.info("进度: %s", message)

    def _report_final(self, summary: str = "") -> None:
        """发送最终报告。"""
        if self._reporter:
            self._reporter.finish(summary=summary)

    # ------------------------------------------------------------------
    # 应用生命周期
    # ------------------------------------------------------------------

    def launch_app(self) -> bool:
        """启动目标应用。"""
        self._report_progress(f"启动应用 {self.app_name}...")

        # 先杀已有进程（精确匹配进程名，避免误杀）
        subprocess.run(
            ["pkill", "-x", self.app_name],
            capture_output=True, timeout=5,
        )
        time.sleep(0.5)

        try:
            self._app_process = subprocess.Popen(
                [self.app_binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.error("找不到可执行文件: %s", self.app_binary)
            return False

        # 等待应用在 AT-SPI 树中出现
        deadline = time.monotonic() + _LAUNCH_TIMEOUT
        while time.monotonic() < deadline:
            try:
                tree = self._dump_tree()
                if tree:
                    logger.info("应用 %s 已启动，树中有 %d 个根节点",
                                self.app_name, len(tree))
                    return True
            except Exception:
                pass
            time.sleep(_APP_READY_POLL)

        logger.error("应用 %s 启动超时", self.app_name)
        return False

    def kill_app(self) -> None:
        """关闭应用。"""
        subprocess.run(
            ["pkill", "-x", self.app_name],
            capture_output=True, timeout=5,
        )
        if self._app_process:
            try:
                self._app_process.terminate()
                self._app_process.wait(timeout=3)
            except Exception:
                self._app_process.kill()
            self._app_process = None

    # ------------------------------------------------------------------
    # AT-SPI 树操作
    # ------------------------------------------------------------------

    def _dump_tree(self) -> list[dict]:
        """dump 当前应用的 AT-SPI 树。"""
        from src.at.scanner.atspi_dumper import dump_at_spi_tree
        return dump_at_spi_tree(self.app_name) or []

    # ------------------------------------------------------------------
    # 阶段 1：源码扫描（Clang）
    # ------------------------------------------------------------------

    def scan_source(self) -> dict[str, Any]:
        """扫描源码，提取全部 UI 控件类。

        Returns:
            扫描统计信息。
        """
        if not self.src_dir:
            return {"status": "skipped", "reason": "未提供源码目录 (--src)"}

        src_path = Path(self.src_dir)
        if not src_path.is_dir():
            return {"status": "error", "reason": f"源码目录不存在: {self.src_dir}"}

        self._report_progress(f"阶段 1: 扫描源码 {self.src_dir}...")

        try:
            from src.at.scanner.clang_scanner import scan_source_dir
            from src.at.scanner.merger import dedup_static_classes

            # 扫描
            self._scan_result = scan_source_dir(self.src_dir)
            if not self._scan_result or not self._scan_result.classes:
                logger.warning("扫描未发现 UI 控件类")
                return {"status": "ok", "classes": 0, "files": 0}

            # 去重
            self._scan_result.classes = dedup_static_classes(self._scan_result.classes)

            stats = {
                "status": "ok",
                "classes": len(self._scan_result.classes),
                "files": self._scan_result.stats.get("total_files", 0),
                "parsed": self._scan_result.stats.get("parsed_files", 0),
                "failed": self._scan_result.stats.get("failed_files", 0),
            }
            logger.info("扫描完成: %d 个 UI 控件类, %d 个文件",
                        stats["classes"], stats["files"])

            # 写入静态 dump 供调试
            from src.at.scanner.merger import write_static_dump, generate_name_gaps_report
            static_path = self.output_dir / "scanned_classes.yaml"
            write_static_dump(self._scan_result.classes, str(static_path))
            gaps_path = self.output_dir / "element_gaps.yaml"
            generate_name_gaps_report(
                self._scan_result.classes, str(gaps_path), app_name=self.app_name
            )

            self._report_progress(
                f"扫描完成: {stats['classes']} 个控件类, "
                f"{stats['files']} 个文件"
            )
            return stats

        except ImportError as e:
            logger.warning("Clang 静态扫描不可用: %s", e)
            return {"status": "skipped", "reason": f"libclang 未安装: {e}"}

    # ------------------------------------------------------------------
    # 阶段 2：运行时 dump + merge
    # ------------------------------------------------------------------

    def dump_and_merge(self, output_path: str = "") -> str:
        """启动应用 → dump AT-SPI 树 → merge 静态类 → 输出 at-tree.yaml。

        merge_trees 合并策略：
        - 静态有 + 运行时也有 → 富化节点（class_name, object_name, accessible_id）
        - 静态有 + 运行时没有 → 作为占位节点加入（source: static）
        - 静态没有 + 运行时才有 → 保留（动态创建或非 Qt 控件）

        这保证 **100% 覆盖** 源码中声明的全部 UI 控件。

        Args:
            output_path: at-tree.yaml 输出路径。

        Returns:
            at-tree.yaml 路径，失败返回空字符串。
        """
        self._report_progress("阶段 2: dump 运行时树 + merge...")

        # 启动应用
        if not self.launch_app():
            return ""

        try:
            # dump 运行时树
            self._runtime_tree = self._dump_tree()
            if not self._runtime_tree:
                logger.error("运行时树为空")
                return ""

            tree_node_count = self._count_nodes(self._runtime_tree)
            logger.info("运行时树: %d 个根节点, %d 个总节点",
                        len(self._runtime_tree), tree_node_count)
            self._report_progress(
                f"运行时树: {tree_node_count} 个节点"
            )

            # 合并
            from src.at.scanner.merger import (
                merge_trees,
                write_at_tree_yaml,
                write_runtime_dump,
            )

            # 先写原始运行时 dump（调试用）
            runtime_path = self.output_dir / "runtime_dump.yaml"
            write_runtime_dump(
                self._runtime_tree, str(runtime_path), app_name=self.app_name
            )

            # 获取静态类列表
            static_classes = []
            if self._scan_result and self._scan_result.classes:
                static_classes = self._scan_result.classes
                logger.info("静态扫描: %d 个控件类参与合并", len(static_classes))

            # merge_trees：核心合并逻辑
            merged = merge_trees(self._runtime_tree, static_classes)
            if not merged:
                logger.error("合并后树为空")
                return ""

            merged_count = self._count_nodes(merged)
            logger.info("合并后树: %d 个根节点, %d 个总节点",
                        len(merged), merged_count)

            # 统计静态来源的占位节点
            placeholder_count = sum(
                1 for n in self._flatten_nodes(merged)
                if n.get("source") == "static"
            )
            if placeholder_count > 0:
                logger.info(
                    "  %d 个占位节点（静态有、运行时无 → 源码中声明的未渲染控件）",
                    placeholder_count,
                )

            # 写入 at-tree.yaml
            out_path = Path(output_path) if output_path else \
                self.output_dir / "at-tree.yaml"
            write_at_tree_yaml(
                merged,
                str(out_path),
                app_name=self.app_name,
            )

            self._report_progress(
                f"at-tree.yaml 已生成: {merged_count} 个节点 "
                f"({placeholder_count} 个占位节点)"
            )
            return str(out_path)

        finally:
            self.kill_app()

    @staticmethod
    def _count_nodes(nodes: list[dict]) -> int:
        """递归统计节点总数。"""
        count = 0
        for node in nodes:
            count += 1
            count += MulticaAgent._count_nodes(node.get("children", []))
        return count

    @staticmethod
    def _flatten_nodes(nodes: list[dict]) -> list[dict]:
        """展平树为列表。"""
        flat: list[dict] = []
        for node in nodes:
            flat.append(node)
            flat.extend(MulticaAgent._flatten_nodes(node.get("children", [])))
        return flat

    # ------------------------------------------------------------------
    # 阶段 3：解析用例
    # ------------------------------------------------------------------

    def parse_cases(self, input_path: str, output_path: str = "",
                    at_tree_path: str = "") -> str:
        """解析 xlsx/csv 用例文件为 cases_raw.yaml。"""
        self._report_progress(f"阶段 3: 解析用例文件 {input_path}...")

        out_path = Path(output_path) if output_path else \
            self.output_dir / "cases_raw.yaml"

        from src.at.generator.case_parser import parse_to_cases
        parse_to_cases(
            input_path=input_path,
            output_path=str(out_path),
            at_tree_path=at_tree_path,
        )

        logger.info("用例已解析: %s", out_path)
        return str(out_path)

    @staticmethod
    def _load_src_module(module_path: str) -> Any:
        """Load a src module via importlib, bypassing src/__init__.py DISPLAY dep.

        Args:
            module_path: Relative path from project root, e.g.
                         "src/at/generator/case_parser.py"

        Returns:
            Loaded module object.
        """
        import importlib.util as _ilu

        _base = Path(__file__).resolve().parent.parent
        _full = _base / module_path
        _name = "_src_" + module_path.replace("/", "_").replace(".py", "")
        _spec = _ilu.spec_from_file_location(_name, str(_full))
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        return _mod

    @staticmethod
    def _looks_mapped(cases_path: str) -> bool:
        """Detect whether a cases YAML already contains mapped actions."""
        try:
            import yaml
            data = yaml.safe_load(Path(cases_path).read_text(encoding="utf-8"))
            cases = data.get("cases", []) if isinstance(data, dict) else []
            for case in cases[:1]:
                steps = case.get("steps", [])
                if steps and isinstance(steps[0], dict) and steps[0].get("action"):
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def _load_mapped_stats(mapped_path: str) -> dict:
        """Load summary stats from an AI-mapped cases_mapped.yaml."""
        import yaml
        data = yaml.safe_load(Path(mapped_path).read_text(encoding="utf-8"))
        cases = data.get("cases", []) if isinstance(data, dict) else []
        total_steps = sum(len(c.get("steps", [])) for c in cases)
        return {
            "status": "ok",
            "cases_mapped": len(cases),
            "steps_mapped": total_steps,
            "mapped_actions": total_steps,
            "unsupported_steps": 0,
            "output": mapped_path,
            "source": "AI manual (at-case-generator)",
        }

    # ------------------------------------------------------------------
    # 阶段 4：生成套件
    # ------------------------------------------------------------------

    def generate_suite(self, cases_path: str, at_tree_path: str,
                       output_dir: str = "",
                       skip_mapping: bool = False) -> tuple[str, dict]:
        """生成可执行 YAML 测试套件。

        Args:
            cases_path: cases_raw.yaml 路径（AI 映射的输入）或 cases_mapped.yaml 路径。
            at_tree_path: at-tree.yaml 路径。
            output_dir: 套件输出目录（默认 tests/at/yaml/）。
            skip_mapping: 为 True 时使用已存在的 cases_mapped.yaml（由 AI 按 at-case-generator 生成）。

        Returns:
            (suite_dir, stats)

        Raises:
            RuntimeError: 缺少 AI 映射结果时，提示先完成 at-case-generator Step 3。
        """
        self._report_progress("阶段 4: 生成 YAML 测试套件...")

        suite_dir = Path(output_dir) if output_dir else \
            self.yaml_dir
        suite_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: tree-info → 精简 at-tree（输出到 tests/at/ 级别，可选）
        #   如果 DISPLAY 不可用则跳过（不影响用例生成）
        tree_info_path = self.output_dir / "at-tree-compact.yaml"
        try:
            _cp = self._load_src_module("src/at/generator/case_parser.py")
            _cp.compact_at_tree_to_file(
                at_tree_path=at_tree_path,
                output_path=str(tree_info_path),
                fmt="yaml",
            )
        except Exception as exc:
            logger.warning("Compact tree skipped (no DISPLAY?): %s", exc)

        mapped_path = self.output_dir / "cases_mapped.yaml"

        # 确定要喂给 generate_yaml 的 cases_mapped 文件。
        # 注意：这里绝不调用脚本/正则映射；cases_mapped.yaml 必须由 AI 智能体
        # 按照 at-case-generator Step 3 理解 AT 元树和用例描述后填写。
        cases_input = ""
        map_stats: dict = {}

        if skip_mapping:
            if not mapped_path.exists():
                raise RuntimeError(
                    "缺少 AI 映射结果: 请先按 at-case-generator Step 3 生成 "
                    f"{mapped_path}，再使用 --skip-mapping 生成套件。"
                )
            cases_input = str(mapped_path)
            map_stats = self._load_mapped_stats(cases_input)
            logger.info("使用 AI 已映射结果: %s", cases_input)
        elif self._looks_mapped(cases_path):
            cases_input = cases_path
            map_stats = self._load_mapped_stats(cases_input)
            logger.info("使用传入的 AI 已映射结果: %s", cases_input)
        else:
            # 仍生成 precandidate 作为 AI 参考，但不自动映射
            candidates_path = self.output_dir / "suite-cases.yaml"
            try:
                _precan = self._load_src_module("src/at/generator/precandidate.py")
                _precan.precandidate_from_cases(
                    cases_path=cases_path,
                    at_tree_path=at_tree_path,
                    output_path=str(candidates_path),
                )
            except Exception as exc:
                logger.warning("Precandidate skipped (debug-only): %s", exc)
            raise RuntimeError(
                "AI 语义映射是必需的，不能由脚本代替。"
                "请按 at-case-generator 技能完成："
                "1) 阅读 at-tree-annotated.yaml 与 cases_raw.yaml；"
                "2) AI 理解并拆分步骤，填写 action/selector/items/key/text；"
                "3) 写出 cases_mapped.yaml；"
                "4) 重新运行本命令并加 --skip-mapping。"
            )

        # Step 2b: 保留 precandidate 输出作为引用（仅调试用，不用于生成）
        candidates_path = self.output_dir / "suite-cases.yaml"
        try:
            _precan = self._load_src_module("src/at/generator/precandidate.py")
            _precan.precandidate_from_cases(
                cases_path=cases_path,
                at_tree_path=at_tree_path,
                output_path=str(candidates_path),
            )
        except Exception as exc:
            logger.warning("Precandidate skipped (debug-only): %s", exc)

        # Step 3: generate → 可执行 YAML（从 AI 映射结果生成）
        _yaml_gen = self._load_src_module("src/at/generator/yaml_generator.py")
        _yaml_gen.generate_yaml(
            cases_path=cases_input,
            mappings_path="",
            output_dir=str(suite_dir),
            app_name=self.app_name,
            at_tree_path=at_tree_path,
            assert_gate=True,
        )

        logger.info("套件已生成: %s", suite_dir)
        self._report_progress(
            f"套件已生成: {map_stats.get('cases_mapped', 0)} 个用例, "
            f"{map_stats.get('steps_mapped', 0)} 个步骤"
        )
        return str(suite_dir), map_stats

    # ------------------------------------------------------------------
    # 阶段 5：执行测试
    # ------------------------------------------------------------------

    def run_tests(self, test_dir: str, suite: str = "",
                  skip_env_check: bool = True) -> dict:
        """执行生成的测试。"""
        self._report_progress("阶段 5: 执行测试...")

        from src.at.executor.runner import run_tests

        exit_code = run_tests(
            test_dir=test_dir,
            suite=suite or None,
            skip_env_check=skip_env_check,
        )

        summary = {
            "exit_code": exit_code,
            "status": "passed" if exit_code == 0 else "failed",
        }

        logger.info("测试完成: exit_code=%d", exit_code)
        self._report_progress(
            f"测试完成: {'通过' if exit_code == 0 else '有失败'}"
        )
        return summary

    # ------------------------------------------------------------------
    # 完整管线
    # ------------------------------------------------------------------

    def run_pipeline(
        self,
        xlsx_path: str = "",
        *,
        cases: str = "",
        skip_scan: bool = False,
        skip_run: bool = False,
        skip_mapping: bool = False,
        no_display: bool = False,
    ) -> dict[str, Any]:
        """数据准备 + 生成管线：scan → dump → merge → parse → generate → run。

        AI 语义映射由智能体按 at-case-generator 完成，不在本方法内用脚本替代。

        Args:
            xlsx_path: 测试用例 xlsx/csv 文件路径。
            cases: 已存在的 cases_raw.yaml 路径（xlsx_path 为空时使用）。
            skip_scan: 跳过源码扫描（使用已有产物）。
            skip_run: 跳过执行阶段。
            skip_mapping: 跳过 AI 语义映射，使用已存在的 cases_mapped.yaml。
            no_display: 无 DISPLAY 环境，跳过运行时 dump，合成 at-tree。

        Returns:
            管线结果。
        """
        results: dict[str, Any] = {
            "status": "ok",
            "app": self.app_name,
            "output_dir": str(self.output_dir),
            "phases": {},
        }

        # ---- Phase 1: Scan ----
        if not skip_scan and self.src_dir:
            scan_stats = self.scan_source()
            results["phases"]["scan"] = scan_stats
            if scan_stats.get("status") == "error":
                results["status"] = "failed"
                return results
        else:
            results["phases"]["scan"] = {"status": "skipped"}

        # ---- Phase 2: Dump + Merge (or synthesize for no-DISPLAY) ----
        if no_display:
            at_tree_path = self._synthesize_at_tree()
            results["phases"]["build"] = {
                "status": "ok" if at_tree_path else "error",
                "at_tree": at_tree_path or "",
                "method": "synthesized",
            }
            if not at_tree_path:
                results["status"] = "failed"
                return results
        else:
            at_tree_path = self.dump_and_merge()
            results["phases"]["build"] = {
                "status": "ok" if at_tree_path else "failed",
                "at_tree": at_tree_path or "",
                "method": "runtime",
            }
            if not at_tree_path:
                results["status"] = "failed"
                return results

        # ---- Phase 3: Parse ----
        if xlsx_path:
            cases_path = self.parse_cases(
                input_path=xlsx_path,
                at_tree_path=at_tree_path,
            )
            results["phases"]["parse"] = {
                "status": "ok",
                "cases": cases_path,
            }
        elif cases:
            cases_path = cases
            results["phases"]["parse"] = {
                "status": "ok",
                "cases": cases_path,
                "source": "existing",
            }
        else:
            cases_path = ""
            results["phases"]["parse"] = {"status": "skipped", "reason": "未提供用例文件"}

        # ---- Phase 4: Generate ----
        if cases_path or skip_mapping:
            # skip_mapping=True 时，即使没有 xlsx 也生成套件（使用已存在的 cases_mapped.yaml）
            if not cases_path:
                cases_path = str(self.output_dir / "cases_mapped.yaml")
            try:
                suite_dir, gen_stats = self.generate_suite(
                    cases_path=cases_path,
                    at_tree_path=at_tree_path,
                    skip_mapping=skip_mapping,
                )
            except RuntimeError as exc:
                results["status"] = "need_ai_mapping"
                results["phases"]["generate"] = {
                    "status": "need_ai_mapping",
                    "message": str(exc),
                }
                self._report_final(str(exc))
                logger.info("管线暂停: %s", exc)
                return results
            results["phases"]["generate"] = {
                "status": "ok",
                "suite_dir": suite_dir,
                "stats": gen_stats,
            }
        else:
            results["phases"]["generate"] = {"status": "skipped"}

        # ---- Phase 5: Run ----
        if not skip_run and cases_path:
            test_summary = self.run_tests(
                test_dir=str(self.yaml_dir),
            )
            results["phases"]["run"] = test_summary
        else:
            results["phases"]["run"] = {"status": "skipped"}

        # ---- 报告 ----
        summary_str = f"管线完成: {results['status']}"
        self._report_final(summary_str)
        logger.info("管线完成: %s", json.dumps(results, ensure_ascii=False, indent=2))

        return results

    # ------------------------------------------------------------------
    # 无 DISPLAY 环境：合成 at-tree
    # ------------------------------------------------------------------

    def _synthesize_at_tree(self) -> str:
        """在无 DISPLAY 环境下，从 expected_names.yaml 和 scanned_ok.yaml 合成 at-tree。

        Returns:
            at-tree.yaml 路径，失败返回空字符串。
        """
        self._report_progress("阶段 2 (no-DISPLAY): 合成 at-tree...")

        nodes: list[dict] = []
        seen_names: set[str] = set()
        node_id = 0

        # 1. 从 spi/expected_names.yaml 读取预期元素
        expected_path = self.output_dir / "spi" / "expected_names.yaml"
        if expected_path.exists():
            try:
                import yaml
                expected_data = yaml.safe_load(expected_path.read_text(encoding="utf-8"))
                if isinstance(expected_data, dict):
                    # C++ widgets
                    for w in expected_data.get("widgets", []):
                        name = w.get("name", "") or w.get("accessibleName", "")
                        if name and name not in seen_names:
                            seen_names.add(name)
                            nodes.append({
                                "id": f"n{node_id}",
                                "name": name,
                                "role": w.get("role", "panel"),
                                "source": "expected",
                            })
                            node_id += 1
                    # QML elements
                    for q in expected_data.get("qml", []):
                        name = q.get("name", "") or q.get("accessibleName", "")
                        if name and name not in seen_names:
                            seen_names.add(name)
                            nodes.append({
                                "id": f"q{node_id}",
                                "name": name,
                                "role": "push button",
                                "source": "expected",
                            })
                            node_id += 1
            except Exception as exc:
                logger.warning("expected_names.yaml 解析失败: %s", exc)

        # 2. 从 scanned_classes.yaml 读取已命名的控件类
        # 格式：{version, type, classes: [{class_name, accessible_names, ...}, ...]}
        scanned_path = self.output_dir / "scanned_classes.yaml"
        if scanned_path.exists():
            try:
                import yaml
                scan_data = yaml.safe_load(scanned_path.read_text(encoding="utf-8"))
                if isinstance(scan_data, dict):
                    scan_classes = scan_data.get("classes", [])
                    if isinstance(scan_classes, list):
                        for doc in scan_classes:
                            if not isinstance(doc, dict):
                                continue
                            acc_names = doc.get("accessible_names", [])
                            for name in acc_names:
                                if name and name not in seen_names:
                                    seen_names.add(name)
                                    role = "panel"
                                    base = doc.get("base_classes", [])
                                    if any(b in ("DPushButton", "QPushButton", "DIconButton") for b in base):
                                        role = "push button"
                                    elif any(b in ("DSpinBox", "QSpinBox") for b in base):
                                        role = "spin button"
                                    elif any(b in ("DLineEdit", "QLineEdit") for b in base):
                                        role = "text"
                                    elif any(b in ("DTabBar", "QTabBar") for b in base):
                                        role = "page tab list"
                                    elif any(b in ("DLabel", "QLabel") for b in base):
                                        role = "label"
                                    elif any(b in ("DAbstractDialog", "QDialog") for b in base):
                                        role = "dialog"
                                    nodes.append({
                                        "id": f"s{node_id}",
                                        "name": name,
                                        "role": role,
                                        "source": "static",
                                    })
                                    node_id += 1
            except Exception as exc:
                logger.warning("scanned_classes.yaml 解析失败: %s", exc)
        # 2b. Fallback: scanned_ok.yaml (multi-doc format from `youqu at scan`)
        scanned_ok_path = self.output_dir / "scanned_ok.yaml"
        if scanned_ok_path.exists() and scanned_ok_path != scanned_path:
            try:
                import yaml
                for doc in yaml.safe_load_all(scanned_ok_path.read_text(encoding="utf-8")):
                    if not isinstance(doc, dict):
                        continue
                    acc_names = doc.get("accessible_names", [])
                    for name in acc_names:
                        if name and name not in seen_names:
                            seen_names.add(name)
                            role = "panel"
                            base = doc.get("base_classes", [])
                            if any(b in ("DPushButton", "QPushButton", "DIconButton") for b in base):
                                role = "push button"
                            elif any(b in ("DSpinBox", "QSpinBox") for b in base):
                                role = "spin button"
                            elif any(b in ("DLineEdit", "QLineEdit") for b in base):
                                role = "text"
                            elif any(b in ("DTabBar", "QTabBar") for b in base):
                                role = "page tab list"
                            elif any(b in ("DLabel", "QLabel") for b in base):
                                role = "label"
                            elif any(b in ("DAbstractDialog", "QDialog") for b in base):
                                role = "dialog"
                            nodes.append({
                                "id": f"t{node_id}",
                                "name": name,
                                "role": role,
                                "source": "static",
                            })
                            node_id += 1
            except Exception as exc:
                logger.warning("scanned_ok.yaml 解析失败: %s", exc)

        # 3. Always add the app frame itself
        if self.app_name not in seen_names:
            nodes.insert(0, {
                "id": f"f{node_id}",
                "name": self.app_name,
                "role": "frame",
                "source": "synthesized",
            })
            node_id += 1

        if not nodes:
            logger.error("无法合成 at-tree：没有 expected_names 或 scanned_classes")
            return ""

        # Write at-tree.yaml
        out_path = self.output_dir / "at-tree.yaml"
        tree_data = {
            "version": "2.0",
            "app": self.app_name,
            "tree": nodes,
            "transient_contexts": [],
        }
        try:
            import yaml
            out_path.write_text(
                yaml.dump(tree_data, allow_unicode=True, default_flow_style=False, sort_keys=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("写入 at-tree.yaml 失败: %s", exc)
            return ""

        self._report_progress(
            f"at-tree 合成完成: {len(nodes)} 个节点 (来源: expected_names + scanned_classes)"
        )
        return str(out_path)

    # ------------------------------------------------------------------
    # 辅助：快速验证
    # ------------------------------------------------------------------

    def smoke_test(self, modules_dir: str = "",
                   skip_env_check: bool = True) -> list[dict]:
        """执行烟雾测试（每模块 1 个代表用例）。"""
        from src.at.executor.runner import smoke_test_all_modules
        return smoke_test_all_modules(
            modules_dir=modules_dir or str(self.yaml_dir),
            skip_env_check=skip_env_check,
        )

    def verify_case(self, suite_yaml: str, spec_id: str,
                    skip_env_check: bool = True) -> dict:
        """验证单个用例。"""
        from src.at.executor.runner import verify_single_case
        return verify_single_case(
            suite_yaml=suite_yaml,
            spec_id=spec_id,
            skip_env_check=skip_env_check,
        )


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


def cmd_multica_agent(args) -> None:
    """CLI 入口：youqu multica-agent。"""
    agent = MulticaAgent(
        app_name=args.app,
        app_binary=getattr(args, "binary", args.app),
        app_package=getattr(args, "package", args.app),
        src_dir=getattr(args, "src", ""),
        issue_id=getattr(args, "issue_id", ""),
        report_interval=getattr(args, "report_interval", 300),
    )

    # 子命令路由
    subcommand = getattr(args, "ma_command", "pipeline")

    if subcommand == "scan":
        stats = agent.scan_source()
        print(f"扫描完成: {json.dumps(stats, ensure_ascii=False)}")
        if stats.get("status") == "error":
            sys.exit(1)

    elif subcommand == "dump":
        skip_scan = getattr(args, "skip_scan", False)
        if skip_scan:
            agent._scan_result = None
        elif getattr(args, "src", ""):
            stats = agent.scan_source()
            if stats.get("status") == "error":
                print("错误: 源码扫描失败")
                sys.exit(1)
        at_tree = agent.dump_and_merge()
        if at_tree:
            print(f"at-tree.yaml: {at_tree}")
            import yaml
            with open(at_tree, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            tree = data.get("tree", [])
            flat = []
            def _walk(nodes):
                for n in nodes:
                    flat.append(n)
                    _walk(n.get("children", []))
            _walk(tree)
            static_count = sum(1 for n in flat if n.get("source") == "static")
            runtime_count = sum(1 for n in flat if n.get("source") in ("runtime", "static+runtime"))
            print(f"  总节点: {len(flat)}")
            print(f"  运行时节点: {runtime_count}")
            print(f"  静态占位节点: {static_count}（源码中有、运行时未渲染的控件）")
        else:
            print("错误: dump+merge 失败")
            sys.exit(1)

    elif subcommand == "pipeline":
        skip_scan = getattr(args, "skip_scan", False)
        skip_run = getattr(args, "skip_run", False)
        skip_mapping = getattr(args, "skip_mapping", False)
        no_display = getattr(args, "no_display", False)
        cases_path = getattr(args, "cases", "")

        # Detect if --cases is an existing yaml (cases_raw.yaml) or xlsx
        cases_param = ""
        xlsx_param = ""
        if cases_path:
            if cases_path.endswith(".yaml") or cases_path.endswith(".yml"):
                cases_param = cases_path
            else:
                xlsx_param = cases_path

        results = agent.run_pipeline(
            xlsx_path=xlsx_param,
            cases=cases_param,
            skip_scan=skip_scan,
            skip_run=skip_run,
            skip_mapping=skip_mapping,
            no_display=no_display,
        )
        print(f"状态: {results['status']}")
        print(f"应用: {results['app']}")
        print(f"输出目录: {results['output_dir']}")
        for phase, data in results.get("phases", {}).items():
            status = data.get("status", "?")
            icon = "✓" if status == "ok" else "✗" if status == "failed" else "○"
            print(f"  {icon} {phase}: {status}")
            if status == "need_ai_mapping" and data.get("message"):
                print(f"      {data['message']}")

        build = results.get("phases", {}).get("build", {})
        if build.get("runtime_nodes", 0) > 0:
            print(f"\n  运行时节点: {build.get('runtime_nodes', 0)}")
            print(f"  静态类: {build.get('static_classes', 0)}")

        run_result = results.get("phases", {}).get("run", {})
        if run_result.get("status") in ("passed", "failed"):
            print(f"\n  测试结果: {'通过' if run_result.get('status') == 'passed' else '有失败'}"
                  f" (exit_code={run_result.get('exit_code', '?')})")

        if results["status"] != "ok":
            sys.exit(1)

    elif subcommand == "smoke":
        modules_dir = getattr(args, "modules_dir", str(agent.yaml_dir))
        result = agent.smoke_test(modules_dir=modules_dir)
        print(f"烟雾测试: {json.dumps(result, ensure_ascii=False)}")

    else:
        print(f"未知子命令: {subcommand}")
        sys.exit(1)