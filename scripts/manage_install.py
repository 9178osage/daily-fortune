#!/usr/bin/env python3
"""Install, update, and remove the offline CLI using verified receipts."""
import sys

if sys.version_info < (3, 9):
    print("需要 Python 3.9 或更新版本：https://www.python.org/downloads/", file=sys.stderr)
    sys.exit(1)

import argparse
from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import tempfile

WINDOWS = os.name == "nt"
if WINDOWS:
    import msvcrt
else:
    import fcntl

COMMAND = "daily-fortune" if WINDOWS else "今日运势"
BASE = Path() if WINDOWS else Path("share/daily-fortune")
APP = BASE / "app"
STATE = BASE / "state"
RECEIPT = BASE / "receipt.json"
LAUNCHER = Path("bin") / (COMMAND + ".cmd" if WINDOWS else COMMAND)
LOCK_NAME = ".install.lock"
BACKUPS = "backups"
INSTALL_SCRIPT = ".\\install.ps1" if WINDOWS else "./install.sh"
REQUIRED = {LAUNCHER.as_posix(), (APP / "main.py").as_posix(), (APP / "daily_fortune/__init__.py").as_posix()}
PACKAGE_FILE = re.compile(re.escape((APP / "daily_fortune").as_posix()) + r"/[A-Za-z_][A-Za-z_0-9]*\.py\Z")


class InstallError(Exception):
    pass


def exists(path):
    return os.path.lexists(str(path))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular(path):
    """lstat intentionally refuses links, devices, and dangling links."""
    try:
        info = path.lstat()
        return stat.S_ISREG(info.st_mode) and not reparse_point(info)
    except FileNotFoundError:
        return False


def reparse_point(info):
    # Windows junctions and other name substitutions need not be symlinks.
    return bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def safe_parent_chain(prefix, path):
    """The chosen prefix is canonical; nothing below it may be a symlink."""
    relative = path.relative_to(prefix)
    current = prefix
    for part in relative.parts:
        current = current / part
        if exists(current):
            info = current.lstat()
            if not stat.S_ISDIR(info.st_mode) or reparse_point(info):
                raise InstallError("目录不是普通目录或为符号链接，已停止：{}".format(current))


def make_dir(prefix, path, made, mode=0o755):
    safe_parent_chain(prefix, path)
    missing = []
    current = path
    while not exists(current):
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir(mode=mode if directory == path else 0o755)
        made.append(directory)


def write_new(path, content, mode):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(path), flags, mode)
    created = os.fstat(fd)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            if not WINDOWS:
                os.fchmod(stream.fileno(), mode)
    except OSError:
        # A failed write may have left a partial file before it was receipted.
        if exists(path) and path.lstat().st_ino == created.st_ino:
            path.unlink()
        raise


def prefix_path(value):
    # Canonicalize the user-chosen root once; receipt paths stay strictly relative.
    return Path(value).expanduser().resolve()


def check_base(prefix):
    base = prefix / BASE
    safe_parent_chain(prefix, base)
    if base.exists():
        allowed = {"state", "bin", LOCK_NAME, BACKUPS} if WINDOWS else {"state"}
        unknown = set(p.name for p in base.iterdir()) - allowed
        if unknown:
            raise InstallError("安装目录已有文件，拒绝覆盖：{}（{}）".format(base, "、".join(sorted(unknown))))
    state = prefix / STATE
    safe_parent_chain(prefix, state)


def application_payloads():
    source = Path(__file__).resolve().parents[1]
    source_files = [(source / "main.py", APP / "main.py")]
    package = source / "daily_fortune"
    source_files.extend((p, APP / "daily_fortune" / p.name) for p in sorted(package.glob("*.py")))
    if not regular(source / "main.py") or not regular(package / "__init__.py"):
        raise InstallError("源码不完整：需要 main.py 和 daily_fortune/__init__.py。")
    payloads = {}
    for original, relative in source_files:
        if not regular(original) or (relative != APP / "main.py" and not PACKAGE_FILE.fullmatch(relative.as_posix())):
            raise InstallError("源码包含不支持的文件：{}".format(original))
        payloads[relative.as_posix()] = original.read_bytes()
    return payloads


def receipt_bytes(files):
    receipt = {"schema": 1, "files": files}
    return (json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def launcher_bytes(prefix):
    if WINDOWS:
        # ASCII source and a relative path preserve Unicode and spaces in the
        # installation path at any cmd.exe code page.
        launcher = (
            '@echo off\r\n'
            'setlocal DisableDelayedExpansion\r\n'
            'set NoDefaultCurrentDirectoryInExePath=1\r\n'
            'set "DAILY_FORTUNE_HOME=%~dp0..\\state"\r\n'
            'python.exe -I -B -c "import sys; raise SystemExit(not sys.version_info >= (3, 9))" >nul 2>&1\r\n'
            'if not errorlevel 1 goto use-python\r\n'
            'py.exe -3 -I -B -c "import sys; raise SystemExit(not sys.version_info >= (3, 9))" >nul 2>&1\r\n'
            'if not errorlevel 1 goto use-py\r\n'
            'echo Daily Fortune requires Python 3.9 or newer. 1>&2\r\n'
            'exit /b 1\r\n'
            ':use-python\r\n'
            'python.exe -I -B "%~dp0..\\app\\main.py" %*\r\n'
            'exit /b %errorlevel%\r\n'
            ':use-py\r\n'
            'py.exe -3 -I -B "%~dp0..\\app\\main.py" %*\r\n'
            'exit /b %errorlevel%\r\n'
        )
        return launcher.encode("ascii")
    python = str(Path(sys.executable).resolve())
    launcher = (
        "#!/bin/sh\n"
        "# Installed by Daily Fortune; user data is kept on uninstall.\n"
        "export DAILY_FORTUNE_HOME={}\n"
        "if [ ! -x {} ]; then\n"
        "  printf '%s\\n' '今日运势：原 Python 解释器已不可用，请重新安装程序。' >&2\n"
        "  exit 1\n"
        "fi\n"
        "exec {} -I -B {} \"$@\"\n"
    ).format(shlex.quote(str(prefix / STATE)), shlex.quote(python),
             shlex.quote(python), shlex.quote(str(prefix / APP / "main.py")))
    return launcher.encode("utf-8")


def install(prefix):
    payloads = application_payloads()
    conflict = shutil.which(COMMAND)
    if conflict:
        raise InstallError("PATH 已有同名命令，拒绝覆盖或遮蔽：{}".format(conflict))
    check_base(prefix)
    safe_parent_chain(prefix, prefix / "bin")
    if exists(prefix / LAUNCHER):
        raise InstallError("命令文件已存在，拒绝覆盖：{}".format(prefix / LAUNCHER))
    payloads[LAUNCHER.as_posix()] = launcher_bytes(prefix)
    made_dirs = []
    written = []
    try:
        make_dir(prefix, prefix / "bin", made_dirs)
        make_dir(prefix, prefix / BASE, made_dirs)
        make_dir(prefix, prefix / STATE, made_dirs, mode=0o700)
        # An existing app is rejected, including an empty directory.
        (prefix / APP).mkdir()
        made_dirs.append(prefix / APP)
        (prefix / APP / "daily_fortune").mkdir()
        made_dirs.append(prefix / APP / "daily_fortune")
        for relative, content in payloads.items():
            target = prefix / relative
            write_new(target, content, 0o755 if relative == LAUNCHER.as_posix() else 0o644)
            written.append((target, digest(content)))
        receipt_data = receipt_bytes({relative: digest(content) for relative, content in payloads.items()})
        write_new(prefix / RECEIPT, receipt_data, 0o600)
        written.append((prefix / RECEIPT, digest(receipt_data)))
    except OSError:
        # Roll back only files this invocation created and whose bytes still match.
        for path, expected in reversed(written):
            if regular(path) and digest(path.read_bytes()) == expected:
                path.unlink()
        for path in reversed(made_dirs):
            try:
                path.rmdir()
            except OSError:
                pass
        raise
    print("安装完成：{}".format(prefix / LAUNCHER))
    if WINDOWS:
        print("运行：& {}".format(powershell_quote(prefix / LAUNCHER)))
        print("要在当前 PowerShell 中使用 daily-fortune 命令，执行：")
        print("  $env:Path = {} + ';' + $env:Path".format(powershell_quote(prefix / "bin")))
        print("卸载：在源码目录执行 .\\uninstall.ps1 -Prefix {}（保留用户标识）。".format(powershell_quote(prefix)))
        return
    path_entries = [str(Path(item).expanduser().resolve()) for item in os.environ.get("PATH", "").split(os.pathsep) if item]
    if str(prefix / "bin") not in path_entries:
        print("该目录尚未加入 PATH。当前终端执行：")
        print("  export PATH={}:\"$PATH\"".format(shlex.quote(str(prefix / "bin"))))
        print("若希望新终端生效，请自行将上一行加入 ~/.zshrc（安装器不会修改 shell 配置）。")
    print("运行：{}".format(COMMAND))
    print("卸载：在源码目录执行 sh uninstall.sh --prefix {}（保留用户标识）。".format(shlex.quote(str(prefix))))


def powershell_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InstallError("安装清单存在重复字段。")
        result[key] = value
    return result


def read_receipt(prefix):
    safe_parent_chain(prefix, prefix / BASE)
    receipt_file = prefix / RECEIPT
    if not regular(receipt_file):
        raise InstallError("未找到普通安装清单：{}".format(receipt_file))
    if receipt_file.stat().st_size > 1024 * 1024:
        raise InstallError("安装清单异常大。")
    try:
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (ValueError, UnicodeError) as error:
        raise InstallError("安装清单损坏：{}".format(error))
    if (not isinstance(receipt, dict) or set(receipt) != {"schema", "files"}
            or type(receipt["schema"]) is not int or receipt["schema"] != 1
            or not isinstance(receipt["files"], dict)):
        raise InstallError("安装清单格式不受支持。")
    files = receipt["files"]
    if not REQUIRED.issubset(files):
        raise InstallError("安装清单缺少必要文件。")
    for relative, expected in files.items():
        if relative not in REQUIRED and not PACKAGE_FILE.fullmatch(relative):
            raise InstallError("安装清单路径越界或不受支持：{}".format(relative))
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise InstallError("安装清单校验值损坏。")
    return files


@contextmanager
def installation_lock(prefix):
    base = prefix / BASE
    safe_parent_chain(prefix, base)
    if not base.is_dir():
        raise InstallError("没有找到安装目录，请先执行 {}：{}".format(INSTALL_SCRIPT, base))
    if WINDOWS:
        lock = base / LOCK_NAME
        if exists(lock) and not regular(lock):
            raise InstallError("安装锁不是普通文件：{}".format(lock))
        with lock.open("a+b") as stream:
            stream.seek(0)
            # Windows accepts locking a byte beyond EOF. Closing the handle
            # releases the lock and leaves the inode for the next process.
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            yield
        return
    fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def check_installation(prefix, *, removing=False):
    files = read_receipt(prefix)
    base = prefix / BASE
    allowed = {"app", "state", "receipt.json"}
    if WINDOWS:
        allowed.update({"bin", LOCK_NAME, BACKUPS})
    unknown = set(p.name for p in base.iterdir()) - allowed
    if unknown:
        raise InstallError("安装目录含未知文件：{}".format("、".join(sorted(unknown))))
    safe_parent_chain(prefix, prefix / STATE)
    safe_parent_chain(prefix, prefix / APP / "daily_fortune")
    if removing:
        # Verify write and search permission for every unlink/rmdir parent
        # before removing the first file.
        removal_parents = {prefix / Path(relative).parent for relative in files}
        removal_parents.update({base, prefix / APP})
        for parent in sorted(removal_parents):
            safe_parent_chain(prefix, parent)
            if not os.access(parent, os.W_OK | os.X_OK):
                raise InstallError("卸载所需目录不存在或缺少写入、执行权限，尚未删除文件：{}".format(parent))
    actual_files = set()
    allowed_dirs = {prefix / APP, prefix / APP / "daily_fortune"}
    for current, directories, names in os.walk(str(prefix / APP), followlinks=False):
        for name in directories:
            path = Path(current) / name
            if reparse_point(path.lstat()) or path.is_symlink() or path not in allowed_dirs:
                raise InstallError("程序目录含未知目录或符号链接：{}".format(path))
        for name in names:
            actual_files.add((Path(current) / name).relative_to(prefix).as_posix())
    expected_app_files = set(files) - {LAUNCHER.as_posix()}
    if actual_files != expected_app_files:
        raise InstallError("程序文件缺失或含未知文件，请检查 {}。".format(prefix / APP))
    # Finish all validation before removing anything. The receipt itself cannot
    # authenticate its own bytes; a strict schema/path allowlist constrains it.
    for relative, expected in files.items():
        path = prefix / relative
        safe_parent_chain(prefix, path.parent)
        if not regular(path) or digest(path.read_bytes()) != expected:
            raise InstallError("文件已改动、缺失或为符号链接：{}".format(path))
    return files


def uninstall(prefix):
    files = check_installation(prefix, removing=True)
    for relative, expected in files.items():
        if relative == LAUNCHER.as_posix():
            continue
        path = prefix / relative
        # A second check also catches common concurrent edits during removal.
        if not regular(path) or digest(path.read_bytes()) != expected:
            raise InstallError("卸载期间文件发生变化，已停止：{}".format(path))
        path.unlink()
    (prefix / APP / "daily_fortune").rmdir()
    (prefix / APP).rmdir()
    (prefix / RECEIPT).unlink()
    # Keep the command until the application and receipt have been removed.
    # Preflight cannot make this multi-file operation atomic against concurrent
    # edits, chmod, ACL or filesystem-flag changes; do not run concurrent installers.
    launcher = prefix / LAUNCHER
    if not regular(launcher) or digest(launcher.read_bytes()) != files[LAUNCHER.as_posix()]:
        raise InstallError("卸载期间启动器发生变化，已保留：{}".format(launcher))
    launcher.unlink()
    print("卸载完成。已保留用户数据：{}".format(prefix / STATE))
    print("保留该目录可在重新安装后延续同一用户的每日结果；本工具不会自动删除它。")


def rename_exclusive(source, target):
    if WINDOWS:
        # On Windows os.rename fails if the destination already exists.
        os.rename(source, target)
        return
    # Darwin's renamex_np with RENAME_EXCL refuses to replace an existing
    # destination even if it appeared after our checks. See sys/stdio.h.
    rename = ctypes.CDLL(None, use_errno=True).renamex_np
    rename.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    if rename(os.fsencode(source), os.fsencode(target), 0x00000004) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(source), None, str(target))


def verify_command(command, env=None):
    try:
        result = subprocess.run(command, env=env, capture_output=True, encoding="utf-8", timeout=15)
    except (subprocess.TimeoutExpired, UnicodeError, OSError) as error:
        raise InstallError("程序验证失败：{}".format(error)) from error
    if result.returncode or not result.stdout.strip():
        detail = result.stderr.strip() or "程序没有返回有效输出"
        raise InstallError("程序验证失败：{}".format(detail))
    return result.stdout


def update(prefix):
    if sys.platform not in {"darwin", "win32"}:
        raise InstallError("保留备份的原地更新目前支持 macOS 和 Windows。")
    base = prefix / BASE
    launcher = prefix / LAUNCHER
    old_files = check_installation(prefix)
    payloads = application_payloads()
    new_files = {relative: digest(content) for relative, content in payloads.items()}
    new_files[LAUNCHER.as_posix()] = old_files[LAUNCHER.as_posix()]
    verify_command([str(launcher), "--version"])
    if new_files == old_files:
        print("已安装的程序与当前源码一致。")
        return
    if not os.access(base, os.W_OK | os.X_OK):
        raise InstallError("更新所需目录缺少写入、执行权限：{}".format(base))

    backup_parent = base / BACKUPS if WINDOWS else base.parent
    if WINDOWS:
        safe_parent_chain(prefix, backup_parent)
        backup_parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".daily-fortune-update-", dir=backup_parent) as directory:
        stage = Path(directory)
        (stage / "app/daily_fortune").mkdir(parents=True)
        for relative, content in payloads.items():
            write_new(stage / Path(relative).relative_to(BASE), content, 0o644)
        write_new(stage / RECEIPT.name, receipt_bytes(new_files), 0o600)
        command = [sys.executable, "-I", "-B", str(stage / "app/main.py")]
        env = dict(os.environ, DAILY_FORTUNE_HOME=str(stage / "test-state"))
        version = verify_command([*command, "--version"], env)
        verify_command([*command, "--date", "2026-11-08", "--plain"], env)

        if check_installation(prefix) != old_files:
            raise InstallError("安装内容在验证期间发生变化，请重试。")
        backup = Path(tempfile.mkdtemp(prefix="daily-fortune-backup-", dir=backup_parent))
        moves = (
            (base / APP.name, backup / APP.name),
            (base / RECEIPT.name, backup / RECEIPT.name),
            (stage / APP.name, base / APP.name),
            (stage / RECEIPT.name, base / RECEIPT.name),
        )
        attempted = []
        try:
            for source, target in moves:
                attempted.append((source, target))
                rename_exclusive(source, target)
            if check_installation(prefix) != new_files or verify_command([str(launcher), "--version"]) != version:
                raise InstallError("启动器未返回暂存版本。")
        except (OSError, InstallError, KeyboardInterrupt) as error:
            try:
                for source, target in reversed(attempted):
                    # Include the in-flight move in case Ctrl+C arrived just
                    # after rename completed.
                    if exists(target) and not exists(source):
                        rename_exclusive(target, source)
                if check_installation(prefix) != old_files:
                    raise InstallError("恢复后的安装清单校验失败。")
                backup.rmdir()
            except (OSError, InstallError, KeyboardInterrupt) as rollback_error:
                raise InstallError("更新中断，无法自动恢复：{}。请检查备份目录：{}".format(rollback_error, backup)) from error
            raise InstallError("{}。已恢复原版本。".format(error or "更新被中断")) from error

    print("更新完成。")
    print("原版本备份：{}".format(backup))


def default_prefix():
    if not WINDOWS:
        return Path.home() / ".local"
    local_app_data = os.environ.get("LOCALAPPDATA")
    app_data = Path(local_app_data) if local_app_data else Path.home() / "AppData/Local"
    if not app_data.is_absolute():
        raise InstallError("LOCALAPPDATA 必须是绝对路径。")
    return app_data / COMMAND


def main():
    if WINDOWS:
        # Windows PowerShell and redirected output can use a legacy code page.
        for stream in (sys.stdout, sys.stderr):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="今日运势的离线用户目录安装器")
    actions = {"install": ("安装", install), "uninstall": ("卸载", uninstall), "update": ("更新", update)}
    parser.add_argument("action", choices=actions)
    location = r"%LOCALAPPDATA%\daily-fortune" if WINDOWS else "~/.local"
    parser.add_argument("--prefix", help="安装根目录（默认 {}）".format(location))
    args = parser.parse_args()
    label, action = actions[args.action]
    try:
        prefix = prefix_path(args.prefix if args.prefix is not None else default_prefix())
        if prefix == prefix.parent:
            raise InstallError("不能以系统根目录作为安装根目录。")
        if action is install and WINDOWS:
            prefix.mkdir(parents=True, exist_ok=True)
            with installation_lock(prefix):
                action(prefix)
        elif action is install:
            action(prefix)
        else:
            with installation_lock(prefix):
                action(prefix)
    except (OSError, InstallError) as error:
        print("{}失败：{}".format(label, error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
