"""计时器 安装 / 卸载向导。

打包后是一个自包含的 计时器安装程序.exe：
    计时器安装程序.exe                 打开安装界面
    计时器安装程序.exe --uninstall     卸载界面（安装时也会拷贝一份到安装目录）
    计时器安装程序.exe --auto --target <目录>   静默安装（自测用）

自测（不打包）：
    python installer/setup_app.py --auto --payload dist\\计时器.exe --target .tmp\\install_test
"""

from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import winreg
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tkinter as tk  # noqa: E402
from tkinter import filedialog, messagebox  # noqa: E402

from wintimer import APP_ID, APP_NAME, EXE_NAME, UNINST_NAME, __version__  # noqa: E402
from wintimer import notify  # noqa: E402
from wintimer.app import enable_dpi_awareness  # noqa: E402

UNINST_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\WinTimer"
MOVEFILE_DELAY_UNTIL_REBOOT = 0x4

# 与主程序一致的浅色配色
BG = "#f4f6f9"
PANEL = "#ffffff"
FG = "#1b2431"
MUTED = "#6d7684"
ACCENT = "#1677ff"
ACCENT_HI = "#3f8cff"
BTN = "#eef1f6"
BTN_HI = "#e0e5ec"
OK = "#12a150"
WARN = "#e5484d"
UI = "Microsoft YaHei UI"


# ------------------------------------------------------------------ 路径工具

def default_target() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / "Programs" / APP_NAME


def shell_folder(name: str, fallback: Path) -> Path:
    """从注册表取桌面/开始菜单等真实路径（兼容 OneDrive 重定向）。"""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        ) as key:
            value, _ = winreg.QueryValueEx(key, name)
            if value:
                return Path(value)
    except OSError:
        pass
    return fallback


def desktop_dir() -> Path:
    return shell_folder("Desktop", Path(os.path.expanduser("~")) / "Desktop")


def start_menu_dir() -> Path:
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def payload_path() -> Path | None:
    """找到要安装的 WinTimer.exe：打包后在 _MEIPASS，开发时在 dist/。"""
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / EXE_NAME)
    candidates.append(Path(sys.executable).parent / EXE_NAME)
    candidates.append(ROOT / "dist" / EXE_NAME)
    candidates.append(ROOT / ".tmp" / "smoke" / "dist" / EXE_NAME)
    for path in candidates:
        if path.exists() and path.name.lower() != Path(sys.executable).name.lower():
            return path
    return None


def self_exe() -> Path | None:
    """安装时把本程序复制成 Uninstall.exe；开发模式下没有可复制的 exe。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    return None


# ------------------------------------------------------------------ 安装动作

def kill_running_app() -> None:
    try:
        subprocess.run(
            ["taskkill", "/IM", EXE_NAME, "/F"],
            capture_output=True,
            creationflags=0x08000000,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def write_uninstall_registry(target: Path, size_kb: int) -> bool:
    exe = target / EXE_NAME
    uninst = target / UNINST_NAME
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINST_KEY) as key:
            values = {
                "DisplayName": APP_NAME,
                "DisplayVersion": __version__,
                "Publisher": "WinTimer",
                "DisplayIcon": str(exe),
                "InstallLocation": str(target),
                "UninstallString": f'"{uninst}" --uninstall',
                "QuietUninstallString": f'"{uninst}" --uninstall --auto',
                "EstimatedSize": size_kb,
                "NoModify": 1,
                "NoRepair": 1,
            }
            for name, value in values.items():
                kind = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
                winreg.SetValueEx(key, name, 0, kind, value)
        return True
    except OSError:
        return False


def remove_uninstall_registry() -> None:
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINST_KEY)
    except OSError:
        pass


def install(payload: Path, target: Path, *, desktop=True, start_menu=True,
            copy_uninstaller=True, log=print) -> bool:
    target.mkdir(parents=True, exist_ok=True)
    dest = target / EXE_NAME

    kill_running_app()
    shutil.copy2(payload, dest)
    log(f"已复制主程序到 {dest}")

    icon = dest
    if start_menu:
        lnk = start_menu_dir() / f"{APP_NAME}.lnk"
        ok = notify.create_shortcut(lnk, dest, workdir=target, description=APP_NAME,
                                    icon=icon, aumid=APP_ID)
        log(f"开始菜单快捷方式：{'成功' if ok else '失败'}")
    if desktop:
        lnk = desktop_dir() / f"{APP_NAME}.lnk"
        ok = notify.create_shortcut(lnk, dest, workdir=target, description=APP_NAME,
                                    icon=icon, aumid=APP_ID)
        log(f"桌面快捷方式：{'成功' if ok else '失败'}")

    if copy_uninstaller:
        src = self_exe()
        if src and src.resolve() != (target / UNINST_NAME).resolve():
            try:
                shutil.copy2(src, target / UNINST_NAME)
                log("已写入卸载程序 Uninstall.exe")
            except OSError as exc:
                log(f"卸载程序写入失败：{exc}")
        elif not src:
            log("开发模式：跳过卸载程序")

    size_kb = sum(f.stat().st_size for f in target.glob("*") if f.is_file()) // 1024
    log("注册表卸载项：" + ("成功" if write_uninstall_registry(target, size_kb) else "失败（可忽略）"))
    return True


def _schedule_delete(path: Path) -> None:
    """自己正在运行、删不掉的 exe 交给系统重启后删除。"""
    try:
        ctypes.windll.kernel32.MoveFileExW(str(path), None, MOVEFILE_DELAY_UNTIL_REBOOT)
    except Exception:
        pass


def uninstall(target: Path, *, log=print) -> bool:
    kill_running_app()
    for folder in (desktop_dir(), start_menu_dir()):
        lnk = folder / f"{APP_NAME}.lnk"
        try:
            if lnk.exists():
                lnk.unlink()
                log(f"已删除快捷方式 {lnk}")
        except OSError as exc:
            log(f"快捷方式删除失败 {lnk}: {exc}")

    remove_uninstall_registry()
    log("已移除注册表卸载项")

    current = Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None
    leftovers = []
    if target.exists():
        for item in sorted(target.rglob("*"), reverse=True):
            try:
                if item.is_dir():
                    item.rmdir()
                else:
                    item.unlink()
                log(f"已删除 {item.name}")
            except OSError:
                leftovers.append(item)
        try:
            target.rmdir()
        except OSError:
            leftovers.append(target)

    for item in leftovers:
        if item.is_file() and current and item.resolve() == current:
            _schedule_delete(item)
            log("卸载程序自身将在重启后删除")
        else:
            log(f"未能删除：{item}")
    return True


# ------------------------------------------------------------------ 界面

def launch_app(target: Path) -> None:
    exe = target / EXE_NAME
    if exe.exists():
        try:
            subprocess.Popen([str(exe)], cwd=str(target),
                             creationflags=0x00000008 | 0x08000000)  # DETACHED | NO_WINDOW
        except OSError:
            pass


class Setup(tk.Tk):
    def __init__(self, payload: Path | None, uninstall_mode: bool,
                 target_override: Path | None = None, desktop: bool = True, start_menu: bool = True):
        super().__init__()
        self.payload = payload
        self.uninstall_mode = uninstall_mode
        self.desktop = desktop
        self.start_menu = start_menu
        self.target = Path(target_override) if target_override else default_target()
        self.title(f"{APP_NAME} {'卸载' if uninstall_mode else '安装'}")
        self.configure(bg=BG)
        self._set_icon()

        if uninstall_mode:
            self._build_uninstall()
        else:
            self._build_install()

        # 按内容定窗口大小，再居中（高 DPI 下也合适）
        self.update_idletasks()
        self.resizable(False, False)
        min_width = 560 if not uninstall_mode else 520
        self._center(max(min_width, self.winfo_reqwidth()), self.winfo_reqheight())

    def _set_icon(self):
        for path in (Path(getattr(sys, "_MEIPASS", ROOT)) / "icon.ico", ROOT / "assets" / "icon.ico"):
            if path.exists():
                try:
                    self.iconbitmap(default=str(path))
                except tk.TclError:
                    pass
                return

    def _center(self, width, height):
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{width}x{height}+{(screen_w - width) // 2}+{(screen_h - height) // 3}")

    # ------------------------------------------------------------ 安装界面
    def _build_install(self):
        pad = tk.Frame(self, bg=BG, padx=22, pady=18)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text=f"{APP_NAME}", font=(UI, 16, "bold"), bg=BG, fg=FG).pack(anchor="w")
        tk.Label(pad, text="秒表 + 倒计时，到点用 Windows 通知提醒你。", font=(UI, 9),
                 bg=BG, fg=MUTED).pack(anchor="w", pady=(2, 16))

        tk.Label(pad, text="安装位置", font=(UI, 9), bg=BG, fg=MUTED).pack(anchor="w")
        row = tk.Frame(pad, bg=BG)
        row.pack(fill="x", pady=(4, 14))
        self.path_var = tk.StringVar(value=str(self.target))
        entry = tk.Entry(row, textvariable=self.path_var, font=(UI, 9), bg=PANEL, fg=FG,
                         relief="flat", highlightthickness=1, highlightbackground="#dfe3ea",
                         highlightcolor=ACCENT, insertbackground=FG)
        entry.pack(side="left", fill="x", expand=True, ipady=5)
        browse = tk.Button(row, text="浏览…", font=(UI, 9), bg=BTN, fg=FG, relief="flat", bd=0,
                           activebackground=BTN_HI, padx=12, pady=5, cursor="hand2",
                           command=self._browse)
        browse.pack(side="left", padx=(8, 0))

        self.desktop_var = tk.BooleanVar(value=True)
        self.menu_var = tk.BooleanVar(value=True)
        self.run_var = tk.BooleanVar(value=True)
        for text, var in (
            ("创建桌面快捷方式", self.desktop_var),
            ("创建开始菜单快捷方式（系统通知需要）", self.menu_var),
            ("安装完成后立即运行", self.run_var),
        ):
            tk.Checkbutton(pad, text=text, variable=var, font=(UI, 9), bg=BG, fg=FG,
                           activebackground=BG, activeforeground=FG, selectcolor=PANEL,
                           bd=0, highlightthickness=0, cursor="hand2").pack(anchor="w", pady=1)

        self.status = tk.Label(pad, text="", font=(UI, 9), bg=BG, fg=MUTED, wraplength=500,
                               justify="left")
        self.status.pack(anchor="w", pady=(16, 0))

        buttons = tk.Frame(self, bg=BG, padx=22, pady=14)
        buttons.pack(fill="x", side="bottom")
        self.install_btn = tk.Button(buttons, text="安装", font=(UI, 11, "bold"), bg=ACCENT,
                                     fg="#ffffff", activebackground=ACCENT_HI, activeforeground="#ffffff",
                                     relief="flat", bd=0, padx=26, pady=8, cursor="hand2",
                                     command=self._do_install)
        self.install_btn.pack(side="right")
        tk.Button(buttons, text="取消", font=(UI, 10), bg=BTN, fg=FG, activebackground=BTN_HI,
                  relief="flat", bd=0, padx=18, pady=8, cursor="hand2",
                  command=self.destroy).pack(side="right", padx=(0, 8))

    def _browse(self):
        chosen = filedialog.askdirectory(initialdir=str(self.target.parent), title="选择安装位置")
        if chosen:
            self.path_var.set(str(Path(chosen) / APP_NAME))

    def _do_install(self):
        if self.payload is None:
            messagebox.showerror("安装失败", f"安装包里找不到 {EXE_NAME}。", parent=self)
            return
        target = Path(self.path_var.get())
        self.install_btn.configure(state="disabled", text="安装中…")
        self.status.configure(text="正在安装…", fg=MUTED)
        self.update_idletasks()
        lines = []
        try:
            install(self.payload, target, desktop=self.desktop_var.get(),
                    start_menu=self.menu_var.get(), log=lines.append)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("安装失败", str(exc), parent=self)
            self.install_btn.configure(state="normal", text="安装")
            return
        self.status.configure(text="\n".join(lines[-2:]), fg=OK)
        self.update_idletasks()
        if self.run_var.get():
            launch_app(target)
        messagebox.showinfo("安装完成", f"{APP_NAME} 已安装到：\n{target}", parent=self)
        self.destroy()

    # ------------------------------------------------------------ 卸载界面
    def _build_uninstall(self):
        pad = tk.Frame(self, bg=BG, padx=22, pady=18)
        pad.pack(fill="both", expand=True)
        tk.Label(pad, text=f"卸载 {APP_NAME}", font=(UI, 16, "bold"), bg=BG, fg=FG).pack(anchor="w")
        tk.Label(pad, text=f"将从下面这个位置移除程序、快捷方式和卸载项：\n{self.target}",
                 font=(UI, 9), bg=BG, fg=MUTED, justify="left").pack(anchor="w", pady=(10, 16))
        self.status = tk.Label(pad, text="", font=(UI, 9), bg=BG, fg=MUTED, wraplength=500,
                               justify="left")
        self.status.pack(anchor="w")

        buttons = tk.Frame(self, bg=BG, padx=22, pady=14)
        buttons.pack(fill="x", side="bottom")
        tk.Button(buttons, text="卸载", font=(UI, 11, "bold"), bg=WARN, fg="#ffffff",
                  activebackground="#ef6a6f", activeforeground="#ffffff", relief="flat", bd=0,
                  padx=26, pady=8, cursor="hand2", command=self._do_uninstall).pack(side="right")
        tk.Button(buttons, text="取消", font=(UI, 10), bg=BTN, fg=FG, activebackground=BTN_HI,
                  relief="flat", bd=0, padx=18, pady=8, cursor="hand2",
                  command=self.destroy).pack(side="right", padx=(0, 8))

    def _do_uninstall(self):
        lines = []
        uninstall(self.target, log=lines.append)
        self.status.configure(text="\n".join(lines[-3:]) or "已卸载", fg=OK)
        self.update_idletasks()
        messagebox.showinfo("卸载完成", f"{APP_NAME} 已卸载。", parent=self)
        self.destroy()

    # ------------------------------------------------------------ 界面动作
def main():
    parser = argparse.ArgumentParser(description="WinTimer 安装程序")
    parser.add_argument("--uninstall", action="store_true", help="进入卸载流程")
    parser.add_argument("--auto", action="store_true", help="静默执行（不显示界面）")
    parser.add_argument("--target", type=Path, default=None, help="安装目录")
    parser.add_argument("--payload", type=Path, default=None, help="要安装的 WinTimer.exe")
    parser.add_argument("--no-desktop", action="store_true")
    parser.add_argument("--no-menu", action="store_true")
    args = parser.parse_args()

    enable_dpi_awareness()
    payload = args.payload or payload_path()
    target = Path(args.target) if args.target else default_target()

    if args.auto:
        if args.uninstall:
            uninstall(target)
            print("uninstalled", target)
            return 0
        if payload is None:
            print("payload not found")
            return 2
        install(payload, target, desktop=not args.no_desktop, start_menu=not args.no_menu)
        print("installed to", target)
        return 0

    app = Setup(payload, args.uninstall, target_override=target,
                desktop=not args.no_desktop, start_menu=not args.no_menu)
    app.mainloop()
    return 0


if __name__ == "__main__":
    main()
