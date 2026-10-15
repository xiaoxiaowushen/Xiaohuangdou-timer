"""WinTimer 主界面：秒表 + 倒计时。"""

import ctypes
import threading
import time
import tkinter as tk
from tkinter import font as tkfont

from . import APP_NAME, __version__
from . import notify
from . import settings as settings_mod
from . import theme as T

TICK_MS = 40
PRESETS = [(0, 5, "5 分"), (0, 10, "10 分"), (0, 25, "25 分"), (0, 30, "30 分"),
           (1, 0, "1 小时"), (2, 0, "2 小时")]


# ------------------------------------------------------------------ 计时模型

class Stopwatch:
    """正计时：perf_counter 计时，暂停时冻结。"""

    def __init__(self):
        self.elapsed = 0.0
        self._started_at = None

    @property
    def running(self):
        return self._started_at is not None

    def value(self):
        if self.running:
            return self.elapsed + (time.perf_counter() - self._started_at)
        return self.elapsed

    def start(self):
        if not self.running:
            self._started_at = time.perf_counter()

    def pause(self):
        if self.running:
            self.elapsed = self.value()
            self._started_at = None

    def reset(self):
        self.elapsed = 0.0
        self._started_at = None


class Countdown:
    """倒计时：用墙钟时间做截止点，休眠唤醒后依然准确。"""

    def __init__(self, total=0.0):
        self.total = float(total)
        self.remaining = float(total)
        self._deadline = None
        self.finished = False

    @property
    def running(self):
        return self._deadline is not None

    def value(self):
        if self.running:
            return max(0.0, self._deadline - time.time())
        return max(0.0, self.remaining)

    def set_total(self, total):
        self.total = float(total)
        self.remaining = float(total)
        self._deadline = None
        self.finished = False

    def start(self):
        if self.remaining <= 0:
            self.remaining = self.total
        if self.remaining <= 0:
            return False
        self.finished = False
        self._deadline = time.time() + self.remaining
        return True

    def pause(self):
        if self.running:
            self.remaining = self.value()
            self._deadline = None

    def reset(self):
        self._deadline = None
        self.remaining = self.total
        self.finished = False

    def check_finished(self):
        """到点返回 True，只触发一次。"""
        if self.running and self.value() <= 0:
            self._deadline = None
            self.remaining = 0.0
            if not self.finished:
                self.finished = True
                return True
        return False


def duration_label(seconds: float) -> str:
    """把秒数说成人话：3 秒 / 1 分 30 秒 / 25 分钟 / 1 小时。"""
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours} 小时")
    if minutes:
        parts.append(f"{minutes} 分")
    if secs:
        parts.append(f"{secs} 秒")
    return " ".join(parts) or "0 秒"


def fmt_clock(seconds: float, centis: bool = False) -> str:
    seconds = max(0.0, seconds)
    if centis:
        total_cs = int(seconds * 100)
        cs = total_cs % 100
        total_s = total_cs // 100
        h, rem = divmod(total_s, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}.{cs:02d}"
    total_s = int(seconds + 0.5) if seconds > 0 else 0
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def flash_taskbar(window):
    """任务栏图标闪烁，窗口被挡住时也能注意到。"""
    try:
        class FLASHWINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_uint),
                ("hwnd", ctypes.c_void_p),
                ("dwFlags", ctypes.c_uint),
                ("uCount", ctypes.c_uint),
                ("dwTimeout", ctypes.c_uint),
            ]

        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 0x00000003 | 0x0000000C, 6, 0)
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
    except Exception:
        pass


# ------------------------------------------------------------------- 界面

class TimerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = settings_mod.load()
        self.stopwatch = Stopwatch()
        self.countdown = Countdown(0)
        self.mode = self.cfg.get("mode", "stopwatch")
        self._alert = None
        self._notify_status = "系统通知：未测试"

        root.title(APP_NAME)
        root.configure(bg=T.BG)
        root.resizable(False, False)
        self._set_icon()
        self._build()
        self.set_mode(self.mode, initial=True)
        self._restore_geometry()
        self._bind_keys()

        self.apply_topmost(self.cfg.get("topmost", True))
        self.root.after(80, self._maybe_register_aumid)
        self.root.after(TICK_MS, self._tick)

    # ------------------------------------------------------------ 构建界面
    def _set_icon(self, window=None):
        try:
            import sys
            from pathlib import Path

            window = window or self.root
            candidates = []
            if getattr(sys, "frozen", False):
                candidates.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "icon.ico")
            candidates.append(Path(__file__).resolve().parent.parent / "assets" / "icon.ico")
            for path in candidates:
                if path.exists():
                    window.iconbitmap(default=str(path))
                    return
        except Exception:
            pass

    def _build(self):
        pad = tk.Frame(self.root, bg=T.BG, padx=14, pady=12)
        pad.pack(fill="both", expand=True)

        # 模式切换
        seg = tk.Frame(pad, bg=T.BG)
        seg.pack(fill="x", pady=(0, 10))
        self.chip_stopwatch = T.Chip(seg, "秒表", lambda: self.set_mode("stopwatch"), font=T.ui_font(10, "bold"))
        self.chip_stopwatch.pack(side="left")
        self.chip_countdown = T.Chip(seg, "倒计时", lambda: self.set_mode("countdown"), font=T.ui_font(10, "bold"))
        self.chip_countdown.pack(side="left", padx=(6, 0))

        self.topmost_chip = T.Chip(seg, "置顶", self._toggle_topmost, font=T.ui_font(9, "bold"))
        self.topmost_chip.pack(side="right")

        card = tk.Frame(pad, bg=T.PANEL)
        card.pack(fill="both", expand=True)

        # 秒表面板
        self.sw_frame = tk.Frame(card, bg=T.PANEL, padx=12, pady=8)
        tk.Frame(self.sw_frame, bg=T.PANEL, height=2).pack(fill="both", expand=True)
        self.sw_display = tk.Label(self.sw_frame, text="00:00.00", font=T.mono_font(38), bg=T.PANEL, fg=T.FG)
        self.sw_display.pack()
        self.sw_status = tk.Label(self.sw_frame, text="已停止", font=T.ui_font(9), bg=T.PANEL, fg=T.MUTED)
        self.sw_status.pack(pady=(2, 0))
        tk.Frame(self.sw_frame, bg=T.PANEL, height=2).pack(fill="both", expand=True)

        # 倒计表面板
        self.cd_frame = tk.Frame(card, bg=T.PANEL, padx=12, pady=8)
        self.cd_display = tk.Label(self.cd_frame, text="05:00", font=T.mono_font(38), bg=T.PANEL, fg=T.FG)
        self.cd_display.pack()
        self.cd_status = tk.Label(self.cd_frame, text="设置时长后点开始", font=T.ui_font(9), bg=T.PANEL, fg=T.MUTED)
        self.cd_status.pack(pady=(2, 0))

        setup = tk.Frame(self.cd_frame, bg=T.PANEL)
        setup.pack(pady=(8, 0))
        self.hour_var = tk.StringVar(value=str(int(self.cfg.get("countdown_hours", 0))))
        self.min_var = tk.StringVar(value=str(int(self.cfg.get("countdown_minutes", 5))))
        self.sec_var = tk.StringVar(value=str(int(self.cfg.get("countdown_seconds", 0))))
        vcmd = (self.root.register(self._validate_digits), "%P")

        unit = dict(font=T.ui_font(9), bg=T.PANEL, fg=T.MUTED)
        self.hour_spin = self._spin(setup, self.hour_var, 0, 99, vcmd)
        self.hour_spin.pack(side="left")
        tk.Label(setup, text="时", **unit).pack(side="left", padx=(3, 8))
        self.min_spin = self._spin(setup, self.min_var, 0, 59, vcmd)
        self.min_spin.pack(side="left")
        tk.Label(setup, text="分", **unit).pack(side="left", padx=(3, 8))
        self.sec_spin = self._spin(setup, self.sec_var, 0, 59, vcmd)
        self.sec_spin.pack(side="left")
        tk.Label(setup, text="秒", **unit).pack(side="left", padx=(3, 0))

        presets = tk.Frame(self.cd_frame, bg=T.PANEL)
        presets.pack(pady=(6, 0))
        for hours, minutes, label in PRESETS:
            T.Chip(presets, label, lambda h=hours, m=minutes: self._apply_preset(h, m),
                   font=T.ui_font(8)).pack(side="left", padx=2)

        # 控制按钮
        controls = tk.Frame(pad, bg=T.BG)
        controls.pack(fill="x", pady=(12, 0))
        self.main_btn = T.FlatButton(controls, "开始", self._toggle_primary, primary=True, font=T.ui_font(11, "bold"))
        self.main_btn.pack(side="left", fill="x", expand=True)
        self.reset_btn = T.FlatButton(controls, "重置", self._reset)
        self.reset_btn.pack(side="left", padx=(8, 0))

        # 底部状态
        footer = tk.Frame(pad, bg=T.BG)
        footer.pack(fill="x", pady=(10, 0))
        self.status = tk.Label(footer, text="空格 开始/暂停 · Ctrl+R 重置", font=T.ui_font(8),
                               bg=T.BG, fg=T.MUTED, anchor="w")
        self.status.pack(side="left")
        T.Chip(footer, "测试通知", self._test_notify, font=T.ui_font(8)).pack(side="right")

    def _spin(self, parent, var, lo, hi, vcmd):
        return tk.Spinbox(
            parent, from_=lo, to=hi, textvariable=var, width=4, justify="center",
            font=T.mono_font(11, "normal"), bg=T.PANEL_HI, fg=T.FG, buttonbackground=T.BTN,
            insertbackground=T.FG, relief="flat", bd=0, highlightthickness=0,
            validate="key", validatecommand=vcmd, readonlybackground=T.PANEL_HI,
        )

    @staticmethod
    def _validate_digits(proposed):
        return proposed == "" or (proposed.isdigit() and len(proposed) <= 3)

    def _restore_geometry(self):
        pos = self.cfg.get("window_pos") or ""
        current = self.mode
        heights = {}
        width = 0
        # 两种模式内容高度不同，各自记下来，切换时窗口跟着变
        for mode in ("stopwatch", "countdown"):
            self.set_mode(mode)
            self.root.update_idletasks()
            width = max(width, self.root.winfo_reqwidth())
            heights[mode] = max(170, self.root.winfo_reqheight())
        self._width = max(360, width)
        self._heights = heights
        if current == "countdown":
            self._sync_countdown_total()
        self.set_mode(current)
        self.root.update_idletasks()
        self.root.minsize(self._width, min(heights.values()))

        geom = f"{self._width}x{heights[current]}"
        if pos:
            geom += pos
        else:
            screen_w = self.root.winfo_screenwidth()
            geom += f"+{max(0, screen_w - self._width - 80)}+60"
        self.root.geometry(geom)

    def apply_mode_size(self):
        heights = getattr(self, "_heights", None)
        if not heights:
            return
        height = heights.get(self.mode)
        if height:
            self.root.geometry(f"{self._width}x{height}")

    def _bind_keys(self):
        self.root.bind("<space>", self._on_space)
        self.root.bind("<Control-r>", lambda _e: self._reset())
        self.root.bind("<Control-R>", lambda _e: self._reset())
        self.root.bind("<Escape>", lambda _e: self._close_alert())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_space(self, _event):
        focused = self.root.focus_get()
        if isinstance(focused, (tk.Entry, tk.Spinbox)):
            return None
        self._toggle_primary()
        return "break"

    # --------------------------------------------------------------- 状态
    def apply_topmost(self, value):
        self.root.attributes("-topmost", bool(value))
        if getattr(self, "topmost_chip", None) is not None:
            self.topmost_chip.set_active(bool(value))

    def _toggle_topmost(self):
        self.cfg["topmost"] = not self.cfg.get("topmost", True)
        self.apply_topmost(self.cfg["topmost"])
        self._save()

    def set_mode(self, mode, initial=False):
        self.mode = mode
        self.cfg["mode"] = mode
        if mode == "stopwatch":
            self.cd_frame.pack_forget()
            self.sw_frame.pack(fill="x")
        else:
            self.sw_frame.pack_forget()
            self.cd_frame.pack(fill="x")
            if initial:
                self._sync_countdown_total()
        self.chip_stopwatch.set_active(mode == "stopwatch")
        self.chip_countdown.set_active(mode == "countdown")
        if not initial:
            self.root.update_idletasks()
            self.apply_mode_size()
            self._refresh_buttons()
            self._render()

    # ------------------------------------------------------- 交互动作
    def _apply_preset(self, hours, minutes):
        if self.countdown.running:
            return
        self.hour_var.set(str(hours))
        self.min_var.set(str(minutes))
        self.sec_var.set("0")
        self._sync_countdown_total()
        self._render()

    def _sync_countdown_total(self):
        total = self._input_seconds()
        if total > 0:
            self.countdown.set_total(total)

    def _input_seconds(self) -> int:
        def read(var, hi):
            try:
                value = int(var.get() or 0)
            except (ValueError, tk.TclError):
                value = 0
            return max(0, min(hi, value))

        hours = read(self.hour_var, 99)
        minutes = read(self.min_var, 59)
        seconds = read(self.sec_var, 59)
        return hours * 3600 + minutes * 60 + seconds

    def _toggle_primary(self):
        if self.mode == "stopwatch":
            if self.stopwatch.running:
                self.stopwatch.pause()
            else:
                self.stopwatch.start()
        else:
            if self.countdown.running:
                self.countdown.pause()
            elif self.countdown.finished or self.countdown.value() <= 0:
                total = self._input_seconds()
                if total <= 0:
                    self._flash_status("请先设置倒计时时长")
                    return
                self.countdown.set_total(total)
                self.countdown.start()
            else:
                if not self.countdown.start():
                    self._flash_status("请先设置倒计时时长")
                    return
        self._refresh_buttons()
        self._render()

    def _reset(self):
        if self.mode == "stopwatch":
            self.stopwatch.reset()
        else:
            self.countdown.reset()
            self._sync_countdown_total()
        self._refresh_buttons()
        self._render()

    def _refresh_buttons(self):
        if self.mode == "stopwatch":
            running = self.stopwatch.running
            started = self.stopwatch.value() > 0
            self.main_btn.configure(text="暂停" if running else ("继续" if started else "开始"))
        else:
            running = self.countdown.running
            paused = not running and 0 < self.countdown.value() < self.countdown.total
            self.main_btn.configure(text="暂停" if running else ("继续" if paused else "开始"))
        state = "disabled" if (self.mode == "countdown" and self.countdown.running) else "normal"
        for widget in (self.hour_spin, self.min_spin, self.sec_spin):
            widget.configure(state=state)

    def _flash_status(self, text, ms=2500):
        self.status.configure(text=text, fg=T.WARN)
        self.root.after(ms, lambda: self.status.configure(text="空格 开始/暂停 · Ctrl+R 重置", fg=T.MUTED))

    # ------------------------------------------------------------ 渲染
    def _render(self):
        if self.mode == "stopwatch":
            value = self.stopwatch.value()
            self.sw_display.configure(text=fmt_clock(value, centis=True))
            if self.stopwatch.running:
                self.sw_status.configure(text="计时中…", fg=T.OK)
            elif value > 0:
                self.sw_status.configure(text="已暂停", fg=T.WARN)
            else:
                self.sw_status.configure(text="已停止", fg=T.MUTED)
        else:
            value = self.countdown.value()
            finished = self.countdown.finished and value <= 0
            if finished:
                color = T.WARN
            elif self.countdown.running:
                color = T.ACCENT
            else:
                color = T.FG
            self.cd_display.configure(text=fmt_clock(value, centis=False), fg=color)
            if finished:
                self.cd_status.configure(text="时间到！", fg=T.WARN)
            elif self.countdown.running:
                self.cd_status.configure(text="倒计时中…", fg=T.OK)
            elif 0 < value < self.countdown.total:
                self.cd_status.configure(text="已暂停", fg=T.WARN)
            else:
                self.cd_status.configure(text="设置时长后点开始", fg=T.MUTED)

    def _tick(self):
        # 两个计时器都在跑，只管画面上的那个
        if self.countdown.check_finished():
            self._on_countdown_finished()
        if self.mode == "stopwatch" and self.stopwatch.running:
            self._refresh_buttons()
        if self.mode == "countdown":
            self._refresh_buttons()
        self._render()
        self.root.after(TICK_MS, self._tick)

    # ------------------------------------------------------------ 提醒
    def _on_countdown_finished(self):
        label = duration_label(self.countdown.total)
        title = "时间到"
        toast_title = "⏰ 时间到"
        message = f"你设置的 {label}倒计时已结束"

        ok = False
        detail = "系统通知已关闭"
        if self.cfg.get("notify_toast", True):
            ok, detail = notify.show_toast(toast_title, message)
        self._notify_status = "系统通知：正常" if ok else f"系统通知失败（{detail}）"

        if self.cfg.get("notify_toast", True) and not ok:
            self._flash_status("系统通知发送失败，已改用弹窗提醒", 6000)

        flash_taskbar(self.root)
        if ok and not self.cfg.get("notify_popup", False):
            self.status.configure(text=self._notify_status, fg=T.MUTED)
            return

        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self._show_alert(title, message)
        if self.cfg.get("topmost", True):
            self.root.after(400, lambda: self.apply_topmost(True))

    def _show_alert(self, title, message):
        if self._alert is not None and self._alert.winfo_exists():
            self._alert.destroy()
        top = tk.Toplevel(self.root)
        self._alert = top
        top.title(title)
        top.configure(bg=T.PANEL)
        top.resizable(False, False)
        top.attributes("-topmost", True)
        self._set_icon(top)

        body = tk.Frame(top, bg=T.PANEL, padx=22, pady=18)
        body.pack(fill="both", expand=True)
        tk.Label(body, text=title, font=T.ui_font(15, "bold"), bg=T.PANEL, fg=T.WARN).pack(anchor="w")
        tk.Label(body, text=message, font=T.ui_font(10), bg=T.PANEL, fg=T.FG, wraplength=260,
                 justify="left").pack(anchor="w", pady=(8, 14))
        T.FlatButton(body, "知道了", self._close_alert, primary=True,
                     font=T.ui_font(10, "bold")).pack(fill="x")

        top.update_idletasks()
        px, py = self.root.winfo_rootx(), self.root.winfo_rooty()
        top.geometry(f"+{px + 40}+{py + 40}")
        top.lift()
        top.focus_force()
        top.bind("<Return>", lambda _e: self._close_alert())
        top.bind("<Escape>", lambda _e: self._close_alert())
        self._beep_alarm()

    def _beep_alarm(self):
        def worker():
            try:
                import winsound

                for _ in range(3):
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                    time.sleep(0.45)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _close_alert(self):
        if self._alert is not None and self._alert.winfo_exists():
            self._alert.destroy()
        self._alert = None

    def _test_notify(self):
        def worker():
            notify.ensure_shortcut(force=True)
            ok, detail = notify.show_toast("计时器", "通知测试：能看到这条就说明系统通知正常 ✅")
            self.root.after(0, lambda: self._flash_status(
                "测试通知已发送" if ok else f"通知发送失败：{detail}", 8000))

        self._flash_status("正在发送测试通知…", 8000)
        threading.Thread(target=worker, daemon=True).start()

    def _maybe_register_aumid(self):
        """首次运行：写入带 AUMID 的开始菜单快捷方式，让通知显示为“计时器”。"""
        import sys

        if not getattr(sys, "frozen", False):
            return
        if self.cfg.get("aumid_registered"):
            return

        def worker():
            ok = notify.ensure_shortcut()
            if ok:
                self.cfg["aumid_registered"] = True
                self.root.after(0, self._save)

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------ 收尾
    def _save(self):
        self.cfg["mode"] = self.mode
        try:
            self.cfg["countdown_hours"] = int(self.hour_var.get() or 0)
            self.cfg["countdown_minutes"] = int(self.min_var.get() or 0)
            self.cfg["countdown_seconds"] = int(self.sec_var.get() or 0)
        except (ValueError, AttributeError):
            pass
        try:
            self.cfg["window_pos"] = f"+{self.root.winfo_x()}+{self.root.winfo_y()}"
        except Exception:
            pass
        settings_mod.save(self.cfg)

    def _on_close(self):
        self._save()
        self.root.destroy()


def enable_dpi_awareness():
    """让高分屏下界面清晰（不做的话 Windows 会把窗口拉伸放大）。"""
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def main():
    enable_dpi_awareness()
    root = tk.Tk()
    TimerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
