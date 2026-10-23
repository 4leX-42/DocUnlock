"""Self-install for the frozen .exe: one file to hand out, nothing to run first.

Opened from anywhere (USB, Downloads, a share), the .exe copies itself to
%LOCALAPPDATA%\\Programs\\DocUnlock, adds a Start menu shortcut so Windows
search finds it, and relaunches from there. A newer copy opened later
replaces the installed one. Per user, no admin rights. Any failure just runs
the app in place: installing is a convenience, never a reason not to start.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

APP = "DocUnlock"


def _shortcut(target: Path) -> None:
    programs = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    lnk = programs / f"{APP}.lnk"
    if lnk.exists():
        return
    ps = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:DU_LNK);"
        "$s.TargetPath = $env:DU_EXE; $s.WorkingDirectory = $env:DU_DIR;"
        "$s.IconLocation = $env:DU_EXE + ',0';"
        "$s.Description = 'Limpiar y comprimir documentos'; $s.Save()"
    )
    env = dict(os.environ, DU_LNK=str(lnk), DU_EXE=str(target), DU_DIR=str(target.parent))
    # Absolute path: a bare "powershell" is searched first in the .exe's own
    # folder (Downloads, a USB stick), where a planted powershell.exe would run.
    powershell = (Path(os.environ.get("SystemRoot", r"C:\Windows"))
                  / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
    subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-Command", ps],
        env=env, timeout=30, check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _same(a: Path, b: Path) -> bool:
    sa, sb = a.stat(), b.stat()
    return sa.st_size == sb.st_size and int(sa.st_mtime) == int(sb.st_mtime)


def ensure_installed() -> bool:
    """Install or update this .exe for the current user. Returns True when a
    relaunch from the installed copy was started and this process should exit."""
    if not getattr(sys, "frozen", False) or os.name != "nt":
        return False
    try:
        exe = Path(sys.executable).resolve()
        dest = Path(os.environ["LOCALAPPDATA"]) / "Programs" / APP / f"{APP}.exe"
        if exe == dest.resolve():
            _shortcut(dest)
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists() or not _same(exe, dest):
            shutil.copy2(exe, dest)  # fails if the installed copy is open: run in place
        _shortcut(dest)
        # Without the reset the child reuses this process's unpack folder,
        # which the bootloader deletes as soon as we exit.
        env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
        subprocess.Popen([str(dest)], cwd=str(dest.parent), env=env, close_fds=True)
        return True
    except (OSError, KeyError, subprocess.SubprocessError):
        return False
