"""Install/uninstall integration tests; every destination lives in TemporaryDirectory."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from scripts import manage_install

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "scripts/manage_install.py"
MACOS_FIXTURE = ROOT / "tests/fixtures/daily-fortune-1.5.0-macos.zip"


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
            text=True, capture_output=True, env=env or self.env, timeout=30,
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

    def install_previous_release(self):
        old_release = self.root / "old-release"
        with ZipFile(MACOS_FIXTURE) as archive:
            archive.extractall(old_release)
        self.manage("install", manager=old_release / "scripts/manage_install.py")
        return old_release

    def interrupt_after_move(self, action, count):
        driver = """
import os
import sys
from scripts import manage_install

rename = manage_install.rename_exclusive
remaining = int(sys.argv.pop(1))

def interrupt(source, target):
    global remaining
    rename(source, target)
    remaining -= 1
    if remaining == 0:
        os._exit(73)

manage_install.rename_exclusive = interrupt
raise SystemExit(manage_install.main())
"""
        result = subprocess.run(
            [sys.executable, "-B", "-c", driver, str(count), action, "--prefix", str(self.prefix)],
            cwd=ROOT, env=self.env, text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 73, result.stdout + result.stderr)

    def test_install_run_uninstall_and_reinstall_preserves_identity(self):
        installed = subprocess.run(
            ["/bin/sh", str(ROOT / "install.sh"), "--prefix", str(self.prefix)],
            capture_output=True, text=True, env=self.env,
        )
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertTrue(os.access(self.launcher, os.X_OK))
        output = self.run_installed("--date", "2026-11-08", "--plain")
        self.assertIn("穷观阵推演已毕", output)
        self.assertIn("符卡：", output)
        self.assertIn("2026-11-08", self.run_installed("--full", "--date", "2026-11-08"))
        self.assertEqual(output, self.run_installed("--date", "2026-11-08", "--plain"))
        state = self.base / "state/user-id"
        identity = state.read_bytes()
        self.assertIn("符卡：", self.run_installed())
        self.assertIn("同日诸元未变", self.run_installed())
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
        self.assertIn("同日诸元未变", self.run_installed())
        self.assertEqual(output, self.run_installed("--date", "2026-11-08", "--plain"))
        self.manage("uninstall")

    @unittest.skipUnless(sys.platform == "darwin", "更新器使用 macOS 排他改名")
    def test_update_preserves_launcher_and_state_and_keeps_old_program(self):
        old_release = self.install_previous_release()
        old_package = old_release / "daily_fortune/__init__.py"
        self.assertEqual(self.run_installed("--version").strip(), "今日运势 1.5.0")
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
        self.assertNotEqual(expected.strip(), "今日运势 1.5.0")
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
            if source.parent.name == "new" and target == self.base / "receipt.json":
                raise OSError("测试更新中断")
            rename(source, target)

        with patch.object(manage_install, "application_payloads", return_value=payloads), \
                patch.object(manage_install, "rename_exclusive", side_effect=fail_publishing_receipt), \
                self.assertRaisesRegex(manage_install.InstallError, "已恢复原版本"):
            manage_install.update(self.prefix)
        self.assertEqual((self.base / "receipt.json").read_bytes(), old_receipt)
        self.assertIn("今日运势", self.run_installed("--version"))
        self.assertEqual(list(self.base.parent.glob("daily-fortune-backup-*")), [])
        self.manage("uninstall")

    @unittest.skipUnless(sys.platform == "darwin", "更新器使用 macOS 排他改名")
    def test_update_recovers_after_process_termination(self):
        for move in (2, 5):
            with self.subTest(move=move):
                self.prefix = self.root / f"interrupted-{move}"
                self.install_previous_release()
                self.run_installed("--plain")
                state = {path.name: path.read_bytes() for path in (self.base / "state").iterdir()}
                self.interrupt_after_move("update", move)
                pending = self.base / manage_install.TRANSACTION
                self.assertTrue((pending / "app/main.py").is_file())
                if move == 2:
                    self.assertFalse((self.base / "app").exists())
                else:
                    # Interrupt recovery itself after moving the new receipt aside.
                    self.interrupt_after_move("update", 1)
                    self.assertFalse((self.base / "receipt.json").exists())
                result = self.manage("update")
                self.assertIn("已恢复上次未完成", result.stdout)
                self.assertFalse(pending.exists())
                self.assertEqual({path.name: path.read_bytes() for path in (self.base / "state").iterdir()}, state)
                self.assertNotIn("1.5.0", self.run_installed("--version"))
                self.assertIn("同日诸元未变", self.run_installed())

    @unittest.skipUnless(sys.platform == "darwin", "更新器使用 macOS 排他改名")
    def test_update_can_replace_a_missing_interpreter(self):
        old_python = self.root / "old-python"
        old_python.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n', encoding="utf-8")
        old_python.chmod(0o755)
        launcher_bytes = manage_install.launcher_bytes

        def bind_old_python(prefix):
            with patch.object(sys, "executable", str(old_python)):
                return launcher_bytes(prefix)

        with patch.object(manage_install, "launcher_bytes", side_effect=bind_old_python), \
                patch.dict(os.environ, self.env, clear=True), redirect_stdout(io.StringIO()):
            manage_install.install(self.prefix.resolve())
        old_launcher = self.launcher.read_bytes()
        self.assertIn(str(old_python.resolve()), old_launcher.decode())
        self.run_installed("--plain")
        old_python.rename(self.root / "moved-python")
        result = self.manage("update", success=False, env=dict(self.env, PYTHON=""))
        self.assertIn("原 Python 解释器已不可用", result.stderr)
        result = self.manage("update")
        self.assertIn("更新完成", result.stdout)
        self.assertNotEqual(self.launcher.read_bytes(), old_launcher)
        (backup,) = self.base.parent.glob("daily-fortune-backup-*")
        self.assertEqual((backup / "bin/今日运势").read_bytes(), old_launcher)
        self.assertIn("同日诸元未变", self.run_installed())

    def test_install_rejects_missing_and_unrunnable_payloads(self):
        source = self.root / "incomplete-source"
        shutil.copytree(ROOT / "daily_fortune", source / "daily_fortune",
                        ignore=shutil.ignore_patterns("cli.py", "__pycache__"))
        shutil.copy2(ROOT / "main.py", source / "main.py")
        manager = source / "scripts/manage_install.py"
        manager.parent.mkdir()
        shutil.copy2(MANAGER, manager)
        result = self.manage("install", success=False, manager=manager)
        self.assertIn("daily_fortune/cli.py", result.stderr)
        self.assertFalse(self.prefix.exists())

        (source / "daily_fortune/cli.py").write_text("raise SystemExit('broken CLI fixture')\n", encoding="utf-8")
        result = self.manage("install", success=False, manager=manager)
        self.assertIn("broken CLI fixture", result.stderr)
        self.assertFalse(self.launcher.exists())
        self.assertFalse((self.base / "receipt.json").exists())
        self.assertFalse((self.base / "app").exists())

    def test_uninstall_refuses_immutable_launcher_before_mutation(self):
        if sys.platform != "darwin":
            self.skipTest("需要 macOS 不可变文件标志")
        self.manage("install")
        receipt = self.base / "receipt.json"
        recorded = json.loads(receipt.read_text())["files"]
        before = {path: (self.prefix / path).read_bytes() for path in recorded}
        os.chflags(self.launcher, stat.UF_IMMUTABLE)
        try:
            refused = self.manage("uninstall", success=False)
            self.assertIn("不可变", refused.stderr)
            self.assertTrue(receipt.exists())
            self.assertEqual({path: (self.prefix / path).read_bytes() for path in recorded}, before)
        finally:
            os.chflags(self.launcher, 0)
        self.manage("uninstall")

    @unittest.skipUnless(sys.platform == "darwin", "更新器使用 macOS 排他改名")
    def test_uninstall_recovers_after_process_termination(self):
        self.manage("install")
        self.run_installed("--plain")
        receipt = (self.base / "receipt.json").read_bytes()
        self.interrupt_after_move("uninstall", 3)
        self.assertFalse(self.launcher.exists())
        self.assertEqual((self.base / "receipt.json").read_bytes(), receipt)
        self.assertIn("已恢复上次未完成", self.manage("update").stdout)
        self.assertEqual((self.base / "receipt.json").read_bytes(), receipt)
        self.assertIn("同日诸元未变", self.run_installed())
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

    @unittest.skipIf(os.name == "nt", "POSIX 文件系统锁")
    def test_installation_lock_serializes_posix_operations(self):
        holding = threading.Event()
        release = threading.Event()
        acquired = threading.Event()

        def first():
            with manage_install.installation_lock(self.prefix):
                holding.set()
                if not release.wait(5):
                    raise RuntimeError("test lock was not released")

        def second():
            if not holding.wait(5):
                raise RuntimeError("first operation did not acquire lock")
            with manage_install.installation_lock(self.prefix):
                acquired.set()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first_result = pool.submit(first)
            self.assertTrue(holding.wait(5))
            second_result = pool.submit(second)
            try:
                self.assertFalse(acquired.wait(0.2))
            finally:
                release.set()
            first_result.result(timeout=5)
            second_result.result(timeout=5)
        self.assertTrue(acquired.is_set())

    def test_failed_uninstall_rolls_back_published_moves(self):
        self.manage("install")
        rename = manage_install.rename_exclusive

        def fail_launcher_move(source, target):
            if source == self.launcher:
                raise OSError("simulated launcher move failure")
            rename(source, target)

        with patch.object(manage_install, "rename_exclusive", side_effect=fail_launcher_move):
            with self.assertRaisesRegex(manage_install.InstallError, "已恢复原版本"):
                manage_install.uninstall(self.prefix)

        self.assertTrue(os.access(self.launcher, os.X_OK))
        manage_install.check_installation(self.prefix)
        self.assertIn("今日运势", self.run_installed("--version"))
        self.assertFalse(any(path.name == manage_install.TRANSACTION
                             for path in self.base.iterdir()))
        self.manage("uninstall")

    def test_windows_install_entrypoint_recovers_pending_change(self):
        with patch.object(manage_install, "WINDOWS", True), \
                patch.object(manage_install, "check_install_target"), \
                patch.object(manage_install, "installation_lock", return_value=nullcontext()), \
                patch.object(manage_install, "recover_change", return_value=True) as recover, \
                patch.object(manage_install, "install") as action, \
                patch.object(sys, "argv", ["manage_install.py", "install", "--prefix", str(self.prefix)]), \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(manage_install.main(), 0)
        recover.assert_called_once_with(self.prefix.resolve())
        action.assert_called_once_with(self.prefix.resolve())
        self.assertIn("已恢复上次未完成", output.getvalue())

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

    def test_installer_rejects_invalid_or_relative_home_paths(self):
        with patch.object(Path, "home", return_value=Path("relative-home")):
            with self.assertRaisesRegex(manage_install.InstallError, "绝对路径"):
                manage_install.default_prefix()
        with self.assertRaisesRegex(manage_install.InstallError, "无法解析安装根目录"):
            manage_install.prefix_path("~daily-fortune-user-that-does-not-exist/install")

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
