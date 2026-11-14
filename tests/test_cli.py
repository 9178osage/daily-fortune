from concurrent.futures import ThreadPoolExecutor
from datetime import date
import errno
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

if os.name != "nt":
    import pty
    import select
    import termios
    import time

from daily_fortune.draw_memory import DrawMemoryError, daily_draw
from daily_fortune.engine import generate
from daily_fortune.identity import IdentityError, load_identity, state_directory
from daily_fortune.render import ANSI, clusters, display_width, render, wrap

ROOT = Path(__file__).resolve().parents[1]
USER = "0123456789abcdef0123456789abcdef"


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fortune-test-")
        self.state = Path(self.temp.name) / "中文 状态"
        self.env = dict(os.environ, DAILY_FORTUNE_HOME=str(self.state), COLUMNS="76")

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args, isolated=True, **env):
        python_flags = ["-I", "-B"] if isolated else ["-B"]
        return subprocess.run([sys.executable, *python_flags, str(ROOT / "main.py"), *args],
                              env=dict(self.env, **env), capture_output=True, encoding="utf-8")

    def test_process_restarts_and_fresh_zsh_same_day(self):
        expected = self.run_cli("--date", "2026-11-08", "--plain")
        self.assertEqual(expected.returncode, 0, expected.stderr)
        for seed in ("0", "42", "random"):
            actual = self.run_cli("--date", "2026-11-08", "--plain", isolated=False, PYTHONHASHSEED=seed)
            self.assertEqual(actual.returncode, 0, actual.stderr)
            self.assertEqual(actual.stdout, expected.stdout)
        if Path("/bin/zsh").exists():
            for _ in range(2):
                shell = subprocess.run(["/bin/zsh", "-f", "-c", 'exec "$1" -I -B "$2" --plain --date 2026-11-08',
                                        "fortune-test", sys.executable, str(ROOT / "main.py")],
                                       env=self.env, capture_output=True, encoding="utf-8")
                self.assertEqual(shell.returncode, 0, shell.stderr)
                self.assertEqual(shell.stdout, expected.stdout)
        tomorrow = self.run_cli("--date", "2026-11-09", "--plain")
        self.assertNotEqual(tomorrow.stdout, expected.stdout)

    def test_local_date_and_utc_boundary(self):
        # TZ is read by each new process; compare to its own local date.
        zones = ("Pacific/Kiritimati", "America/Los_Angeles", "Etc/GMT+12") if os.name != "nt" else ("",)
        for zone in zones:
            local = subprocess.check_output([sys.executable, "-c", "from datetime import date; print(date.today())"],
                                             env=dict(self.env, TZ=zone), text=True).strip()
            state = str(self.state / zone.replace("/", "-"))
            output = self.run_cli("--plain", TZ=zone, DAILY_FORTUNE_HOME=state)
            explicit = self.run_cli("--plain", "--date", local, TZ=zone, DAILY_FORTUNE_HOME=state)
            self.assertIn("符卡：", output.stdout)
            self.assertEqual(output.stdout, explicit.stdout)

    def test_help_version_and_invalid_date_do_not_create_state(self):
        for args in (("--help",), ("--version",), ("--date", "2026-02-30"),
                     ("--date", "20261108"), ("--date", "2026-1-01"), ("--unknown",)):
            result = self.run_cli(*args, isolated=False, LC_ALL="C", PYTHONUTF8="0", PYTHONIOENCODING="ascii")
            self.assertEqual(result.returncode, 0 if args[0] in ("--help", "--version") else 2)
            self.assertFalse(self.state.exists())

    def test_closed_output_pipe_exits_quietly(self):
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        try:
            process = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "main.py")],
                                     env=self.env, stdout=write_fd, stderr=subprocess.PIPE)
        finally:
            os.close(write_fd)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(process.stderr, b"")
        self.assertIn("符卡：", self.run_cli().stdout)

    def test_daily_draw_memory(self):
        first_zone = "Pacific/Kiritimati"
        today = subprocess.check_output([sys.executable, "-c", "from datetime import date; print(date.today())"],
                                        env=dict(self.env, TZ=first_zone), text=True).strip()
        preview = self.run_cli("--date", today, TZ=first_zone)
        self.assertIn("符卡：", preview.stdout)
        self.assertIn("今日总览", self.run_cli("--full", TZ=first_zone).stdout)
        first = self.run_cli(TZ=first_zone)
        self.assertEqual(first.stdout, preview.stdout)
        repeat = self.run_cli("--plain", TZ=first_zone)
        self.assertEqual(repeat.returncode, 0)
        self.assertTrue(repeat.stdout.startswith("此卦本座已断。哼，同日无须再问 ("))
        self.assertNotIn("符卡：", repeat.stdout)
        self.assertEqual(self.run_cli("--date", today, TZ=first_zone).stdout, preview.stdout)

    @unittest.skipIf(os.name == "nt", "Windows 不使用 IANA TZ 环境变量切换本地时区")
    def test_daily_draw_date_rollover(self):
        first = self.run_cli(TZ="Pacific/Kiritimati")
        self.assertIn("符卡：", first.stdout)
        self.assertIn("符卡：", self.run_cli(TZ="Etc/GMT+12").stdout)
        self.assertIn("此卦本座已断", self.run_cli(TZ="Pacific/Kiritimati").stdout)

    def test_concurrent_daily_draw_only_prints_one_card(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: self.run_cli(), range(8)))
        self.assertTrue(all(result.returncode == 0 for result in results))
        self.assertEqual(sum("符卡：" in result.stdout for result in results), 1)
        self.assertEqual(sum("此卦本座已断" in result.stdout for result in results), 7)

    def test_default_compact_card_and_plain(self):
        args = ("--date", "2026-11-08")
        result = self.run_cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 7)
        self.assertRegex(lines[0], r"^穷观阵已启，本座观得[坎艮坤巽兑离乾]象 \(")
        self.assertNotIn("我", result.stdout)
        self.assertIn("仅供娱乐", lines[0])
        for line, label in zip(lines[1:4], ("财运", "桃花运", "事业运")):
            self.assertRegex(line, rf"^{label}：(?:[1-9][0-9]?|100)$")
        self.assertRegex(lines[4], r"^符卡：.+「.+」$")
        self.assertRegex(lines[5], r"^点评：(凶|末吉|平|小吉|中吉|大吉)。")
        self.assertIn("宜", lines[5])
        self.assertIn("不宜", lines[5])
        self.assertRegex(lines[6], r"^[★☆]{7}$")
        plain = self.run_cli(*args, "--plain").stdout.splitlines()
        self.assertEqual(plain, [*lines[:-1], f"{lines[-1].count('★')}/7"])

    def test_plain_pipe_utf8_and_complete_sections(self):
        result = self.run_cli("--full", "--plain", isolated=False,
                              LC_ALL="C", PYTHONUTF8="0", PYTHONIOENCODING="ascii")
        self.assertEqual(result.returncode, 0, result.stderr)
        for title in ("今日总览", "幸运元素", "赛博黄历", "今日签文", "今日寄语", "仅供娱乐"):
            self.assertIn(title, result.stdout)
        self.assertNotIn("\x1b", result.stdout)
        self.assertIn("穷观阵", result.stdout)
        self.assertIn("本座", result.stdout)
        self.assertIn("不宜", result.stdout)
        self.assertNotIn("我", result.stdout)
        self.assertNotIn("🔮", result.stdout)
        self.assertNotIn("★", result.stdout)
        self.assertNotIn("\x1b", self.run_cli().stdout)

    @unittest.skipIf(os.name == "nt", "需要 POSIX 伪终端")
    def test_interactive_followup_menu(self):
        def run_terminal(keys, *args, width=76):
            master, slave = pty.openpty()
            process = None
            chunks = []
            deadline = time.monotonic() + 10
            try:
                terminal_attributes = termios.tcgetattr(slave)
                terminal_attributes[3] &= ~termios.ECHO
                termios.tcsetattr(slave, termios.TCSANOW, terminal_attributes)
                process = subprocess.Popen(
                    [sys.executable, "-B", str(ROOT / "main.py"), *args],
                    env=dict(self.env, TERM="xterm-256color", NO_COLOR="1", COLUMNS=str(width),
                             LC_ALL="C", PYTHONUTF8="0", PYTHONIOENCODING="ascii"),
                    stdin=slave, stdout=slave, stderr=slave,
                )
                os.close(slave)
                slave = None
                if keys:
                    os.write(master, keys)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not select.select([master], [], [], remaining)[0]:
                        self.fail(f"Interactive CLI timed out: {b''.join(chunks).decode('utf-8', 'replace')}")
                    try:
                        chunk = os.read(master, 8192)
                    except OSError as exc:
                        if exc.errno != errno.EIO:
                            raise
                        break
                    if not chunk:
                        break
                    chunks.append(chunk)
                output = b"".join(chunks).decode("utf-8")
                self.assertEqual(process.wait(timeout=2), 0, output)
                return output
            finally:
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait(timeout=2)
                os.close(master)
                if slave is not None:
                    os.close(slave)

        output = run_terminal("1\n1\n2\n3\n清茶\n糕点\n\n".encode("utf-8"))
        self.assertLess(output.index("符卡："), output.index("详卦"))
        self.assertEqual(output.count("今日总览"), 2)
        self.assertIn("今日小任务：", output)
        self.assertIn("二选一", output)
        self.assertRegex(output, r"本座抽得：(?:清茶|糕点)")
        self.assertIn("仅供娱乐", output.split("本座抽得：", 1)[1])

        repeat = run_terminal(b"2\n\n")
        self.assertIn("此卦本座已断", repeat)
        self.assertIn("今日小任务：", repeat)
        narrow = run_terminal("3\n茶\n糕\n\n".encode("utf-8"), width=12)
        self.assertRegex(narrow, r"第一项[^\r\n]*\r?\n返回）：")
        self.assertRegex(narrow, r"第二项[^\r\n]*\r?\n返回）：")

        for args in (("--full",), ("--date", "2026-11-08"), ("--plain",)):
            with self.subTest(args=args):
                self.assertNotIn("二选一", run_terminal(b"", *args))
        self.assertNotIn("二选一", self.run_cli().stdout)

    @unittest.skipIf(os.name == "nt", "需要 POSIX 伪终端")
    def test_tty_ansi_emoji_and_no_color(self):
        for extra, colored in (({}, True), ({"NO_COLOR": "1"}, False), ({"TERM": "dumb"}, False)):
            master, slave = pty.openpty()
            try:
                tty_env = dict(self.env, TERM="xterm-256color", NO_COLOR="")
                tty_env.update(extra)
                proc = subprocess.Popen([sys.executable, "-I", "-B", str(ROOT / "main.py"), "--full", "--date", "2026-11-08"],
                                        env=tty_env, stdout=slave, stderr=slave)
                os.close(slave)
                slave = None
                chunks = []
                while True:
                    try:
                        chunk = os.read(master, 8192)
                    except OSError:
                        break
                    if not chunk:
                        break
                    chunks.append(chunk)
                self.assertEqual(proc.wait(timeout=10), 0)
                output = b"".join(chunks).decode("utf-8")
                self.assertEqual("\x1b[" in output, colored)
                self.assertEqual("🔮" in output, extra.get("TERM") != "dumb")
            finally:
                os.close(master)
                if slave is not None:
                    os.close(slave)

    def test_zero_terminal_columns_use_readable_fallback(self):
        import contextlib
        import io
        from daily_fortune.cli import main

        with patch.dict(os.environ, self.env), \
                patch("shutil.get_terminal_size", return_value=os.terminal_size((0, 0))), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--date", "2026-11-08"]), 0)
        self.assertEqual(len(output.getvalue().splitlines()), 7)

    def test_offline_execution_with_network_functions_blocked(self):
        from daily_fortune.cli import main
        import contextlib
        import io
        with patch.dict(os.environ, self.env), patch("socket.socket", side_effect=AssertionError("network forbidden")), \
                patch("socket.create_connection", side_effect=AssertionError("network forbidden")), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--plain"]), 0)
        self.assertIn("穷观阵已启", output.getvalue())

    def test_identity_private_atomic_and_corruption_never_resets(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            values = list(pool.map(lambda _: load_identity(self.state), range(30)))
        self.assertEqual(len(set(values)), 1)
        key = self.state / "user-id"
        if os.name != "nt":
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.state.stat().st_mode & 0o777, 0o700)
        self.assertEqual(list(self.state.iterdir()), [key])
        key.write_text("broken", encoding="utf-8")
        with self.assertRaises(IdentityError):
            load_identity(self.state)
        self.assertEqual(key.read_text(), "broken")
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)

    @unittest.skipUnless(os.name == "nt", "需要 Windows 用户目录")
    def test_windows_state_directory(self):
        profile = Path(self.temp.name) / "用户"
        local = Path(self.temp.name) / "本地应用"
        with patch.dict(os.environ, USERPROFILE=str(profile), LOCALAPPDATA=str(local),
                        DAILY_FORTUNE_HOME=str(self.state)):
            self.assertEqual(state_directory(), self.state)
            del os.environ["DAILY_FORTUNE_HOME"]
            self.assertEqual(state_directory(), local / "daily-fortune" / "state")
            os.environ["LOCALAPPDATA"] = "relative"
            with self.assertRaises(IdentityError):
                state_directory()
            del os.environ["LOCALAPPDATA"]
            self.assertEqual(state_directory(), profile / "AppData" / "Local" / "daily-fortune" / "state")

    def test_symlink_state_errors(self):
        target = Path(self.temp.name) / "target"
        target.mkdir()
        try:
            self.state.symlink_to(target, target_is_directory=True)
        except OSError as exc:
            if os.name == "nt" and exc.winerror == 1314:
                self.skipTest("Windows 当前用户无法创建符号链接")
            raise
        with self.assertRaises(IdentityError):
            load_identity(self.state)

    @unittest.skipIf(os.name == "nt", "需要 POSIX 目录权限")
    def test_unwritable_state_errors(self):
        self.state.mkdir(mode=0o500)
        try:
            with self.assertRaises(IdentityError):
                load_identity(self.state)
        finally:
            self.state.chmod(0o700)

    def test_state_files_reject_symlinks(self):
        self.state.mkdir()
        target = Path(self.temp.name) / "target"
        target.write_bytes((USER + "\n").encode("ascii"))
        key = self.state / "user-id"
        try:
            key.symlink_to(target)
        except OSError as exc:
            if os.name == "nt" and exc.winerror == 1314:
                self.skipTest("Windows 当前用户无法创建符号链接")
            raise
        with self.assertRaises(IdentityError):
            load_identity(self.state)

        day = date(2026, 11, 8)
        (self.state / f"drawn-{day.isoformat()}").symlink_to(target)
        with self.assertRaises(DrawMemoryError):
            with daily_draw(self.state, day):
                self.fail("state symlink was opened")
        self.assertEqual(target.read_bytes(), (USER + "\n").encode("ascii"))


class LayoutTests(unittest.TestCase):
    def test_known_display_clusters(self):
        self.assertEqual(display_width("中文abc"), 7)
        self.assertEqual(display_width("\x1b[31m中文\x1b[0m"), 4)
        for text, expected in (("e\u0301", 1), ("🔮", 2), ("👩🏽‍💻", 2), ("🇨🇳", 2), ("1️⃣", 2)):
            self.assertEqual(len(list(clusters(text))), 1)
            self.assertEqual(display_width(text), expected)
        self.assertEqual(wrap("中文abc", 4), ["中文", "abc"])
        self.assertEqual(wrap("今天可以读书：读一页。", 12), ["今天可以读", "书：读一页。"])

    def test_windows_from_very_narrow_to_wide(self):
        report = generate(date(2026, 11, 8), USER)
        for width in (2, 8, 12, 20, 31, 32, 40, 60, 80, 120):
            for plain in (False, True):
                result = render(report, width=width, color=True, emoji=True, plain=plain)
                self.assertTrue(all(display_width(line) <= min(width, 78) for line in result.splitlines()),
                                (width, plain))
                if plain:
                    self.assertNotIn("\x1b", result)


if __name__ == "__main__":
    unittest.main()
