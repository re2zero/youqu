#!/usr/bin/env python3
"""libclang bootstrap — single source of truth for locating & configuring libclang.

Shared by scan_gaps.py (configures BEFORE importing clang.cindex) and
coverage_stats.py (env-check report). Keeps libclang resolution out of the two
scanners so a fix lands in ONE place instead of being re-patched per run
(see the two scan logs: the old candidate list lived in both scripts and was
patched independently, so fixing one never fixed the other).

Resolution priority (high → low):
  1. $LIBCLANG_LIBRARY_FILE   — path to a specific libclang*.so
  2. $LIBCLANG_LIBRARY_PATH   — dir containing libclang*.so
  3. ldconfig -p              — system library cache
  4. user-local + system dirs — ~/.local/lib, ~/clanglib, /usr/lib/llvm-*/lib ...
  5. pip install libclang     — self-contained fallback (bundles
                                clang/native/libclang.so); sudo-free, needs only
                                Python + network.

Call ensure_libclang() BEFORE `from clang.cindex import ...` so that
Config.set_library_file()/set_library_path() takes effect before the library is
first loaded.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ENV_FILE = "LIBCLANG_LIBRARY_FILE"
ENV_DIR = "LIBCLANG_LIBRARY_PATH"

# User-local dirs that commonly hold a hand-installed libclang.
_USER_LOCAL_DIRS = [
    str(Path.home() / ".local" / "lib"),
    str(Path.home() / ".local" / "lib64"),
    str(Path.home() / ".local" / "share"),
    str(Path.home() / "clanglib"),
]

# System dirs: arch multiarch + per-LLVM-version install trees.
_SYSTEM_DIRS = [
    "/usr/lib/x86_64-linux-gnu",
    "/usr/lib64",
    "/usr/lib",
    "/usr/lib/llvm-18/lib",
    "/usr/lib/llvm-17/lib",
    "/usr/lib/llvm-19/lib",
    "/usr/lib/llvm-16/lib",
]


class LibclangResult:
    """Outcome of a libclang resolution attempt."""

    def __init__(self, found: bool, libfile: str | None, libpath: str | None, source: str):
        self.found = found
        self.libfile = libfile          # specific .so path, or None
        self.libpath = libpath          # directory, or None
        self.source = source            # env / ldconfig / user-local/system / pip / not-found

    def display(self) -> str:
        return self.libfile or self.libpath or ""


def _is_libclang_so(name: str) -> bool:
    """True for a libclang shared object: libclang*.so*, excluding libclang-cpp.

    Robust to versioned suffixes (.so, .so.1, .so.17). The old check
    `Path.suffix in (".so", ".so.1")` missed every versioned name because
    Path.suffix returns only the last component (`.17`, `.1`), so a system
    `libclang-17.so.17` was never matched — the root cause of the second
    scan log even though the library was installed.
    """
    return name.startswith("libclang") and ".so" in name and "cpp" not in name


def _find_so_in_dir(directory: str) -> str | None:
    try:
        for f in sorted(Path(directory).iterdir()):
            if f.is_file() and _is_libclang_so(f.name):
                return str(f)
    except OSError:
        pass
    return None


def _via_ldconfig() -> str | None:
    """Find libclang in the system library cache. Returns None if ldconfig is
    unavailable or the command fails — silently, so we fall through to dirs."""
    exe = shutil.which("ldconfig")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "-p"], capture_output=True, text=True,
                             timeout=10, check=False).stdout
    except OSError:
        return None
    for line in out.splitlines():
        idx = line.find("=>")
        if idx == -1:
            continue
        path = line[idx + 2:].strip()
        if _is_libclang_so(Path(path).name):
            return path
    return None


def _resolve_from_env() -> LibclangResult | None:
    f = os.environ.get(ENV_FILE)
    if f:
        if Path(f).is_file():
            return LibclangResult(True, f, None, ENV_FILE)
        # Explicitly set but invalid: fail loudly instead of silently falling
        # through — a user who set the var wants THAT library, not whatever
        # the system happens to have. resolve_libclang() short-circuits on this.
        return LibclangResult(False, None, None, ENV_FILE)
    d = os.environ.get(ENV_DIR)
    if d:
        if Path(d).is_dir():
            so = _find_so_in_dir(d)
            if so:
                return LibclangResult(True, so, None, ENV_DIR)
        # Missing dir, or present but no libclang*.so inside: explicit failure
        # (see note above — env vars are authoritative when set).
        return LibclangResult(False, None, None, ENV_DIR)
    return None


def _resolve_from_dirs() -> LibclangResult | None:
    for d in _USER_LOCAL_DIRS + _SYSTEM_DIRS:
        so = _find_so_in_dir(d)
        if so:
            return LibclangResult(True, so, None, "user-local/system")
    return None


def _pip_install_libclang() -> str | None:
    """Best-effort `pip install libclang`; return the bundled .so path or None.

    The libclang PyPI wheel ships clang/native/libclang.so alongside the
    clang.cindex binding, so one install satisfies both dependencies without
    sudo or system packages. Survives PEP 668 (externally-managed) by trying
    --user then --break-system-packages. Skipped when $LIBCLANG_NO_PIP.
    """
    if os.environ.get("LIBCLANG_NO_PIP"):
        return None
    installed = False
    for extra in (["--user"], ["--break-system-packages"], []):
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet",
                 "--disable-pip-version-check", *extra, "libclang"],
                capture_output=True, text=True, timeout=240, check=False,
            )
            if r.returncode == 0:
                installed = True
                break
        except (OSError, subprocess.SubprocessError):
            continue
    if not installed:
        return None
    return _find_bundled_libclang()


def _find_bundled_libclang() -> str | None:
    """Locate the bundled clang/native/libclang.so* after a pip install.

    Works regardless of which `clang` binding ends up importable: we only need
    the .so path, because _configure_clang() forces it via set_library_file().
    """
    native_dirs: list[Path] = []
    try:
        import clang  # noqa: F401
        native_dirs.append(Path(clang.__file__).parent / "native")
    except Exception:
        pass
    try:
        import site
        for d in site.getsitepackages():
            native_dirs.append(Path(d) / "clang" / "native")
        _user = site.getusersitepackages()
        if _user:
            native_dirs.append(Path(_user) / "clang" / "native")
    except Exception:
        pass
    for n in native_dirs:
        try:
            for cand in sorted(Path(n).glob("libclang.so*")):
                if cand.is_file():
                    return str(cand)
        except OSError:
            pass
    return None


def resolve_libclang() -> LibclangResult:
    """Read-only detection (env → ldconfig → dirs). No pip, no side effects."""
    hit = _resolve_from_env()
    if hit:
        return hit
    ld = _via_ldconfig()
    if ld:
        return LibclangResult(True, ld, None, "ldconfig")
    hit = _resolve_from_dirs()
    if hit:
        return hit
    return LibclangResult(False, None, None, "not-found")


def _configure_clang(result: LibclangResult) -> None:
    """Apply the resolved path to clang.cindex.Config. Safe to call before import."""
    try:
        from clang.cindex import Config
    except Exception:
        return
    if result.libfile:
        try:
            Config.set_library_file(result.libfile)
            return
        except Exception:
            pass
    if result.libpath:
        key = "LD_LIBRARY_PATH"
        old = os.environ.get(key, "")
        if result.libpath not in old:
            os.environ[key] = f"{result.libpath}:{old}" if old else result.libpath
        try:
            Config.set_library_path(result.libpath)
        except Exception:
            pass


_PIP_BOOTSTRAPPED = False  # True once pip supplied the binding + .so pair


def _binding_importable() -> bool:
    """True if clang.cindex (the Python binding) imports cleanly."""
    try:
        import clang.cindex  # noqa: F401
        return True
    except Exception:
        return False


def ensure_libclang() -> LibclangResult:
    """Resolve libclang (.so + Python binding), self-healing via pip.

    Idempotent: re-resolving an already-resolved environment is cheap and
    re-applying the config is a no-op. Returns the resolution result so callers
    can report exactly where the library came from.

    Behavior:
    - .so resolution: env (authoritative when set) -> ldconfig -> dirs.
    - If anything is missing (no .so, or the Python binding won't import),
      `pip install libclang` provides a MATCHED binding + .so pair in one wheel
      (sudo-free, PEP 668-aware) — unless an env var named a specific library,
      in which case that .so is kept and only the binding is installed.
    - Once pip has bootstrapped, later calls keep using its matched .so (a
      system .so can mismatch the pip binding's expected symbols).
    - An explicitly-set-but-invalid env var stays a HARD failure: no fallback,
      because silently substituting another library would mask a typo or a
      stale path.
    """
    global _PIP_BOOTSTRAPPED
    if _PIP_BOOTSTRAPPED and not os.environ.get(ENV_FILE) and not os.environ.get(ENV_DIR):
        bundled = _find_bundled_libclang()
        if bundled:
            result = LibclangResult(True, bundled, None, "pip:libclang")
            _configure_clang(result)
            return result
    result = resolve_libclang()
    if result.found and _binding_importable():
        _configure_clang(result)
        return result
    if result.source in (ENV_FILE, ENV_DIR):
        # Env var is authoritative: honor the chosen .so. If only the binding
        # is missing, pip supplies it without swapping the library.
        if result.found and not _binding_importable():
            _pip_install_libclang()
        if result.found and _binding_importable():
            _configure_clang(result)
            return result
        return result  # invalid env path, or binding still unavailable
    # Nothing authoritative: pip install yields a matched binding + .so pair.
    pip_so = _pip_install_libclang()
    if pip_so:
        _PIP_BOOTSTRAPPED = True
        result = LibclangResult(True, pip_so, None, "pip:libclang")
        _configure_clang(result)
        return result
    if result.found:
        return LibclangResult(False, result.libfile, result.libpath, "binding-missing")
    return result
