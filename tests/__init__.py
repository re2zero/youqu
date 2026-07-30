import importlib.util as _ilu
import os
import sys
import types as _types
from pathlib import Path
from unittest.mock import MagicMock

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def _install_mock_module(name, submodules=None):
    mod = MagicMock()
    sys.modules[name] = mod
    if submodules:
        for sub in submodules:
            sys.modules["{}.{}".format(name, sub)] = getattr(mod, sub, MagicMock())
    return mod


_install_mock_module("funnylog", ["conf", "conf.setting", "log"])
_install_mock_module("allure", ["commons", "pytest", "python_commons"])
_install_mock_module("letmego")
_install_mock_module("xdo")
_install_mock_module("ydotool")
_install_mock_module("dogtail", ["tree", "rawinput", "utils"])
_install_mock_module("pywinauto")
_install_mock_module("paddleocr")
_install_mock_module("fastmcp")
_install_mock_module("pyscreenshot")
_install_mock_module("sniff")
_install_mock_module("xdotool")
_install_mock_module("pdocr_rpc")
_install_mock_module("gi", ["repository", "repository.Atspi", "repository.Gdk"])
_install_mock_module("libdtkwmjack")
_install_mock_module("setting", ["globalconfig"])
import configparser as _cp

_real_cfg = _cp.RawConfigParser()
_real_cfg.read(str(_project_root / "setting" / "globalconfig.ini"), encoding="utf-8")


class _MockGetCfg:
    def __init__(self, config_file, option=None):
        self.option = option
        self.conf = _real_cfg

    def get(self, key, op=None, default=None):
        if op is None:
            op = self.option
        return self.conf.get(op, key, fallback=default)

    def get_bool(self, key, op=None, default=False):
        if op is None:
            op = self.option
        return self.conf.getboolean(op, key, fallback=default)


sys.modules["setting.globalconfig"].GetCfg = _MockGetCfg
sys.modules["setting.globalconfig"].GlobalConfig.GLOBAL_CONFIG_FILE_PATH = str(
    _project_root / "setting" / "globalconfig.ini"
)

sys.modules["src"] = MagicMock()
for mod in [
    "assert_common", "ocr_utils", "cmdctl", "mouse_key",
    "dogtail_utils", "button_center", "dbus_utils", "requestx",
    "image_utils", "short_cut", "calculate", "webui",
]:
    sys.modules["src.{}".format(mod)] = MagicMock()

os.environ.setdefault("DISPLAY", ":0")

import types as _types

_vlm_pkg = _types.ModuleType("src.vlm")
_vlm_pkg.__path__ = [str(_project_root / "src" / "vlm")]
_vlm_pkg.__package__ = "src.vlm"
_vlm_pkg.__file__ = str(_project_root / "src" / "vlm" / "__init__.py")
sys.modules["src.vlm"] = _vlm_pkg

_src_vlm = _project_root / "src" / "vlm"
_load_order = ["config", "screenshot", "vlm_locator", "vlm_executor", "vlm_agent"]
for fname in _load_order:
    fpath = _src_vlm / "{}.py".format(fname)
    spec = _ilu.spec_from_file_location("src.vlm.{}".format(fname), str(fpath))
    mod = _ilu.module_from_spec(spec)
    mod.__package__ = "src.vlm"
    sys.modules["src.vlm.{}".format(fname)] = mod
    spec.loader.exec_module(mod)
    setattr(_vlm_pkg, fname, mod)

_mcp_path = _project_root / "src" / "mcp" / "server.py"
_mcp_spec = _ilu.spec_from_file_location("src.mcp.server", str(_mcp_path))
_mcp_mod = _ilu.module_from_spec(_mcp_spec)
sys.modules["src.mcp.server"] = _mcp_mod
_mcp_spec.loader.exec_module(_mcp_mod)

_jobs_path = _project_root / "src" / "mcp" / "jobs.py"
_jobs_spec = _ilu.spec_from_file_location("src.mcp.jobs", str(_jobs_path))
_jobs_mod = _ilu.module_from_spec(_jobs_spec)
sys.modules["src.mcp.jobs"] = _jobs_mod
_jobs_spec.loader.exec_module(_jobs_mod)

_cli_pkg = _types.ModuleType("cli")
_cli_pkg.__path__ = [str(_project_root / "cli")]
_cli_pkg.__package__ = "cli"
_cli_pkg.__file__ = str(_project_root / "cli" / "__init__.py")
sys.modules["cli"] = _cli_pkg
