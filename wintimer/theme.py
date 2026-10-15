"""浅色主题：配色、字体与通用小控件。"""

import tkinter as tk

# --- 配色（白底浅色风格）---
BG = "#f4f6f9"          # 窗口底色
PANEL = "#ffffff"       # 卡片
PANEL_HI = "#eef1f6"    # 输入框 / 标签底色
FG = "#1b2431"          # 主文字
MUTED = "#6d7684"       # 次要文字
ACCENT = "#1677ff"      # 主色
ACCENT_HI = "#3f8cff"
OK = "#12a150"          # 运行中
WARN = "#e5484d"        # 暂停 / 到点
BTN = "#eef1f6"
BTN_HI = "#e0e5ec"
DISABLED = "#b6bcc6"
BORDER = "#dfe3ea"

UI_FAMILY = "Microsoft YaHei UI"
MONO_CANDIDATES = ("Cascadia Mono", "Consolas", "Lucida Console", "Courier New")

_mono_cache = None


def mono_family(root=None):
    """选一个可用的等宽字体，避免数字跳动。"""
    global _mono_cache
    if _mono_cache:
        return _mono_cache
    families = set()
    try:
        import tkinter.font as tkfont

        families = set(tkfont.families(root))
    except Exception:
        pass
    for name in MONO_CANDIDATES:
        if name in families:
            _mono_cache = name
            break
    else:
        _mono_cache = "Consolas"
    return _mono_cache


def ui_font(size=10, weight="normal"):
    return (UI_FAMILY, size, weight)


def mono_font(size=40, weight="bold"):
    return (mono_family(), size, weight)


class FlatButton(tk.Button):
    """扁平按钮，带悬停反馈。"""

    def __init__(self, master, text, command, *, primary=False, danger=False,
                 width=None, font=None, bg=None, **kwargs):
        if primary:
            base, hover, fg = ACCENT, ACCENT_HI, "#ffffff"
        elif danger:
            base, hover, fg = WARN, "#ef6a6f", "#ffffff"
        else:
            base, hover, fg = (bg or BTN), BTN_HI, FG
        super().__init__(
            master,
            text=text,
            command=command,
            font=font or ui_font(10),
            bg=base,
            fg=fg,
            activebackground=hover,
            activeforeground=fg,
            relief="flat",
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            padx=14,
            pady=7,
            width=width,
            disabledforeground=DISABLED,
            **kwargs,
        )
        self._base = base
        self._hover = hover
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event):
        if self["state"] != "disabled":
            self.configure(bg=self._hover)

    def _on_leave(self, _event):
        if self["state"] != "disabled":
            self.configure(bg=self._base)


class Chip(tk.Label):
    """可点击的小标签（预设时长、模式切换等）。"""

    def __init__(self, master, text, command, *, font=None, padx=10, pady=4):
        super().__init__(
            master,
            text=text,
            font=font or ui_font(9),
            bg=PANEL_HI,
            fg=MUTED,
            padx=padx,
            pady=pady,
            cursor="hand2",
        )
        self.command = command
        self._active = False
        self.bind("<Button-1>", lambda _e: self.command())
        self.bind("<Enter>", lambda _e: self._hover(True))
        self.bind("<Leave>", lambda _e: self._hover(False))

    def _hover(self, on):
        if self._active:
            return
        self.configure(bg=BTN_HI if on else PANEL_HI)

    def set_active(self, active):
        self._active = bool(active)
        self.configure(
            bg=ACCENT if active else PANEL_HI,
            fg="#ffffff" if active else MUTED,
        )
