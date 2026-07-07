# SPDX-FileCopyrightText: 2026 UnionTech Software Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

_src_root = Path(__file__).resolve().parent.parent / "src"
if str(_src_root) not in sys.path:
    sys.path.insert(0, str(_src_root))
stub = sys.modules.get("src")
if stub is not None and getattr(stub, "__spec__", None) is None:
    sys.modules["src"] = types.ModuleType("src")
    sys.modules["src"].__path__ = [str(_src_root)]
    sys.modules["src"].__package__ = "src"
    sys.modules["src"].__file__ = str(_src_root / "__init__.py")

if "pyatspi" not in sys.modules:
    sys.modules["pyatspi"] = MagicMock()


class TestIsAvailable:

    def test_returns_false_without_clang(self):
        import src.at.scanner.clang_scanner as mod
        with patch.dict(sys.modules, {"clang": None, "clang.cindex": None}):
            mod._is_available.cache_clear() if hasattr(mod._is_available, "cache_clear") else None
            assert mod._is_available() is False

    def test_returns_true_with_clang(self):
        import src.at.scanner.clang_scanner as mod
        mock_cindex = MagicMock()
        with patch.dict(sys.modules, {"clang": MagicMock(), "clang.cindex": mock_cindex}):
            assert mod._is_available() is True


class TestFindLibclangPath:

    def test_finds_existing_library(self, tmp_path, monkeypatch):
        lib_dir = tmp_path / "llvm-17" / "lib"
        lib_dir.mkdir(parents=True)
        (lib_dir / "libclang.so").write_text("fake")

        import src.at.scanner.clang_scanner as mod
        result = mod._find_libclang_path()
        assert result is not None
        assert result.endswith("libclang.so")


class TestExtractUiClasses:

    def test_extracts_widget_class_with_object_name(self):
        import src.at.scanner.clang_scanner as mod

        with patch.dict(sys.modules, {"clang": MagicMock(), "clang.cindex": MagicMock()}):
            from clang.cindex import CursorKind as CK

            node = MagicMock()
            node.kind = CK.CLASS_DECL
            node.location.file.name = "/test/main.cpp"
            node.is_definition.return_value = True
            node.spelling = "MainWindow"

            base_spec = MagicMock()
            base_spec.kind = CK.CXX_BASE_SPECIFIER
            base_spec.spelling = "QWidget"

            method = MagicMock()
            method.kind = CK.CXX_METHOD
            method.spelling = "setObjectName"
            call = MagicMock()
            call.kind = CK.CALL_EXPR
            literal = MagicMock()
            literal.kind = CK.STRING_LITERAL
            literal.spelling = '"mainWindow"'
            call.get_children.return_value = [literal]
            method.get_children.return_value = [call]

            node.get_children.return_value = [base_spec, method]

            root = MagicMock()
            root.walk_preorder.return_value = [node]
            mock_tu = MagicMock()
            mock_tu.cursor = root

            result = mod._extract_ui_classes(mock_tu, "/test/main.cpp")
            assert len(result) == 1
            assert result[0]["class_name"] == "MainWindow"
            assert result[0]["base_classes"] == ["QWidget"]
            assert result[0]["object_names"] == ["mainWindow"]

    def test_skips_non_definition(self):
        import src.at.scanner.clang_scanner as mod

        with patch.dict(sys.modules, {"clang": MagicMock(), "clang.cindex": MagicMock()}):
            from clang.cindex import CursorKind as CK

            node = MagicMock()
            node.kind = CK.CLASS_DECL
            node.location.file.name = "/test/forward.h"
            node.is_definition.return_value = False
            node.spelling = "ForwardDecl"

            root = MagicMock()
            root.walk_preorder.return_value = [node]
            mock_tu = MagicMock()
            mock_tu.cursor = root

            result = mod._extract_ui_classes(mock_tu, "/test/forward.h")
            assert result == []


class TestScanSourceDir:

    def test_returns_empty_when_clang_unavailable(self):
        import src.at.scanner.clang_scanner as mod

        with patch.object(mod, "_is_available", return_value=False):
            result = mod.scan_source_dir("/some/dir")
            assert result == []

    def test_returns_empty_for_nonexistent_dir(self):
        import src.at.scanner.clang_scanner as mod

        with patch.object(mod, "_is_available", return_value=True), \
             patch.object(mod, "_init_clang") as mock_init:
            result = mod.scan_source_dir("/nonexistent/path")
            assert result == []

    def test_scans_cpp_files(self, tmp_path):
        import src.at.scanner.clang_scanner as mod

        (tmp_path / "widget.cpp").write_text("// test")
        (tmp_path / "readme.txt").write_text("ignore me")

        mock_index = MagicMock()
        with patch.object(mod, "_is_available", return_value=True), \
             patch.object(mod, "_init_clang", return_value=mock_index), \
             patch.object(mod, "_scan_file", return_value=[{"class_name": "W"}]):
            result = mod.scan_source_dir(str(tmp_path))
            assert len(result) == 1
