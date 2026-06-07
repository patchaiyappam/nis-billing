"""
NIS Admin - Desktop Shortcut Installer
Run this once to create the "NIS Admin" shortcut on your Desktop.
Double-click this file or run: python INSTALL_ADMIN_SHORTCUT.py
"""
import os
import sys
import subprocess

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
TARGET  = os.path.join(SRC_DIR, "START_ADMIN_MODE.bat")
ICON    = os.path.join(SRC_DIR, "app_icon.ico")

# ── 1. Find Desktop (handles OneDrive redirection) ──────────────────────────
try:
    import ctypes.wintypes
    buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
    ctypes.windll.shell32.SHGetFolderPathW(None, 0x0000, None, 0, buf)
    desktop = buf.value  # CSIDL_DESKTOP
except Exception:
    desktop = os.path.join(os.environ.get("USERPROFILE", "C:\\Users\\ADMIIN"), "Desktop")

if not os.path.isdir(desktop):
    # Try OneDrive Desktop
    onedrive = os.environ.get("OneDrive", "")
    alt = os.path.join(onedrive, "Desktop")
    if os.path.isdir(alt):
        desktop = alt

shortcut_path = os.path.join(desktop, "NIS Admin.lnk")

# ── 2. Create shortcut via PowerShell (no extra libs needed) ─────────────────
ps = (
    f'$ws = New-Object -ComObject WScript.Shell; '
    f'$sc = $ws.CreateShortcut("{shortcut_path}"); '
    f'$sc.TargetPath = "{TARGET}"; '
    f'$sc.WorkingDirectory = "{SRC_DIR}"; '
    f'$sc.IconLocation = "{ICON}"; '
    f'$sc.Description = "New Indian Steel - Admin Mode"; '
    f'$sc.Save()'
)
result = subprocess.run(
    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
    capture_output=True, text=True
)

if os.path.exists(shortcut_path):
    print(f"✓ Shortcut created at:\n  {shortcut_path}")
else:
    print("✗ Shortcut creation failed.")
    print(result.stderr)
    sys.exit(1)

# ── 3. Install / verify Python packages ──────────────────────────────────────
print("\nChecking Python packages...")
packages = ["reportlab", "openpyxl", "supabase"]
missing = []
for pkg in packages:
    try:
        __import__(pkg)
        print(f"  ✓ {pkg}")
    except ImportError:
        print(f"  ✗ {pkg} (missing)")
        missing.append(pkg)

if missing:
    print(f"\nInstalling missing packages: {', '.join(missing)}")
    subprocess.run([sys.executable, "-m", "pip", "install"] + missing + ["--disable-pip-version-check"])
    print("Done.")

# ── 4. Launch the app ─────────────────────────────────────────────────────────
print("\nLaunching NIS Admin...")
env = os.environ.copy()
env["NIS_MODE"] = "admin"
subprocess.Popen([sys.executable, os.path.join(SRC_DIR, "main.py")], env=env)

print("\n✓ All done! 'NIS Admin' shortcut is on your Desktop.")
input("\nPress Enter to close...")
