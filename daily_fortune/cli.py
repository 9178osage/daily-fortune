"""Command-line interface; help/version never create state."""

import argparse
from contextlib import nullcontext
from datetime import date
import errno
import os
import re
import shutil
import stat
import sys

from . import __version__
from .compact import already_drawn, summarize
from .draw_memory import DrawMemoryError, daily_draw
from .engine import generate
from .followup import show_followups
from .identity import IdentityError, load_identity, state_directory
from .render import render, render_compact, wrap

if os.name == "nt":
    from ._windows import virtual_terminal


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "今日运势：参数错误：%s\n使用 --help 查看帮助。\n" % message)


def parse_date(value):
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("日期应为有效的 YYYY-MM-DD，例如 2026-11-08。") from exc


def _output_pipe_closed(error):
    if isinstance(error, BrokenPipeError):
        return True
    if os.name == "nt" and isinstance(error, OSError) and error.errno == errno.EINVAL:
        # Older Windows Python can expose a closed pipe as EINVAL.
        try:
            return stat.S_ISFIFO(os.fstat(sys.stdout.fileno()).st_mode)
        except OSError:
            pass
    return False


def main(argv=None):
    # Apply to help/version and argument errors as well as the report body.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = Parser(prog="今日运势", description="每天抽一张中文娱乐短签，抽签记录保存在本机。",
                    epilog="每日次数按系统本地日期计算。终端直接运行时可在签后选择小菜单，按回车离开。",
                    add_help=False)
    parser.add_argument("--help", "-h", action="help", help="显示帮助并退出")
    parser.add_argument("--version", action="version", version="今日运势 " + __version__, help="显示版本并退出")
    parser.add_argument("--plain", action="store_true", help="用数字显示星级，关闭 ANSI、Emoji 和签后菜单")
    parser.add_argument("--full", action="store_true", help="查看七项星级、黄历和寄语的详细报告")
    parser.add_argument("--date", type=parse_date, metavar="YYYY-MM-DD", help="查看指定日期的模拟运势")
    args = parser.parse_args(argv)
    try:
        day = args.date or date.today()
        directory = state_directory()
        identity = load_identity(directory)
        tty = sys.stdout.isatty()
        emoji = tty and os.environ.get("TERM") != "dumb"
        color = emoji and not args.plain and not os.environ.get("NO_COLOR")
        colors = virtual_terminal(sys.stdout) if color and os.name == "nt" else nullcontext(color)
        # Python 3.9 can return zero columns for an unconfigured PTY.
        width = shutil.get_terminal_size(fallback=(76, 24)).columns or 76
        draw = nullcontext(True) if args.date or args.full else daily_draw(directory, day)
        with colors as color:
            with draw as first_draw:
                if not first_draw:
                    output = "\n".join(wrap(already_drawn(day, identity), min(78, width))) + "\n"
                elif args.full:
                    output = render(generate(day, identity), width, color=color, plain=args.plain, emoji=emoji)
                else:
                    output = render_compact(summarize(day, identity), width, color=color, plain=args.plain)
                sys.stdout.write(output)
                sys.stdout.flush()
            if tty and sys.stdin.isatty() and not (args.date or args.full or args.plain):
                if hasattr(sys.stdin, "reconfigure"):
                    sys.stdin.reconfigure(encoding="utf-8", errors="surrogateescape")
                show_followups(day, identity, width, color=color, emoji=emoji)
        return 0
    except (IdentityError, DrawMemoryError) as exc:
        print("今日运势：%s" % exc, file=sys.stderr)
        return 1
    except (OSError, UnicodeError) as exc:
        if _output_pipe_closed(exc):
            # Prevent the interpreter's final stdout flush from emitting a traceback.
            try:
                sys.stdout = open(os.devnull, "w", encoding="utf-8")
            except OSError:
                pass
            return 0
        print("今日运势：无法输出报告：%s" % exc, file=sys.stderr)
        return 1
