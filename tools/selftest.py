"""计时逻辑自检（不依赖界面）。

用法： python tools/selftest.py
"""

import sys
import time
from pathlib import Path

try:  # 控制台可能是 GBK，避免打印中文/符号时崩
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wintimer.app import Countdown, Stopwatch, duration_label, fmt_clock  # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got={got!r} want={want!r}")
    if not ok:
        FAILED.append(name)


def check_true(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name} {detail}")
    if not cond:
        FAILED.append(name)


def test_format():
    check("fmt 0 秒", fmt_clock(0), "00:00")
    check("fmt 65 秒", fmt_clock(65), "01:05")
    check("fmt 3605 秒", fmt_clock(3605), "1:00:05")
    check("fmt 秒表 1.47", fmt_clock(1.47, centis=True), "00:01.47")
    check("fmt 秒表 3725 秒", fmt_clock(3725, centis=True), "1:02:05")
    check("时长文案 5", duration_label(5), "5 秒")
    check("时长文案 90", duration_label(90), "1 分 30 秒")
    check("时长文案 1500", duration_label(1500), "25 分")
    check("时长文案 3600", duration_label(3600), "1 小时")
    check("时长文案 3665", duration_label(3665), "1 小时 1 分 5 秒")


def test_stopwatch():
    sw = Stopwatch()
    check("秒表初始", sw.value(), 0.0)
    check_true("秒表初始未运行", not sw.running)

    sw.start()
    time.sleep(0.25)
    running_value = sw.value()
    check_true("秒表运行 0.25s 后约 0.25", 0.2 < running_value < 0.45, f"value={running_value:.3f}")

    sw.pause()
    paused = sw.value()
    time.sleep(0.2)
    check("暂停后数值冻结", sw.value(), paused)
    check_true("暂停后未运行", not sw.running)

    sw.start()   # 继续
    time.sleep(0.15)
    check_true("继续后累加", sw.value() > paused + 0.1, f"value={sw.value():.3f}")
    sw.pause()

    sw.reset()
    check("重置归零", sw.value(), 0.0)
    check_true("重置后未运行", not sw.running)

    # 重复 start 不应重置计时
    sw.start()
    time.sleep(0.1)
    once = sw.value()
    sw.start()
    time.sleep(0.1)
    check_true("重复 start 不重置", sw.value() > once, f"{once:.3f} -> {sw.value():.3f}")
    sw.pause()


def test_countdown():
    cd = Countdown(0)
    check_true("倒计时 0 时长无法启动", not cd.start())

    cd.set_total(2)
    check("设定后显示 2", cd.value(), 2.0)
    check_true("可以启动", cd.start())
    time.sleep(0.3)
    check_true("运行中数值下降", 1.5 < cd.value() < 1.9, f"value={cd.value():.3f}")
    check_true("未到点不触发", not cd.check_finished())

    cd.pause()
    held = cd.value()
    time.sleep(0.2)
    check_true("暂停后不再下降", abs(cd.value() - held) < 0.05, f"{held:.3f} -> {cd.value():.3f}")
    check_true("可以继续", cd.start())

    # 直接把剩余时间压到很小，验证到点只触发一次
    cd._deadline = time.time() + 0.15
    time.sleep(0.3)
    check_true("到点触发一次", cd.check_finished())
    check_true("到点不再重复触发", not cd.check_finished())
    check("到点后为 0", cd.value(), 0.0)
    check_true("到点后未运行", not cd.running)

    # 到点后再按开始，应从设定时长重新开始
    check_true("到点后可重启", cd.start())
    check_true("重启后回到设定时长附近", cd.value() > 1.5, f"value={cd.value():.3f}")

    cd.reset()
    check("重置回设定时长", cd.value(), 2.0)
    check_true("重置后未运行", not cd.running)
    check_true("重置后未标记结束", not cd.finished)

    # 墙钟时间：停机/休眠后依然准确
    cd.set_total(60)
    cd.start()
    cd._deadline = time.time() + 30   # 模拟时间流逝
    check_true("墙钟口径有效", 29 < cd.value() <= 30, f"value={cd.value():.3f}")


def main():
    test_format()
    test_stopwatch()
    test_countdown()
    print()
    if FAILED:
        print(f"{len(FAILED)} 项失败: {FAILED}")
        raise SystemExit(1)
    print("全部通过 ✅")


if __name__ == "__main__":
    main()
