"""Install/uninstall integration tests; every destination lives in TemporaryDirectory."""
import hashlib
import re
import shutil
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import manage_install


ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "scripts/manage_install.py"


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="fortune-install-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.prefix = self.root / "中文安装 有 空格 ' 引号"
        self.env = dict(os.environ, PATH="/usr/bin:/bin", PYTHON=sys.executable)
        self.env.pop("DAILY_FORTUNE_HOME", None)

    def manage(self, action, success=True, env=None, manager=MANAGER):
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(manager), action, "--prefix", str(self.prefix)],
            text=True, capture_output=True, env=env or self.env,
        )
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout + result.stderr)
        return result

    @property
    def launcher(self):
        return self.prefix / "bin/今日运势"

    @property
    def base(self):
        return self.prefix / "share/daily-fortune"

    def run_installed(self, *arguments):
        result = subprocess.run([str(self.launcher), *arguments], capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_install_run_uninstall_and_reinstall_preserves_identity(self):
        installed = subprocess.run(
            ["/bin/sh", str(ROOT / "install.sh"), "--prefix", str(self.prefix)],
            capture_output=True, text=True, env=self.env,
        )
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertTrue(os.access(self.launcher, os.X_OK))
        output = self.run_installed("--date", "2026-11-08", "--plain")
        self.assertIn("穷观阵已启", output)
        self.assertIn("符卡：", output)
        self.assertIn("2026-11-08", self.run_installed("--full", "--date", "2026-11-08"))
        self.assertEqual(output, self.run_installed("--date", "2026-11-08", "--plain"))
        state = self.base / "state/user-id"
        identity = state.read_bytes()
        self.assertIn("符卡：", self.run_installed())
        self.assertIn("此卦本座已断", self.run_installed())
        # Uninstall must leave the anonymous identity and draw history untouched.
        uninstalled = subprocess.run(
            ["/bin/sh", str(ROOT / "uninstall.sh"), "--prefix", str(self.prefix)],
            capture_output=True, text=True, env=self.env,
        )
        self.assertEqual(uninstalled.returncode, 0, uninstalled.stderr)
        self.assertFalse(self.launcher.exists())
        self.assertFalse((self.base / "app").exists())
        self.assertFalse((self.base / "receipt.json").exists())
        self.assertEqual(state.read_bytes(), identity)
        self.manage("install")
        self.assertIn("此卦本座已断", self.run_installed())
        self.assertEqual(output, self.run_installed("--date", "2026-11-08", "--plain"))
        self.manage("uninstall")

    @unittest.skipUnless(sys.platform == "darwin", "更新器使用 macOS 排他改名")
    def test_update_preserves_launcher_and_state_and_keeps_old_program(self):
        old_release = self.root / "old-release"
        shutil.copytree(ROOT / "daily_fortune", old_release / "daily_fortune", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(ROOT / "main.py", old_release / "main.py")
        old_manager = old_release / "scripts/manage_install.py"
        old_manager.parent.mkdir()
        shutil.copy2(MANAGER, old_manager)
        old_package = old_release / "daily_fortune/__init__.py"
        old_package.write_text(re.sub(r'^__version__ = .*$', '__version__ = "1.4.0"', old_package.read_text(),
                                      count=1, flags=re.MULTILINE))
        self.manage("install", manager=old_manager)
        self.assertEqual(self.run_installed("--version").strip(), "今日运势 1.4.0")
        self.run_installed("--date", "2026-11-08", "--plain")
        state = self.base / "state"
        marker = state / "drawn-2026-11-08"
        marker.write_bytes(b"1")
        old_identity = (state / "user-id").read_bytes()
        old_launcher = (self.launcher.stat().st_ino, self.launcher.read_bytes())
        old_receipt = (self.base / "receipt.json").read_bytes()

        result = subprocess.run(
            ["/bin/sh", str(ROOT / "update.sh"), "--prefix", str(self.prefix)],
            capture_output=True, text=True, env=self.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("更新完成", result.stdout)
        expected = subprocess.check_output(
            [sys.executable, "-I", "-B", str(ROOT / "main.py"), "--version"], env=self.env, text=True,
        )
        self.assertNotEqual(expected.strip(), "今日运势 1.4.0")
        self.assertEqual(self.run_installed("--version"), expected)
        self.assertEqual((self.launcher.stat().st_ino, self.launcher.read_bytes()), old_launcher)
        self.assertEqual((state / "user-id").read_bytes(), old_identity)
        self.assertEqual(marker.read_bytes(), b"1")
        (backup,) = self.base.parent.glob("daily-fortune-backup-*")
        self.assertEqual((backup / "receipt.json").read_bytes(), old_receipt)
        self.assertEqual((backup / "app/daily_fortune/__init__.py").read_bytes(), old_package.read_bytes())
        self.manage("update")  # A retry with identical content keeps just one backup.
        self.assertEqual(list(self.base.parent.glob("daily-fortune-backup-*")), [backup])
        self.manage("uninstall")

    @unittest.skipUnless(sys.platform == "darwin", "更新器使用 macOS 排他改名")
    def test_update_restores_old_program_if_switch_fails(self):
        self.manage("install")
        package_init = str(manage_install.APP / "daily_fortune/__init__.py")
        payloads = manage_install.application_payloads()
        payloads[package_init] += b"\n# Different staged source\n"
        old_receipt = (self.base / "receipt.json").read_bytes()
        rename = manage_install.rename_exclusive

        def fail_publishing_receipt(source, target):
            if source.parent.name.startswith(".daily-fortune-update-") and target == self.base / "receipt.json":
                raise OSError("测试更新中断")
            rename(source, target)

        with patch.object(manage_install, "application_payloads", return_value=payloads), \
                patch.object(manage_install, "rename_exclusive", side_effect=fail_publishing_receipt):
            with self.assertRaisesRegex(manage_install.InstallError, "已恢复原版本"):
                manage_install.update(self.prefix)
        self.assertEqual((self.base / "receipt.json").read_bytes(), old_receipt)
        self.assertIn("今日运势", self.run_installed("--version"))
        self.assertEqual(list(self.base.parent.glob("daily-fortune-backup-*")), [])
        self.manage("uninstall")

    def test_existing_command_file_is_never_overwritten(self):
        self.launcher.parent.mkdir(parents=True)
        self.launcher.write_text("sentinel", encoding="utf-8")
        self.manage("install", success=False)
        self.assertEqual(self.launcher.read_text(), "sentinel")
        self.assertFalse(self.base.exists())

    def test_existing_path_command_is_rejected(self):
        other = self.root / "other-bin"
        other.mkdir()
        command = other / "今日运势"
        command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        command.chmod(0o755)
        env = dict(self.env, PATH=str(other) + os.pathsep + self.env["PATH"])
        result = self.manage("install", success=False, env=env)
        self.assertIn("PATH", result.stderr)
        self.assertFalse(self.prefix.exists())

    def test_second_install_is_rejected(self):
        self.manage("install")
        original = self.launcher.read_bytes()
        self.manage("install", success=False)
        self.assertEqual(original, self.launcher.read_bytes())

    def test_unwritable_prefix_has_clear_error(self):
        self.prefix.mkdir()
        self.prefix.chmod(0o500)
        try:
            if os.access(self.prefix, os.W_OK):
                self.skipTest("当前账号绕过目录写权限，不能可靠模拟权限不足。")
            result = self.manage("install", success=False)
            self.assertIn("安装失败", result.stderr)
            self.assertFalse(self.launcher.exists())
        finally:
            self.prefix.chmod(0o700)

    def test_uninstall_preflights_all_removal_parent_permissions(self):
        # Each of these directories is the parent of an unlink or rmdir.
        for relative in ("bin", "share/daily-fortune", "share/daily-fortune/app",
                         "share/daily-fortune/app/daily_fortune"):
            with self.subTest(relative=relative):
                self.manage("install")
                receipt_path = self.base / "receipt.json"
                recorded = json.loads(receipt_path.read_text())["files"]
                before = {path: (self.prefix / path).read_bytes() for path in recorded}
                parent = self.prefix / relative
                parent.chmod(0o500)
                try:
                    if os.access(parent, os.W_OK):
                        self.skipTest("当前账号绕过目录写权限，不能可靠模拟权限不足。")
                    result = self.manage("uninstall", success=False)
                    self.assertIn("权限", result.stderr)
                    self.assertEqual(before, {path: (self.prefix / path).read_bytes() for path in recorded})
                    self.assertTrue(receipt_path.exists())
                finally:
                    parent.chmod(0o755)
                # Restoring permission must allow a clean retry without repair.
                self.manage("uninstall")

    def test_uninstall_requires_directory_execute_permission(self):
        self.manage("install")
        parent = self.base / "app/daily_fortune"
        parent.chmod(0o600)
        try:
            if os.access(parent, os.X_OK):
                self.skipTest("当前账号绕过目录执行权限，不能可靠模拟权限不足。")
            result = self.manage("uninstall", success=False)
            self.assertIn("权限", result.stderr)
            self.assertTrue(self.launcher.exists())
            self.assertTrue((self.base / "app/main.py").exists())
            self.assertTrue((self.base / "receipt.json").exists())
        finally:
            parent.chmod(0o755)
        self.manage("uninstall")

    def test_modified_program_refuses_all_removal(self):
        self.manage("install")
        main = self.base / "app/main.py"
        main.write_bytes(main.read_bytes() + b"\n# local customization\n")
        result = self.manage("uninstall", success=False)
        self.assertIn("改动", result.stderr)
        self.assertTrue(self.launcher.exists())
        self.assertTrue((self.base / "receipt.json").exists())

    def test_unknown_file_refuses_all_removal(self):
        self.manage("install")
        note = self.base / "app/personal-note.txt"
        note.write_text("must survive", encoding="utf-8")
        self.manage("uninstall", success=False)
        self.assertEqual(note.read_text(), "must survive")
        self.assertTrue(self.launcher.exists())

    def test_missing_file_refuses_all_removal(self):
        self.manage("install")
        (self.base / "app/main.py").unlink()
        self.manage("uninstall", success=False)
        self.assertTrue(self.launcher.exists())

    def test_unknown_directory_refuses_all_removal(self):
        self.manage("install")
        (self.base / "app/extra").mkdir()
        self.manage("uninstall", success=False)
        self.assertTrue(self.launcher.exists())

    def test_symlink_target_is_never_followed(self):
        self.manage("install")
        main = self.base / "app/main.py"
        outside = self.root / "outside.py"
        outside.write_bytes(main.read_bytes())
        main.unlink()
        main.symlink_to(outside)
        self.manage("uninstall", success=False)
        self.assertTrue(main.is_symlink())
        self.assertTrue(outside.exists())
        self.assertTrue(self.launcher.exists())

    def test_symlink_install_directory_is_rejected(self):
        self.prefix.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        (self.prefix / "share").symlink_to(outside, target_is_directory=True)
        self.manage("install", success=False)
        self.assertEqual(list(outside.iterdir()), [])

    def test_manifest_traversal_is_rejected(self):
        self.manage("install")
        outside = self.root / "outside.txt"
        outside.write_text("keep", encoding="utf-8")
        receipt_path = self.base / "receipt.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["files"]["../outside.txt"] = hashlib.sha256(outside.read_bytes()).hexdigest()
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        self.manage("uninstall", success=False)
        self.assertEqual(outside.read_text(), "keep")
        self.assertTrue(self.launcher.exists())

    def test_corrupt_manifest_is_rejected(self):
        self.manage("install")
        (self.base / "receipt.json").write_text("{", encoding="utf-8")
        self.manage("uninstall", success=False)
        self.assertTrue(self.launcher.exists())

    def test_missing_python_has_clear_shell_diagnostic(self):
        env = dict(self.env, PYTHON=str(self.root / "missing-python"))
        for script in ("install.sh", "uninstall.sh", "update.sh"):
            with self.subTest(script=script):
                result = subprocess.run(["/bin/sh", str(ROOT / script)], capture_output=True, text=True, env=env)
                self.assertEqual(result.returncode, 1)
                self.assertIn("找不到 Python 3", result.stderr)
        self.assertFalse(self.prefix.exists())


if __name__ == "__main__":
    unittest.main()
