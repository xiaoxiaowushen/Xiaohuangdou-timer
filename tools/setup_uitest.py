"""驱动安装向导的界面代码路径（安装 / 卸载按钮），验证真实交互流程。

弹窗被打桩，不弹真实对话框；快捷方式和注册表在沙箱里写不进去，只要求不崩。

用法： python tools/setup_uitest.py
"""

import shutil
import sys
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(ROOT / "installer"))
import setup_app as S  # noqa: E402

TARGET = ROOT / ".tmp" / "setup_ui_test"
PAYLOAD = ROOT / "dist" / "计时器.exe"
if not PAYLOAD.exists():
    PAYLOAD = ROOT / ".tmp" / "smoke" / "dist" / "WinTimer.exe"

messages = []
S.messagebox.showinfo = lambda title, msg, **kw: messages.append(("info", title, msg))
S.messagebox.showerror = lambda title, msg, **kw: messages.append(("error", title, msg))

FAILED = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name} {detail}")
    if not cond:
        FAILED.append(name)


def alive(window) -> bool:
    try:
        return bool(window.winfo_exists())
    except tk.TclError:
        return False


def main():
    if TARGET.exists():
        shutil.rmtree(TARGET, ignore_errors=True)

    print("载荷:", PAYLOAD, PAYLOAD.exists())
    app = S.Setup(PAYLOAD, False, target_override=TARGET, desktop=False, start_menu=False)
    app.withdraw()
    app.update_idletasks()
    app.path_var.set(str(TARGET))
    app.run_var.set(False)          # 别真启动程序
    check("安装界面建好了", alive(app))
    check("默认勾选了开始菜单快捷方式", app.menu_var.get() is True)

    app._do_install()               # ← 等价于用户点「安装」
    check("主程序已复制", (TARGET / S.EXE_NAME).exists(),
          f"{(TARGET / S.EXE_NAME).stat().st_size if (TARGET / S.EXE_NAME).exists() else '-'} 字节")
    check("弹了安装完成提示", any(m[0] == "info" and "安装完成" in m[1] for m in messages),
          str(messages[-1:]))
    check("没有报错弹窗", not any(m[0] == "error" for m in messages))
    check("窗口已关闭", not alive(app))

    # 卸载界面
    messages.clear()
    app2 = S.Setup(None, True, target_override=TARGET)
    app2.withdraw()
    app2.update_idletasks()
    check("卸载界面建好了", alive(app2))
    app2._do_uninstall()            # ← 等价于用户点「卸载」
    check("安装目录已清理", not TARGET.exists(), str(list(TARGET.glob('*')) if TARGET.exists() else []))
    check("弹了卸载完成提示", any(m[0] == "info" and "卸载完成" in m[1] for m in messages))
    check("卸载没有报错弹窗", not any(m[0] == "error" for m in messages))

    print()
    if FAILED:
        print(f"{len(FAILED)} 项失败: {FAILED}")
        raise SystemExit(1)
    print("界面流程全部通过 ✅")


if __name__ == "__main__":
    main()
