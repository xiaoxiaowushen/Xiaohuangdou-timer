"""WinTimer 入口脚本（PyInstaller 打包入口）。"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _run():
    from wintimer.app import main

    main()


if __name__ == "__main__":
    try:
        _run()
    except Exception:
        detail = traceback.format_exc()
        try:
            from pathlib import Path

            log = Path(os.environ.get("APPDATA", os.path.expanduser("~"))) / "WinTimer" / "error.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(detail, encoding="utf-8")
        except Exception:
            pass
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, detail[-800:], "计时器 启动失败", 0x10)
        except Exception:
            pass
        raise
