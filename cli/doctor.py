# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

import getpass
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run():
    _Doctor().run()


class _Doctor:

    def __init__(self):
        self._password = None
        self._checked = 0
        self._failed = 0
        self._fixed = 0

    def run(self):
        print("YouQu Doctor")

        self._check_pydantic()
        self._check_pyatspi()
        self._check_atspi_typelib()
        self._check_scrot()
        self._check_opencv()
        self._check_display()
        self._check_xauthority()
        self._check_accessibility()
        self._check_libclang()
        self._check_java()
        self._check_skills()

        print()
        if self._failed:
            print(
                f"{self._checked} checked, {self._failed} failed, "
                f"{self._fixed} fixed, {self._failed - self._fixed} unresolved"
            )
            sys.exit(1)
        else:
            print(f"{self._checked} checked, all OK")

    # ── sudo ──────────────────────────────────────────────────────────

    def _ensure_password(self):
        if self._password is not None:
            return self._password
        if os.geteuid() == 0:
            self._password = ""
            return self._password
        try:
            from setting import conf  # noqa: PLC0415
            pwd = getattr(conf, "PASSWORD", None)
            if pwd and pwd != "1":
                self._password = pwd
                return self._password
        except Exception:
            pass
        try:
            self._password = getpass.getpass("sudo password: ")
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(1)
        return self._password

    def _sudo(self, *args):
        pwd = self._ensure_password()
        return subprocess.run(
            ["sudo", "-S"] + list(args),
            input=pwd + "\n",
            text=True,
            capture_output=True,
        )

    # ── checks ────────────────────────────────────────────────────────

    def _ok(self, msg):
        self._checked += 1
        print(f"  [\033[32mOK\033[0m] {msg}")

    def _fail(self, msg):
        self._checked += 1
        self._failed += 1
        print(f"  [\033[31m!!\033[0m] {msg}")

    def _fixed_msg(self, msg):
        self._fixed += 1
        print(f"       \033[33m→ {msg}\033[0m")

    # ── pydantic ──────────────────────────────────────────────────────

    def _check_pydantic(self):
        if importlib.util.find_spec("pydantic"):
            self._ok("pydantic")
            return
        self._fail("pydantic missing")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "pydantic", "--break-system-packages"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            self._fixed_msg("pip install pydantic")
        else:
            print(f"       pip install failed: {result.stderr.strip()[-200:]}")

    # ── pyatspi ───────────────────────────────────────────────────────

    def _check_pyatspi(self):
        if importlib.util.find_spec("pyatspi"):
            self._ok("pyatspi")
            return
        self._fail("pyatspi missing — fixing")

        # Strategy 1: apt install (may be blocked by gir1.2-atspi-2.0 Breaks)
        result = self._sudo("apt", "install", "-y", "python3-pyatspi")
        if result.returncode == 0:
            self._fixed_msg("apt install python3-pyatspi")
            return

        stderr = result.stderr
        if "破坏" in stderr or "Breaks" in stderr or "未满足" in stderr:
            # Strategy 2: download + extract to site-packages
            if self._install_pyatspi_from_deb():
                self._fixed_msg("apt download + extract python3-pyatspi")
                return

        print(f"       all strategies failed: {stderr.strip()[-200:]}")

    def _install_pyatspi_from_deb(self):
        import sysconfig

        site = Path(sysconfig.get_paths()["purelib"])
        need_sudo = not os.access(site, os.W_OK)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            # Step 1: download the deb (no sudo needed)
            dl = subprocess.run(
                ["apt", "download", "python3-pyatspi"],
                cwd=str(tmp),
                capture_output=True,
                text=True,
            )
            if dl.returncode != 0:
                print(f"       apt download failed: {dl.stderr.strip()[-200:]}")
                return False

            debs = list(tmp.glob("python3-pyatspi*.deb"))
            if not debs:
                return False

            # Step 2: extract
            try:
                subprocess.run(
                    ["dpkg", "-x", str(debs[0]), "extracted"],
                    cwd=str(tmp),
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError as e:
                print(f"       dpkg extract failed: {e.stderr.strip()[-200:]}")
                return False

            src = tmp / "extracted" / "usr" / "lib" / "python3" / "dist-packages"

            # Step 3: copy pyatspi and Accessibility to site-packages
            ok = True
            for mod in ("pyatspi", "Accessibility"):
                src_mod = src / mod
                if not src_mod.exists():
                    continue
                dst_mod = site / mod
                if dst_mod.exists():
                    shutil.rmtree(dst_mod)
                if need_sudo:
                    r = self._sudo("cp", "-r", str(src_mod), str(site))
                    if r.returncode != 0:
                        ok = False
                else:
                    shutil.copytree(src_mod, dst_mod)

            # Verify
            if ok:
                try:
                    spec = importlib.util.find_spec("pyatspi")
                    if spec:
                        return True
                except Exception:
                    pass
        return False

    # ── gir1.2-atspi-2.0 ──────────────────────────────────────────────

    def _check_atspi_typelib(self):
        try:
            import gi
            gi.require_version("Atspi", "2.0")
            self._ok("gir1.2-atspi-2.0")
            return
        except (ImportError, ValueError):
            pass
        self._fail("gir1.2-atspi-2.0 missing — fixing")
        result = self._sudo("apt", "install", "-y", "gir1.2-atspi-2.0")
        if result.returncode == 0:
            self._fixed_msg("apt install gir1.2-atspi-2.0")
        else:
            print(f"       apt install failed: {result.stderr.strip()[-200:]}")

    # ── scrot ─────────────────────────────────────────────────────────

    def _check_scrot(self):
        if shutil.which("scrot"):
            self._ok("scrot")
            return
        self._fail("scrot missing — fixing")
        result = self._sudo("apt", "install", "-y", "scrot")
        if result.returncode == 0:
            self._fixed_msg("apt install scrot")
        else:
            print(f"       apt install failed: {result.stderr.strip()[-200:]}")

    # ── python3-opencv ────────────────────────────────────────────────

    def _check_opencv(self):
        if importlib.util.find_spec("cv2"):
            self._ok("python3-opencv")
            return
        self._fail("python3-opencv missing — fixing")
        result = self._sudo("apt", "install", "-y", "python3-opencv")
        if result.returncode == 0:
            self._fixed_msg("apt install python3-opencv")
            return
        # Fallback: pip install
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "opencv-python", "--break-system-packages"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            self._fixed_msg("pip install opencv-python")
        else:
            print(f"       install failed: {result.stderr.strip()[-200:]}")

    # ── DISPLAY ───────────────────────────────────────────────────────

    def _check_display(self):
        display = os.environ.get("DISPLAY", "")
        if display:
            self._ok(f"DISPLAY={display}")
            return
        self._fail("DISPLAY not set")
        print("       run: export DISPLAY=:0")

    # ── XAUTHORITY ────────────────────────────────────────────────────

    def _check_xauthority(self):
        xauth = Path.home() / ".Xauthority"
        if xauth.exists():
            self._ok("~/.Xauthority")
            return
        self._fail("~/.Xauthority missing — fixing")
        xauth.touch(exist_ok=True)
        self._fixed_msg("touch ~/.Xauthority")

    # ── accessibility ─────────────────────────────────────────────────

    def _check_accessibility(self):
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "toolkit-accessibility"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and "true" in result.stdout.lower():
            self._ok("accessibility enabled")
            return
        self._fail("accessibility disabled — fixing")
        r = subprocess.run(
            [
                "gsettings", "set", "org.gnome.desktop.interface",
                "toolkit-accessibility", "true",
            ],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            self._fixed_msg("gsettings set toolkit-accessibility true")
        else:
            print(f"       gsettings failed: {r.stderr.strip()[-200:]}")

    # ── libclang Python bindings ──────────────────────────────────────

    def _check_libclang(self):
        try:
            import clang.cindex  # noqa: F401
            self._ok("libclang Python bindings")
            return
        except ImportError:
            pass
        self._fail("libclang Python bindings missing — fixing")

        # Strategy 1: apt install python3-clang-18 libclang-18-dev
        result = self._sudo("apt", "install", "-y", "python3-clang-18", "libclang-18-dev")
        if result.returncode == 0:
            self._fixed_msg("apt install python3-clang-18 libclang-18-dev")
            return

        # Strategy 2: apt install python3-clang-17 libclang-17-dev
        result = self._sudo("apt", "install", "-y", "python3-clang-17", "libclang-17-dev")
        if result.returncode == 0:
            self._fixed_msg("apt install python3-clang-17 libclang-17-dev")
            return

        # Strategy 3: apt install python3-clang libclang-dev
        result = self._sudo("apt", "install", "-y", "python3-clang", "libclang-dev")
        if result.returncode == 0:
            self._fixed_msg("apt install python3-clang libclang-dev")
            return

        print(f"       all install strategies failed: {result.stderr.strip()[-200:]}")

    # ── java ──────────────────────────────────────────────────────────


    def _check_java(self):
        if shutil.which("java"):
            result = subprocess.run(
                ["java", "-version"],
                capture_output=True,
                text=True,
            )
            version_info = (result.stderr + result.stdout).split("\n")[0].strip()[:60]
            self._ok(f"java ({version_info})")
            return
        self._fail("java missing (required for Allure HTML reports)")
        result = self._sudo("apt", "install", "-y", "openjdk-11-jdk-headless")
        if result.returncode == 0:
            self._fixed_msg("apt install openjdk-11-jdk-headless")
        else:
            print("       install JDK manually:")
            print("         Debian/Ubuntu: sudo apt install openjdk-11-jdk-headless")
            print("         RHEL/openEuler: sudo yum install java-11-openjdk-headless")

    # ── skills ────────────────────────────────────────────────────────

    def _check_skills(self):
        try:
            import youqu
            skills_dir = Path(youqu.__file__).parent / "skills"
        except Exception:
            return

        if not skills_dir.exists() or not skills_dir.is_dir():
            return

        available = sorted([d.name for d in skills_dir.iterdir() if d.is_dir()])
        if not available:
            return

        print(f"\n  Found {len(available)} YouQu skills: {', '.join(available)}")
        print("  These enable AI agents to generate and run test cases automatically.")

        target_dir = Path.home() / ".agents" / "skills"
        target_dir.mkdir(parents=True, exist_ok=True)

        installed = 0
        for skill_name in available:
            src = skills_dir / skill_name
            dst = target_dir / skill_name
            try:
                if dst.is_symlink():
                    dst.unlink()
                elif dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                installed += 1
            except PermissionError:
                print(f"  \033[31m!!\033[0m Permission denied: {dst}")
            except OSError as e:
                print(f"  \033[31m!!\033[0m Failed to copy {skill_name}: {e}")

        if installed == len(available):
            self._ok(f"installed {installed} skills → {target_dir}")
        else:
            self._fail(f"installed {installed}/{len(available)} skills")
        print(f"  Skill installation path: {target_dir}\n")
