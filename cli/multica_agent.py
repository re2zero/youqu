#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Multica 智能体 — 自动生成 AT-SPI YAML 测试用例。

核心思路：**scan + dump + merge**，三种确定性手段保证 100% 控件覆盖。

  Pipeline:
  1. scan     — 源码扫描（Clang），提取全部 UI 控件类骨架
  2. dump     — 启动应用，dump 运行时 AT-SPI 树
  3. merge    — merge_trees() 合并，静态无运行时无法渲染的也作为占位节点加入
  4. parse    — 解析 xlsx/csv 用例为 cases_raw.yaml
  5. generate — precandidate + generate → 可执行 YAML 套件（输出到 tests/at/yaml/）
  6. run      — 执行生成的测试
  7. report   — 汇总结果

  合并策略（merge_trees 原生逻辑）：
  - 静态有 + 运行时也有 → 富化节点（class_name, object_name, accessible_id 注入）
  - 静态有 + 运行时没有 → _add_unmatched_static_nodes 作为占位节点加入
  - 静态没有 + 运行时才有 → 保留（动态创建或非 Qt 控件）

  不依赖：
  - ❌ youqu at record（事件驱动录制，Multica 环境不可用）
  - ❌ explore 乱点（不可靠，遗漏控件）
  - ❌ AI 生成的 markdown 解析（格式不固定，有遗漏风险）
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

    # ------------------------------------------------------------------
    # 阶段 4：生成套件
    # ------------------------------------------------------------------

    def generate_suite(self, cases_path: str, at_tree_path: str,
                       output_dir: str = "") -> tuple[str, dict]:
        """生成可执行 YAML 测试套件。

        Args:
            cases_path: cases_raw.yaml 路径。
            at_tree_path: at-tree.yaml 路径。
            output_dir: 套件输出目录（默认 tests/at/yaml/）。

        Returns:
            (suite_dir, stats)
        """
        self._report_progress("阶段 4: 生成 YAML 测试套件...")

        suite_dir = Path(output_dir) if output_dir else \
            self.yaml_dir
        suite_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: tree-info → 精简 at-tree（输出到 tests/at/ 级别）
        tree_info_path = self.output_dir / "at-tree-compact.yaml"
        from src.at.generator.case_parser import compact_at_tree_to_file
        compact_at_tree_to_file(
            at_tree_path=at_tree_path,
            output_path=str(tree_info_path),
            fmt="yaml",
        )

        # Step 2: precandidate → 候选元素匹配（输出到 tests/at/ 级别）
        candidates_path = self.output_dir / "suite-cases.yaml"
        from src.at.generator.precandidate import precandidate_from_cases
        stats = precandidate_from_cases(
            cases_path=cases_path,
            at_tree_path=at_tree_path,
            output_path=str(candidates_path),
        )

        # Step 3: generate → 可执行 YAML（输出到 tests/at/yaml/）
        from src.at.generator.yaml_generator import generate_yaml
        generate_yaml(
            cases_path=str(candidates_path),
            mappings_path="",
            output_dir=str(suite_dir),
            app_name=self.app_name,
            at_tree_path=at_tree_path,
            assert_gate=True,
        )

        logger.info("套件已生成: %s", suite_dir)
        self._report_progress(
            f"套件已生成: {stats.get('cases', 0)} 个用例, "
            f"{stats.get('steps', 0)} 个步骤"
        )
        return str(suite_dir), stats

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
        skip_scan: bool = False,
        skip_run: bool = False,
    ) -> dict[str, Any]:
        """完整管线：scan → dump → merge → parse → generate → run。

        Args:
            xlsx_path: 测试用例 xlsx/csv 文件路径。
            skip_scan: 跳过源码扫描（使用已有产物）。
            skip_run: 跳过执行阶段。

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

        # ---- Phase 2: Dump + Merge ----
        at_tree_path = self.dump_and_merge()
        results["phases"]["build"] = {
            "status": "ok" if at_tree_path else "failed",
            "at_tree": at_tree_path,
            "runtime_nodes": len(self._runtime_tree),
            "static_classes": len(self._scan_result.classes)
            if self._scan_result else 0,
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
        else:
            results["phases"]["parse"] = {"status": "skipped", "reason": "未提供用例文件"}

        # ---- Phase 4: Generate ----
        if xlsx_path:
            suite_dir, gen_stats = self.generate_suite(
                cases_path=cases_path,
                at_tree_path=at_tree_path,
            )
            results["phases"]["generate"] = {
                "status": "ok",
                "suite_dir": suite_dir,
                "stats": gen_stats,
            }
        else:
            results["phases"]["generate"] = {"status": "skipped"}

        # ---- Phase 5: Run ----
        if not skip_run and xlsx_path:
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
        at_tree = agent.dump_and_merge()
        if at_tree:
            print(f"at-tree.yaml: {at_tree}")
            # 统计节点
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
        xlsx_path = getattr(args, "cases", "")

        results = agent.run_pipeline(
            xlsx_path=xlsx_path,
            skip_scan=skip_scan,
            skip_run=skip_run,
        )

        print(f"\n=== Multica 智能体管线结果 ===")
        print(f"状态: {results['status']}")
        print(f"应用: {results['app']}")
        print(f"输出目录: {results['output_dir']}")
        for phase, data in results.get("phases", {}).items():
            status = data.get("status", "?")
            icon = "✓" if status == "ok" else "✗" if status == "failed" else "○"
            print(f"  {icon} {phase}: {status}")

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