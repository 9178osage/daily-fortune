"""Exercise the documented Windows PowerShell and cmd entry points."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from daily_fortune import __version__


ROOT = Path(__file__).resolve().parents[1]
PREVIEW_ARGS = ("--date", "2026-11-08", "--plain")


@unittest.skipUnless(sys.platform == "win32", "requires Windows PowerShell and cmd")
class WindowsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="fortune-win-test-")
        self.addCleanup(temporary.cleanup)
        self.external_directory = Path(temporary.name)
        self.local_data = self.external_directory / "中文 本地数据"
        self.local_data.mkdir()
        self.env = dict(
            os.environ,
            LOCALAPPDATA=str(self.local_data),
            PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
        )
        self.env.pop("DAILY_FORTUNE_HOME", None)
        self.installation = self.local_data / "daily-fortune"

    def manage(self, action, *args, source_directory=ROOT):
        process = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(source_directory / f"{action}.ps1"), *map(str, args)],
            cwd=self.external_directory,
            env=self.env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)

    def run_launcher(self, *args, source=False, expected_exit=0):
        if source:
            setup = ""
            launcher = r"python .\main.py"
        else:
            setup = "$env:Path = $env:FORTUNE_TEST_BIN + ';' + $env:Path; "
            launcher = "daily-fortune"
        # The legacy PowerShell host uses this encoding to decode native stdout.
        arguments = " ".join("'" + arg.replace("'", "''") + "'" for arg in args)
        command = (
            "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); "
            f"{setup}& {launcher} {arguments}; exit $LASTEXITCODE"
        )
        process = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            cwd=ROOT if source else self.external_directory,
            env=dict(self.env, FORTUNE_TEST_BIN=str(self.installation / "bin")),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            timeout=30,
        )
        self.assertEqual(process.returncode, expected_exit, process.stdout + process.stderr)
        return process.stdout if expected_exit == 0 else process.stderr

    def previous_release(self):
        fixture = self.external_directory / "旧版 源码"
        fixture.mkdir()
        for file in ("install.ps1", "update.ps1", "uninstall.ps1", "main.py"):
            shutil.copy2(ROOT / file, fixture / file)
        for directory in ("daily_fortune", "scripts"):
            shutil.copytree(ROOT / directory, fixture / directory, ignore=shutil.ignore_patterns("__pycache__"))
        version_file = fixture / "daily_fortune" / "__init__.py"
        old_contents, replacements = re.subn(
            r'^__version__ = "[^"]+"$', '__version__ = "0.0.0"',
            version_file.read_text(encoding="utf-8"), flags=re.MULTILINE,
        )
        self.assertEqual(replacements, 1)
        version_file.write_text(old_contents, encoding="utf-8")
        return fixture

    def test_default_install_update_and_reinstall(self):
        source_preview = self.run_launcher(*PREVIEW_ARGS, source=True)
        self.assertIn("符卡：", source_preview)
        self.assertNotIn("\x1b", source_preview)
        self.assertEqual(len(source_preview.splitlines()), 7)
        identity = self.installation / "state" / "user-id"
        original_identity = identity.read_bytes()

        self.manage("install", source_directory=self.previous_release())
        launcher = self.installation / "bin" / "daily-fortune.cmd"
        self.assertTrue(launcher.is_file())
        self.assertIn("0.0.0", self.run_launcher("--version"))
        self.assertIn("参数错误", self.run_launcher("--date", "2026-02-30", expected_exit=2))
        self.assertEqual(self.run_launcher(*PREVIEW_ARGS), source_preview)
        detailed = self.run_launcher("--full", *PREVIEW_ARGS)
        self.assertIn("赛博黄历", detailed)
        self.assertIn("今日寄语", detailed)
        self.assertIn("符卡：", self.run_launcher())
        self.assertIn("此卦本座已断", self.run_launcher(source=True))

        self.manage("update")
        self.assertIn(__version__, self.run_launcher("--version"))
        self.assertEqual(identity.read_bytes(), original_identity)
        self.assertEqual(self.run_launcher(*PREVIEW_ARGS), source_preview)
        self.assertIn("此卦本座已断", self.run_launcher())

        self.manage("uninstall")
        self.assertFalse(launcher.exists())
        self.assertFalse((self.installation / "app").exists())
        self.assertFalse((self.installation / "receipt.json").exists())
        self.assertEqual(identity.read_bytes(), original_identity)
        self.manage("install")
        self.assertIn("此卦本座已断", self.run_launcher())

    def test_custom_prefix_uses_its_own_state(self):
        self.installation = self.external_directory / "自定义 安装"
        self.manage("install", "-Prefix", self.installation)
        self.assertIn("符卡：", self.run_launcher(*PREVIEW_ARGS))
        self.assertTrue((self.installation / "state" / "user-id").is_file())
        self.assertFalse((self.local_data / "daily-fortune").exists())
        self.manage("uninstall", "-Prefix", self.installation)
