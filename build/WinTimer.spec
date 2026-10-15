# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：单文件、无控制台窗口。

打包命令（在项目根目录）：
    python -m PyInstaller --noconfirm --clean build/WinTimer.spec
"""

from pathlib import Path

ROOT = Path(SPECPATH).parent          # noqa: F821  (PyInstaller 注入)
ICON = ROOT / "assets" / "icon.ico"
VERSION_FILE = ROOT / "build" / "version_info.txt"

a = Analysis(  # noqa: F821
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ICON), ".")] if ICON.exists() else [],
    hiddenimports=["wintimer", "wintimer.app", "wintimer.notify", "wintimer.settings", "wintimer.theme"],
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
    name="计时器",
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
