# -*- mode: python ; coding: utf-8 -*-
"""安装包打包配置：把 计时器.exe 和图标一起塞进一个自包含的安装程序。

打包命令（先打好主程序，产物在 dist\\计时器.exe）：
    python -m PyInstaller --noconfirm --clean build/Setup.spec
"""

from pathlib import Path

ROOT = Path(SPECPATH).parent          # noqa: F821  (PyInstaller 注入)
ICON = ROOT / "assets" / "icon.ico"
APP_EXE = ROOT / "dist" / "计时器.exe"
VERSION_FILE = ROOT / "build" / "version_info.txt"

if not APP_EXE.exists():
    raise SystemExit("先打包主程序：dist\\计时器.exe 不存在")

a = Analysis(  # noqa: F821
    [str(ROOT / "installer" / "setup_app.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(APP_EXE), "."),
        (str(ICON), "."),
    ],
    hiddenimports=["wintimer", "wintimer.notify", "wintimer.settings", "wintimer.theme", "wintimer.app"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "PIL", "numpy", "pandas", "matplotlib", "scipy", "pytest", "pip",
        "setuptools", "pkg_resources", "unittest", "test", "distutils",
        "email", "http", "xml", "sqlite3", "multiprocessing", "asyncio",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="计时器安装程序",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ICON) if ICON.exists() else None,
    version=str(VERSION_FILE) if VERSION_FILE.exists() else None,
)
