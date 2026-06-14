"""
updater.py — One-click self-update from GitHub for the desktop app.
Pulls the latest code (git reset --hard origin/main) and restarts the app.
Used by both the Admin and Shop screens' "Update App" button.
"""
import os
import sys
import shutil
import subprocess
import threading
from tkinter import messagebox

from logger import get_logger

log = get_logger(__name__)


def _app_dir() -> str:
    """Folder that holds main.py and the .git repo (this file lives there)."""
    return os.path.dirname(os.path.abspath(__file__))


def run_update(window, status_setter=None) -> None:
    """Confirm, pull the latest code from GitHub, then offer to restart.
    `window` is the Tk root; `status_setter` is an optional callable(str)."""
    if not shutil.which("git"):
        messagebox.showerror(
            "Git Not Found",
            "Git is not installed on this PC.\n\n"
            "Install it once from https://git-scm.com/download/win,\n"
            "then run SETUP_GITHUB.bat in the app folder.")
        return

    app_dir = _app_dir()
    if not os.path.isdir(os.path.join(app_dir, ".git")):
        messagebox.showerror(
            "Not Set Up Yet",
            "Automatic update isn't configured on this PC yet.\n\n"
            "Run GET_UPDATE.bat once in the app folder to connect it,\n"
            "then this button will work.")
        return

    if not messagebox.askyesno(
            "Update App",
            "Download the latest version and restart the app?\n\n"
            "Your bills and balances are safe — updates never change them.",
            icon="question"):
        return

    if status_setter:
        try: status_setter("\U0001f504  Updating…")
        except Exception: pass

    def _do_pull():
        try:
            r1 = subprocess.run(["git", "fetch", "origin", "main"],
                                cwd=app_dir, capture_output=True, text=True, timeout=60)
            if r1.returncode != 0:
                raise RuntimeError(r1.stderr.strip() or "fetch failed")
            r2 = subprocess.run(["git", "reset", "--hard", "origin/main"],
                                cwd=app_dir, capture_output=True, text=True, timeout=60)
            if r2.returncode != 0:
                raise RuntimeError(r2.stderr.strip() or "reset failed")
            window.after(0, lambda: _finish(window, True, ""))
        except Exception as e:                       # noqa: BLE001
            log.warning("Self-update failed: %s", e)
            window.after(0, lambda: _finish(window, False, str(e)))

    threading.Thread(target=_do_pull, daemon=True, name="self-update").start()


def _finish(window, ok: bool, detail: str) -> None:
    if not ok:
        messagebox.showerror(
            "Update Failed",
            f"Could not download the update:\n\n{detail}\n\n"
            "Check the internet connection and try again.")
        return
    if messagebox.askyesno(
            "Update Complete",
            "Update downloaded!\n\nRestart now to start using the new version?",
            icon="info"):
        python = sys.executable
        script = os.path.join(_app_dir(), "main.py")
        try:
            window.destroy()
        except Exception:
            pass
        os.execv(python, [python, script])
