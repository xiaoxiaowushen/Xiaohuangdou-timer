"""自动驱动界面走一遍各状态并截图，用于开发自检。

用法： python tools/uitest.py
"""

import ctypes
import ctypes.wintypes as wt
import sys
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import ImageGrab  # noqa: E402

from wintimer import notify  # noqa: E402
from wintimer.app import TimerApp, enable_dpi_awareness  # noqa: E402

OUT = ROOT / "_probe"
OUT.mkdir(exist_ok=True)

enable_dpi_awareness()
user32 = ctypes.windll.user32


def find_window(title_part):
    hits = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _l):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if title_part in buf.value and user32.IsWindowVisible(hwnd):
                hits.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return hits


def grab(hwnd, name):
    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    img = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True)
    img.save(OUT / name)
    print(f"  shot {name} {img.size}")


def grab_full(name):
    img = ImageGrab.grab(all_screens=True)
    img.save(OUT / name)
    print(f"  shot {name} {img.size} (full screen)")


def main():
    root = tk.Tk()
    app = TimerApp(root)
    root.update()

    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            root.update()
            time.sleep(0.02)

    main_hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()

    print("[1] 秒表：初始")
    app.set_mode("stopwatch")
    pump(0.4)
    grab(main_hwnd, "ui_1_sw_idle.png")

    print("[2] 秒表：运行 1.4s")
    app._toggle_primary()
    pump(1.4)
    grab(main_hwnd, "ui_2_sw_running.png")

    print("[3] 秒表：暂停")
    app._toggle_primary()
    pump(0.4)
    grab(main_hwnd, "ui_3_sw_paused.png")
    print("   显示 =", app.sw_display.cget("text"), "| 状态 =", app.sw_status.cget("text"))

    print("[4] 倒计时：1 小时 0 分 5 秒（自定义时/分/秒）")
    app.set_mode("countdown")
    app.hour_var.set("1")
    app.min_var.set("0")
    app.sec_var.set("5")
    app._sync_countdown_total()
    pump(0.4)
    grab(main_hwnd, "ui_4_cd_setup.png")
    print("   显示 =", app.cd_display.cget("text"))
    print("[4b] 用 3 秒快速验证到点提醒")
    app.hour_var.set("0")
    app.min_var.set("0")
    app.sec_var.set("3")
    app._sync_countdown_total()
    app._toggle_primary()
    pump(0.6)
    grab(main_hwnd, "ui_5_cd_running.png")
    pump(3.6)
    print("   显示 =", app.cd_display.cget("text"), "| 状态 =", app.cd_status.cget("text"))
    grab(main_hwnd, "ui_6_cd_done.png")

    alerts = find_window("时间到")
    if alerts:
        grab(alerts[0], "ui_7_alert.png")
    else:
        print("   ! 没有弹出提醒窗")
    grab_full("ui_8_screen.png")

    print("[5] 直接测试系统通知")
    print("   ", notify.show_toast("计时器", "自检：系统通知通道"))
    grab_full("ui_9_after_toast.png")

    root.destroy()
    print("done")


if __name__ == "__main__":
    main()
