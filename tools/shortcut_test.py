"""验证快捷方式创建（含 AUMID）是否可用，并把结果落在 _probe 下。

用法： python tools/shortcut_test.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from wintimer import APP_ID  # noqa: E402
from wintimer import notify  # noqa: E402

OUT = ROOT / "_probe" / "shortcut_test.lnk"
target = ROOT / "assets" / "icon.ico"   # 只是当个存在的目标文件用

if OUT.exists():
    OUT.unlink()

ok = notify.create_shortcut(
    OUT,
    target,
    description="计时器 WinTimer 测试",
    icon=ROOT / "assets" / "icon.ico",
    aumid=APP_ID,
)
print("create_shortcut ->", ok)
print("文件存在 ->", OUT.exists(), OUT.stat().st_size if OUT.exists() else "-", "字节")

if OUT.exists():
    raw = OUT.read_bytes()
    needle = APP_ID.encode("utf-16-le")
    print("AUMID 写入 ->", needle in raw, f"({APP_ID})")
    print("目标路径写入 ->", str(target).encode("utf-16-le") in raw)
