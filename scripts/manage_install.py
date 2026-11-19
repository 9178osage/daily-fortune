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
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
from typing import Optional
import uuid

WINDOWS = sys.platform == "win32"
if sys.platform == "win32":
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
BACKUP_PREFIX = "daily-fortune-backup-"
TRANSACTION = ".daily-fortune-transaction"
JOURNAL = "journal.json"
INSTALL_SCRIPT = ".\\install.ps1" if WINDOWS else "./install.sh"
REQUIRED = {LAUNCHER.as_posix(), (APP / "main.py").as_posix(), (APP / "daily_fortune/__init__.py").as_posix()}
PACKAGE_FILE = re.compile(re.escape((APP / "daily_fortune").as_posix()) + r"/[A-Za-z_][A-Za-z_0-9]*\.py\Z")
REQUIRED_MODULES = (
    "__init__", "_windows", "cli", "compact", "content", "draw_memory", "engine", "followup", "identity", "render",
)


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
    return sys.platform == "win32" and bool(info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


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


def write_new(path, content, mode, *, sync=False):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(path), flags, mode)
    created = os.fstat(fd)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            if sys.platform != "win32":
                os.fchmod(stream.fileno(), mode)
            if sync:
                os.fsync(stream.fileno())
    except (OSError, KeyboardInterrupt):
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
    safe_parent_chain(source, package)
    required = [source / "main.py", *(package / f"{name}.py" for name in REQUIRED_MODULES)]
    missing = [path.relative_to(source).as_posix() for path in required if not regular(path)]
    if missing:
        raise InstallError("源码不完整或文件不是普通文件：{}".format("、".join(missing)))
    source_files.extend((p, APP / "daily_fortune" / p.name) for p in sorted(package.glob("*.py")))
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


def check_install_target(prefix):
    conflict = shutil.which(COMMAND)
    if conflict:
        raise InstallError("PATH 已有同名命令，拒绝覆盖或遮蔽：{}".format(conflict))
    check_base(prefix)
    safe_parent_chain(prefix, prefix / "bin")
    if exists(prefix / LAUNCHER):
        raise InstallError("命令文件已存在，拒绝覆盖：{}".format(prefix / LAUNCHER))


def install(prefix):
    check_install_target(prefix)
    payloads = application_payloads()
    launcher_content = launcher_bytes(prefix)
    launcher = prefix / LAUNCHER
    made_dirs: list[Path] = []
    written: list[tuple[Path, str]] = []
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
            write_new(target, content, 0o644)
            written.append((target, digest(content)))
        version = verify_application(prefix / APP)
        write_new(launcher, launcher_content, 0o755)
        written.append((launcher, digest(launcher_content)))
        if verify_command([str(launcher), "--version"]) != version:
            raise InstallError("启动器未返回已验证的版本。")
        files = {relative: digest(content) for relative, content in payloads.items()}
        files[LAUNCHER.as_posix()] = digest(launcher_content)
        receipt_data = receipt_bytes(files)
        write_new(prefix / RECEIPT, receipt_data, 0o600)
        written.append((prefix / RECEIPT, digest(receipt_data)))
    except (OSError, InstallError, KeyboardInterrupt):
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


def read_json(path, description):
    if not regular(path):
        raise InstallError("未找到普通{}：{}".format(description, path))
    if path.stat().st_size > 1024 * 1024:
        raise InstallError("{}异常大。".format(description))
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (ValueError, RecursionError) as error:
        raise InstallError("{}损坏：{}".format(description, error)) from error


def read_receipt(path):
    receipt = read_json(path, "安装清单")
    if (not isinstance(receipt, dict) or set(receipt) != {"schema", "files"}
            or type(receipt["schema"]) is not int or receipt["schema"] != 1):
        raise InstallError("安装清单格式不受支持。")
    return checked_hashes(receipt["files"])


def checked_hashes(files) -> dict[str, str]:
    if not isinstance(files, dict):
        raise InstallError("安装清单格式不受支持。")
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
    if sys.platform == "win32":
        lock = base / LOCK_NAME
        if exists(lock) and not regular(lock):
            raise InstallError("安装锁不是普通文件：{}".format(lock))
        with lock.open("a+b") as stream:
            stream.seek(0)
            # Windows accepts locking a byte beyond EOF. Closing the handle
            # releases the lock and leaves the inode for the next process.
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            yield
    else:
        fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)


def check_removable(path):
    info = path.lstat()
    if sys.platform == "win32":
        blocked = stat.S_ISREG(info.st_mode) and info.st_file_attributes & stat.FILE_ATTRIBUTE_READONLY
    else:
        flags = stat.UF_IMMUTABLE | stat.SF_IMMUTABLE | stat.UF_APPEND | stat.SF_APPEND
        blocked = getattr(info, "st_flags", 0) & flags
    if blocked:
        raise InstallError("文件或目录具有只读或不可变标志，尚未卸载：{}".format(path))


def check_file(path, expected):
    if not regular(path) or digest(path.read_bytes()) != expected:
        raise InstallError("文件已改动、缺失或为符号链接：{}".format(path))


def check_application(app, files):
    package = app / "daily_fortune"
    safe_parent_chain(app.parent, package)
    actual: set[str] = set()
    for current, directories, names in os.walk(app, followlinks=False):
        for name in directories:
            path = Path(current) / name
            if path != package:
                raise InstallError("程序目录含未知目录或符号链接：{}".format(path))
        actual.update((Path(current) / name).relative_to(app).as_posix() for name in names)
    expected = {Path(relative).relative_to(APP).as_posix(): value
                for relative, value in files.items() if relative != LAUNCHER.as_posix()}
    if actual != expected.keys():
        raise InstallError("程序文件缺失或含未知文件，请检查 {}。".format(app))
    for relative, value in expected.items():
        check_file(app / relative, value)


def check_installation(prefix, *, removing=False, allow_pending=False):
    base = prefix / BASE
    safe_parent_chain(prefix, base)
    files = read_receipt(prefix / RECEIPT)
    allowed = {"app", "state", "receipt.json"}
    if WINDOWS:
        allowed.update({"bin", LOCK_NAME, BACKUPS})
    if allow_pending:
        allowed.add(TRANSACTION)
    unknown = set(p.name for p in base.iterdir()) - allowed
    if unknown:
        raise InstallError("安装目录含未知文件：{}".format("、".join(sorted(unknown))))
    safe_parent_chain(prefix, prefix / STATE)
    launcher = prefix / LAUNCHER
    safe_parent_chain(prefix, launcher.parent)
    if removing:
        # Verify write and search permission for every unlink/rmdir parent
        # before removing the first file.
        removal_parents = {prefix / Path(relative).parent for relative in files}
        removal_parents.update({base, prefix / APP})
        for parent in sorted(removal_parents):
            safe_parent_chain(prefix, parent)
            if not os.access(parent, os.W_OK | os.X_OK):
                raise InstallError("卸载所需目录不存在或缺少写入、执行权限，尚未删除文件：{}".format(parent))
    check_application(prefix / APP, files)
    check_file(launcher, files[LAUNCHER.as_posix()])
    if removing:
        for path in removal_parents | {prefix / RECEIPT, *(prefix / relative for relative in files)}:
            check_removable(path)
    return files


def uninstall(prefix):
    files = check_installation(prefix, removing=True)
    with prepare_change(prefix) as draft:
        apply_change(prefix, draft, files, new_files=None)
    print("卸载完成。已保留用户数据：{}".format(prefix / STATE))
    print("保留该目录可在重新安装后延续同一用户的每日结果；本工具不会自动删除它。")


def rename_exclusive(source, target):
    if sys.platform != "darwin":
        # Windows rename is exclusive. On other POSIX systems the install lock
        # serializes cooperating callers, and this rejects existing targets.
        if exists(target):
            raise FileExistsError(str(target))
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


def verify_application(app):
    command = [sys.executable, "-I", "-B", str(app / "main.py")]
    with tempfile.TemporaryDirectory(prefix="daily-fortune-verify-") as directory:
        env = dict(os.environ, DAILY_FORTUNE_HOME=directory, COLUMNS="76")
        version = verify_command([*command, "--version"], env)
        preview = verify_command([*command, "--date", "2026-11-08", "--plain"], env)
        if "符卡：" not in preview:
            raise InstallError("程序验证失败：未生成预览短签。")
    return version


def backup_directory(prefix):
    base = prefix / BASE
    if WINDOWS:
        directory = base / BACKUPS
        safe_parent_chain(prefix, directory)
        directory.mkdir(exist_ok=True)
        return directory
    return base.parent


@contextmanager
def prepare_change(prefix):
    with tempfile.TemporaryDirectory(prefix=".daily-fortune-prepare-", dir=backup_directory(prefix)) as directory:
        draft = Path(directory) / "transaction"
        draft.mkdir(mode=0o700)
        yield draft


def change_paths(prefix, old_files, new_files):
    slots = [(prefix / APP, Path(APP.name))]
    launcher = LAUNCHER.as_posix()
    if new_files is None or old_files[launcher] != new_files[launcher]:
        slots.append((prefix / LAUNCHER, LAUNCHER))
    slots.append((prefix / RECEIPT, Path(RECEIPT.name)))
    return slots


def check_slot(path, slot, files):
    if slot == Path(APP.name):
        check_application(path, files)
    elif slot == Path(RECEIPT.name):
        if read_receipt(path) != files:
            raise InstallError("安装清单在操作期间发生变化：{}".format(path))
    else:
        check_file(path, files[LAUNCHER.as_posix()])


def retire_change(prefix, pending, *, keep_backup=False):
    name = BACKUP_PREFIX if keep_backup else ".daily-fortune-cleanup-"
    destination = backup_directory(prefix) / (name + uuid.uuid4().hex)
    # Moving the whole directory is the commit point. Cleanup can be interrupted
    # without leaving a half-written recovery record in the installation.
    rename_exclusive(pending, destination)
    if not keep_backup:
        try:
            shutil.rmtree(destination)
        except OSError as error:
            print("安装变更已完成，暂存目录清理失败：{}（{}）".format(destination, error), file=sys.stderr)
    return destination


def recover_change(prefix):
    pending = prefix / BASE / TRANSACTION
    if not exists(pending):
        return False
    safe_parent_chain(prefix, pending)
    journal = read_json(pending / JOURNAL, "安装恢复记录")
    if (not isinstance(journal, dict) or set(journal) != {"schema", "old", "new"}
            or type(journal["schema"]) is not int or journal["schema"] != 1):
        raise InstallError("安装恢复记录格式不受支持：{}".format(pending))
    old_files = checked_hashes(journal["old"])
    new_files = None if journal["new"] is None else checked_hashes(journal["new"])
    for live, slot in reversed(change_paths(prefix, old_files, new_files)):
        saved = pending / slot
        safe_parent_chain(pending, saved.parent)
        if not exists(saved):
            continue
        safe_parent_chain(prefix, live.parent)
        check_slot(saved, slot, old_files)
        if exists(live):
            staged = pending / "new" / slot
            safe_parent_chain(pending, staged.parent)
            if new_files is None or exists(staged):
                raise InstallError("恢复目标已有文件，已保留备份：{}".format(live))
            check_slot(live, slot, new_files)
            rename_exclusive(live, staged)
        rename_exclusive(saved, live)
    if check_installation(prefix, allow_pending=True) != old_files:
        raise InstallError("恢复后的安装清单校验失败。")
    retire_change(prefix, pending)
    return True


def apply_change(prefix, draft, old_files, new_files: Optional[dict[str, str]], version=None):
    updating = new_files is not None
    if check_installation(prefix, removing=not updating) != old_files:
        raise InstallError("安装内容在验证期间发生变化，请重试。")
    paths = change_paths(prefix, old_files, new_files)
    for _, slot in paths:
        (draft / slot).parent.mkdir(parents=True, exist_ok=True)
    journal = {"schema": 1, "old": old_files, "new": new_files}
    write_new(draft / JOURNAL, json.dumps(journal, ensure_ascii=False).encode("utf-8"), 0o600, sync=True)
    pending = prefix / BASE / TRANSACTION
    rename_exclusive(draft, pending)
    try:
        for live, slot in paths:
            rename_exclusive(live, pending / slot)
            check_slot(pending / slot, slot, old_files)
        if updating:
            for live, slot in paths:
                rename_exclusive(pending / "new" / slot, live)
            if check_installation(prefix, allow_pending=True) != new_files:
                raise InstallError("新安装的清单校验失败。")
            if verify_command([str(prefix / LAUNCHER), "--version"]) != version:
                raise InstallError("启动器未返回暂存版本。")
        return retire_change(prefix, pending, keep_backup=updating)
    except (OSError, InstallError, KeyboardInterrupt) as error:
        if not exists(pending):
            raise
        try:
            recover_change(prefix)
        except (OSError, InstallError, KeyboardInterrupt) as rollback_error:
            raise InstallError("安装变更中断，恢复失败：{}。请检查恢复目录：{}".format(
                rollback_error, pending)) from error
        raise InstallError("{}。已恢复原版本。".format(error or "安装变更被中断")) from error


def update(prefix):
    if sys.platform not in {"darwin", "win32"}:
        raise InstallError("保留备份的原地更新目前支持 macOS 和 Windows。")
    base = prefix / BASE
    launcher = prefix / LAUNCHER
    old_files = check_installation(prefix)
    payloads = application_payloads()
    new_files = {relative: digest(content) for relative, content in payloads.items()}
    launcher_key = LAUNCHER.as_posix()
    launcher_hash = old_files[launcher_key]
    replacement = None
    if not WINDOWS and os.environ.get("PYTHON"):
        candidate = launcher_bytes(prefix)
        if digest(candidate) != launcher_hash:
            replacement = candidate
    if replacement is None:
        verify_command([str(launcher), "--version"])
    else:
        launcher_hash = digest(replacement)
    new_files[launcher_key] = launcher_hash
    if new_files == old_files:
        print("已安装的程序与当前源码一致。")
        return
    if not os.access(base, os.W_OK | os.X_OK):
        raise InstallError("更新所需目录缺少写入、执行权限：{}".format(base))

    with prepare_change(prefix) as draft:
        stage = draft / "new"
        (stage / "app/daily_fortune").mkdir(parents=True)
        for relative, content in payloads.items():
            write_new(stage / Path(relative).relative_to(BASE), content, 0o644)
        write_new(stage / RECEIPT.name, receipt_bytes(new_files), 0o600)
        if replacement is not None:
            staged_launcher = stage / LAUNCHER
            staged_launcher.parent.mkdir()
            write_new(staged_launcher, replacement, 0o755)
        version = verify_application(stage / "app")
        backup = apply_change(prefix, draft, old_files, new_files, version)

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
            if isinstance(stream, io.TextIOWrapper):
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
        pending = exists(prefix / BASE / TRANSACTION)
        if action is install and WINDOWS:
            # A conflict in an unrelated directory must not create an install lock.
            if not (pending and regular(prefix / LOCK_NAME)):
                check_install_target(prefix)
            prefix.mkdir(parents=True, exist_ok=True)
        if action is install and not WINDOWS and not pending:
            action(prefix)
        else:
            with installation_lock(prefix):
                if recover_change(prefix):
                    print("已恢复上次未完成的安装变更。")
                action(prefix)
    except (OSError, InstallError) as error:
        print("{}失败：{}".format(label, error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("{}已中断。".format(label), file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
