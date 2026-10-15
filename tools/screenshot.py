"""抓取指定标题窗口的截图。

优先用 PrintWindow（不受遮挡影响），黑屏时退回「提到最前 + 屏幕截取」。

用法： python tools/screenshot.py "标题片段" 输出.png
"""

import ctypes
import ctypes.wintypes as wt
import sys
import time

from PIL import Image, ImageGrab, ImageStat

try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

target = sys.argv[1] if len(sys.argv) > 1 else "计时器"
out = sys.argv[2] if len(sys.argv) > 2 else "_probe/shot.png"


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


def print_window(hwnd, width, height):
    hdc = user32.GetWindowDC(hwnd)
    memdc = gdi32.CreateCompatibleDC(hdc)
    bitmap = gdi32.CreateCompatibleBitmap(hdc, width, height)
    gdi32.SelectObject(memdc, bitmap)
    ok = user32.PrintWindow(hwnd, memdc, 2)  # PW_RENDERFULLCONTENT
    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = width
    info.bmiHeader.biHeight = -height
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = 0
    buf = ctypes.create_string_buffer(width * height * 4)
    got = gdi32.GetDIBits(memdc, bitmap, 0, height, buf, ctypes.byref(info), 0)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memdc)
    user32.ReleaseDC(hwnd, hdc)
    if not ok or not got:
        return None
    return Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1).convert("RGB")


def is_blank(img):
    stat = ImageStat.Stat(img.convert("L"))
    return stat.stddev[0] < 1.5


found = []


@ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def enum_proc(hwnd, _lparam):
    length = user32.GetWindowTextLengthW(hwnd)
    if length and user32.IsWindowVisible(hwnd):
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if target in buf.value:
            found.append((buf.value, hwnd))
    return True


user32.EnumWindows(enum_proc, 0)
if not found:
    print("window not found:", target)
    raise SystemExit(1)

title, hwnd = found[0]
rect = wt.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
width, height = rect.right - rect.left, rect.bottom - rect.top
print("found:", title, width, "x", height)

img = print_window(hwnd, width, height)
if img is None or is_blank(img):
    user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0040)
    time.sleep(1.2)
    img = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True)
    print("(PrintWindow 不可用，改用屏幕截取)")

img.save(out)
print("saved", out, img.size)
