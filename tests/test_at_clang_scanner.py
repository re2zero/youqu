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

            constructor = MagicMock()
            constructor.kind = CK.CONSTRUCTOR
            constructor.location.file.name = "/test/main.cpp"
            constructor.semantic_parent.spelling = "MainWindow"
            compound = MagicMock()
            compound.kind = CK.COMPOUND_STMT
            call = MagicMock()
            call.kind = CK.CALL_EXPR
            call.spelling = "setObjectName"
            literal = MagicMock()
            literal.kind = CK.STRING_LITERAL
            literal.spelling = '"mainWindow"'
            literal.get_children.return_value = []
            call.get_children.return_value = [literal]
            compound.get_children.return_value = [call]
            constructor.get_children.return_value = [compound]

            node.get_children.return_value = [base_spec, constructor]

            root = MagicMock()
            root.walk_preorder.return_value = [node, constructor]
            mock_tu = MagicMock()
            mock_tu.cursor = root

            result = mod._extract_ui_classes(mock_tu, "main.cpp")
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
            assert result.classes == []
            assert result.stats["total_files"] == 0

    def test_returns_empty_for_nonexistent_dir(self):
        import src.at.scanner.clang_scanner as mod

        with (
            patch.object(mod, "_is_available", return_value=True),
            patch.object(mod, "_init_clang") as mock_init,
        ):
            result = mod.scan_source_dir("/nonexistent/path")
            assert result.classes == []
            assert result.stats["total_files"] == 0

    def test_scans_cpp_files(self, tmp_path):
        import src.at.scanner.clang_scanner as mod

        (tmp_path / "widget.cpp").write_text("// test")
        (tmp_path / "readme.txt").write_text("ignore me")

        mock_index = MagicMock()
        with (
            patch.object(mod, "_is_available", return_value=True),
            patch.object(mod, "_init_clang", return_value=mock_index),
            patch.object(mod, "_scan_file", return_value=([{"class_name": "W"}], None)),
        ):
            result = mod.scan_source_dir(str(tmp_path))
            assert len(result.classes) == 1
            assert result.stats["total_files"] == 1

    def test_progress_cb_called_for_each_file(self, tmp_path):
        import src.at.scanner.clang_scanner as mod

        (tmp_path / "a.cpp").write_text("")
        (tmp_path / "b.cpp").write_text("")
        (tmp_path / "c.cpp").write_text("")

        calls = []
        mock_index = MagicMock()
        with (
            patch.object(mod, "_is_available", return_value=True),
            patch.object(mod, "_init_clang", return_value=mock_index),
            patch.object(mod, "_scan_file", return_value=([], None)),
        ):
            mod.scan_source_dir(
                str(tmp_path), progress_cb=lambda i, t, fp: calls.append((i, t, fp))
            )

        assert len(calls) == 3
        assert calls[0][1] == 3  # total
        assert calls[2][0] == 2  # last index (0-based)

    def test_scan_file_returns_error_on_exception(self):
        import src.at.scanner.clang_scanner as mod

        mock_index = MagicMock()
        mock_index.parse.side_effect = RuntimeError("clang crashed")

        with (
            patch.object(mod, "_is_available", return_value=True),
            patch.object(mod, "_init_clang", return_value=mock_index),
        ):
            classes, error = mod._scan_file(mock_index, "/bad/file.cpp", "file.cpp", [])
            assert classes == []
            assert "RuntimeError" in error

    def test_skips_test_directories_and_files(self, tmp_path):
        import src.at.scanner.clang_scanner as mod

        # Should be scanned
        (tmp_path / "widget.cpp").write_text("")
        (tmp_path / "src" / "panel.h").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "src" / "panel.h").write_text("")

        # Should be skipped: test dirs, autotest dirs, test_ prefix files
        (tmp_path / "tests" / "test_widget.cpp").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "tests" / "test_widget.cpp").write_text("")
        (tmp_path / "autotests" / "ut_case.h").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "autotests" / "ut_case.h").write_text("")
        (tmp_path / "test_main.cpp").write_text("")
        (tmp_path / "test" / "helper.cpp").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "test" / "helper.cpp").write_text("")

        mock_index = MagicMock()
        with (
            patch.object(mod, "_is_available", return_value=True),
            patch.object(mod, "_init_clang", return_value=mock_index),
            patch.object(mod, "_scan_file", return_value=([], None)),
        ):
            result = mod.scan_source_dir(str(tmp_path))
            assert result.stats["total_files"] == 2

    def test_skips_moc_and_ui_generated_files(self, tmp_path):
        import src.at.scanner.clang_scanner as mod

        (tmp_path / "widget.cpp").write_text("")
        (tmp_path / "moc_widget.cpp").write_text("")
        (tmp_path / "ui_widget.h").write_text("")

        mock_index = MagicMock()
        with (
            patch.object(mod, "_is_available", return_value=True),
            patch.object(mod, "_init_clang", return_value=mock_index),
            patch.object(mod, "_scan_file", return_value=([], None)),
        ):
            result = mod.scan_source_dir(str(tmp_path))
            assert result.stats["total_files"] == 1

    def test_include_dirs_filters_to_subdirectories(self, tmp_path):
        import src.at.scanner.clang_scanner as mod

        (tmp_path / "src" / "widget.cpp").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "src" / "widget.cpp").write_text("")
        (tmp_path / "plugins" / "plugin.cpp").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "plugins" / "plugin.cpp").write_text("")
        (tmp_path / "tests" / "test.cpp").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "tests" / "test.cpp").write_text("")

        mock_index = MagicMock()
        with (
            patch.object(mod, "_is_available", return_value=True),
            patch.object(mod, "_init_clang", return_value=mock_index),
            patch.object(mod, "_scan_file", return_value=([], None)),
        ):
            result = mod.scan_source_dir(str(tmp_path), include_dirs=["src"])
            assert result.stats["total_files"] == 1

            result = mod.scan_source_dir(str(tmp_path), include_dirs=["src", "plugins"])
            assert result.stats["total_files"] == 2

    def test_extracts_setAccessibleName_from_constructor_body(self):
        import src.at.scanner.clang_scanner as mod

        with patch.dict(sys.modules, {"clang": MagicMock(), "clang.cindex": MagicMock()}):
            from clang.cindex import CursorKind as CK


            node = MagicMock()
            node.kind = CK.CLASS_DECL
            node.location.file.name = "titlebar.cpp"
            node.is_definition.return_value = True
            node.spelling = "Titlebar"

            base_spec = MagicMock()
            base_spec.kind = CK.CXX_BASE_SPECIFIER
            base_spec.spelling = "QFrame"

            constructor = MagicMock()
            constructor.kind = CK.CONSTRUCTOR
            constructor.location.file.name = "titlebar.cpp"
            constructor.semantic_parent.spelling = "Titlebar"
            compound = MagicMock()
            compound.kind = CK.COMPOUND_STMT
            call = MagicMock()
            call.kind = CK.CALL_EXPR
            call.spelling = "setAccessibleName"
            literal = MagicMock()
            literal.kind = CK.STRING_LITERAL
            literal.spelling = '"DMainWindowTitlebar"'
            literal.get_children.return_value = []
            call.get_children.return_value = [literal]
            compound.get_children.return_value = [call]
            constructor.get_children.return_value = [compound]

            node.get_children.return_value = [base_spec, constructor]

            root = MagicMock()
            root.walk_preorder.return_value = [node, constructor]
            mock_tu = MagicMock()
            mock_tu.cursor = root

            result = mod._extract_ui_classes(mock_tu, "titlebar.cpp")
            assert len(result) == 1
            assert result[0]["accessible_names"] == ["DMainWindowTitlebar"]

    def test_extracts_dtk_instantiation_nested_in_if_block(self):
        import src.at.scanner.clang_scanner as mod

        with patch.dict(sys.modules, {"clang": MagicMock(), "clang.cindex": MagicMock()}):
            from clang.cindex import CursorKind as CK


            node = MagicMock()
            node.kind = CK.CLASS_DECL
            node.location.file.name = "panel.cpp"
            node.is_definition.return_value = True
            node.spelling = "Panel"

            base_spec = MagicMock()
            base_spec.kind = CK.CXX_BASE_SPECIFIER
            base_spec.spelling = "QWidget"

            method = MagicMock()
            method.kind = CK.CXX_METHOD
            method.location.file.name = "panel.cpp"
            method.semantic_parent.spelling = "Panel"
            if_stmt = MagicMock()
            if_stmt.kind = CK.IF_STMT
            compound = MagicMock()
            compound.kind = CK.COMPOUND_STMT
            new_expr = MagicMock()
            new_expr.kind = CK.CXX_NEW_EXPR
            new_expr.spelling = "DPushButton"
            compound.get_children.return_value = [new_expr]
            if_stmt.get_children.return_value = [compound]
            method.get_children.return_value = [if_stmt]

            node.get_children.return_value = [base_spec, method]

            root = MagicMock()
            root.walk_preorder.return_value = [node, method]
            mock_tu = MagicMock()
            mock_tu.cursor = root

            result = mod._extract_ui_classes(mock_tu, "panel.cpp")
            assert len(result) == 1
            assert result[0]["dtk_instantiations"] == ["DPushButton"]

    def test_source_file_uses_relative_path(self, tmp_path):
        import src.at.scanner.clang_scanner as mod

        (tmp_path / "widgets" / "button.cpp").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "widgets" / "button.cpp").write_text("")

        captured = {}

        def mock_scan(index, file_path, source_file, extra_args):
            captured["file_path"] = file_path
            captured["source_file"] = source_file
            return [{"class_name": "Btn"}], None

        mock_index = MagicMock()
        with (
            patch.object(mod, "_is_available", return_value=True),
            patch.object(mod, "_init_clang", return_value=mock_index),
            patch.object(mod, "_scan_file", side_effect=mock_scan),
        ):
            mod.scan_source_dir(str(tmp_path))

        assert captured["source_file"] == "widgets/button.cpp"
        assert captured["file_path"] == str(tmp_path / "widgets" / "button.cpp")
