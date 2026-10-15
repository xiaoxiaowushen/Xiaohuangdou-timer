"""生成应用图标 assets/icon.ico。

优先用 assets/icon_source.jpg（用户提供的图）：抠掉白底 → 裁边 → 输出多尺寸 ico。
源图不在时退回程序绘制的钟表图标。

用法： python tools/make_icon.py
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SOURCE = ASSETS / "icon_source.jpg"
OUT_ICO = ASSETS / "icon.ico"
OUT_PNG = ASSETS / "icon.png"

SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
SENTINEL = (255, 0, 255)
BG_TOLERANCE = 42          # 容忍 JPEG 噪点
PADDING_RATIO = 0.03       # 四周留一点边


def _background_color(img: Image.Image):
    """取四角中位数当背景色。"""
    w, h = img.size
    picks = [img.getpixel(p) for p in ((2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3))]
    return tuple(sorted(c[i] for c in picks)[len(picks) // 2] for i in range(3))


def _components(mask: Image.Image, min_area: int = 1):
    """返回 [(像素列表, (x0,y0,x1,y1)), ...]，四连通。"""
    from collections import deque

    w, h = mask.size
    src = mask.load()
    seen = bytearray(w * h)
    result = []
    for y0 in range(h):
        for x0 in range(w):
            idx = y0 * w + x0
            if seen[idx] or not src[x0, y0]:
                continue
            queue = deque([(x0, y0)])
            seen[idx] = 1
            pixels = []
            while queue:
                x, y = queue.popleft()
                pixels.append((x, y))
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h:
                        nidx = ny * w + nx
                        if not seen[nidx] and src[nx, ny]:
                            seen[nidx] = 1
                            queue.append((nx, ny))
            if len(pixels) >= min_area:
                xs = [p[0] for p in pixels]
                ys = [p[1] for p in pixels]
                result.append((pixels, (min(xs), min(ys), max(xs), max(ys))))
    return result


def _keep_big_components(mask: Image.Image, min_ratio: float = 0.004) -> Image.Image:
    """只保留足够大的连通块，去掉 JPEG 噪点。"""
    w, h = mask.size
    out = Image.new("L", (w, h), 0)
    dst = out.load()
    for pixels, _bbox in _components(mask, int(w * h * min_ratio)):
        for x, y in pixels:
            dst[x, y] = 255
    return out


def _find_pupils(work: Image.Image):
    """找出两只眼睛的黑色瞳孔：返回 [(中心x, 中心y, 半径), ...]。"""
    w, h = work.size
    gray = work.convert("L")
    dark = gray.point(lambda v: 255 if v < 90 else 0)
    candidates = []
    for pixels, (x0, y0, x1, y1) in _components(dark, int(w * h * 0.0008)):
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        area = len(pixels)
        fill_ratio = area / (bw * bh)
        if not (0.55 <= fill_ratio <= 1.0):
            continue
        if not (0.6 <= bw / bh <= 1.7):
            continue
        if y1 > h * 0.6:                      # 瞳孔在上半部分
            continue
        cx = sum(p[0] for p in pixels) / area
        cy = sum(p[1] for p in pixels) / area
        candidates.append((area, cx, cy))
    candidates.sort(reverse=True)
    pupils = []
    for area, cx, cy in candidates[:2]:
        pupils.append((cx, cy, max(3.0, (area / 3.14159) ** 0.5)))
    return pupils


def _eye_mask(work: Image.Image, pupils, grow: float = 1.02) -> Image.Image:
    """按瞳孔位置向外量到眼白边缘，生成眼球保护区域。

    8 个方向量距离取中位数：个别方向从轮廓缺口漏出去也不会把保护圈撑大。
    """
    w, h = work.size
    gray = work.convert("L")
    gp = gray.load()
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    directions = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
    measured = []
    for cx, cy, pr in pupils:
        cx, cy = int(cx), int(cy)
        limit = max(6, int(pr * 3.5))
        distances = []
        for dx, dy in directions:
            steps = 0
            x, y = cx, cy
            while steps < limit and 0 <= x < w and 0 <= y < h:
                if steps > pr and gp[x, y] < 120:      # 碰到眼白外圈的黑线
                    break
                x += dx
                y += dy
                steps += 1
            distances.append(min(steps, limit))
        distances.sort()
        median = distances[len(distances) // 2]
        measured.append((cx, cy, pr, median, distances))

    # 两只眼睛一样大：取最小的「眼白/瞳孔」比例，避免某只眼漏到背景把保护圈撑大
    ratio = min((m / pr for _cx, _cy, pr, m, _d in measured if pr > 0), default=2.0)
    ratio = max(1.3, min(2.6, ratio))
    for cx, cy, pr, median, distances in measured:
        radius = max(4.0, pr * ratio * grow)
        print(f"  瞳孔 r={pr:.1f} 方向距离={distances} 比例={ratio:.2f} → 保护圈 r={radius:.1f}")
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=255)
    return mask


def cut_background(img: Image.Image, work_size: int = 640) -> Image.Image:
    """抠掉白底：按颜色分出前景，闭运算封缺口，保护眼球，再从四角泛洪定背景。

    这张图里眼球和背景都是白色，直接泛洪会顺着轮廓缺口钻进眼里，所以要先保护眼球。
    """
    from PIL import ImageChops, ImageFilter

    # 图标最大 256px，处理时降到 640px 足够，而且快很多
    scale = min(1.0, work_size / max(img.size))
    work = img.convert("RGB")
    if scale < 1.0:
        work = work.resize((max(1, int(work.width * scale)), max(1, int(work.height * scale))),
                           Image.LANCZOS)
    width, height = work.size
    bg = _background_color(work)

    # 前景 = 与背景色差异明显的像素
    diff = ImageChops.difference(work, Image.new("RGB", work.size, bg)).convert("L")
    foreground = diff.point(lambda v: 255 if v > 38 else 0)
    foreground = _keep_big_components(foreground)

    # 闭运算：填掉轮廓上的细小缺口
    sealed = foreground.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(7))

    barrier = work.copy()
    barrier.paste((0, 0, 0), (0, 0), sealed)

    # 眼球保护：挡住之后泛洪就进不去，眼里那片白也就不会变透明
    pupils = _find_pupils(work)
    if pupils:
        eyes = _eye_mask(work, pupils)
        barrier.paste((0, 0, 0), (0, 0), eyes)
        print(f"  保护了 {len(pupils)} 只眼睛")
    else:
        print("  未识别到瞳孔，跳过眼球保护")

    sentinel = (255, 0, 255)
    for seed in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        try:
            ImageDraw.floodfill(barrier, seed, sentinel, thresh=34)
        except Exception:
            pass

    # 背景 → 透明；其余保留原色
    alpha = Image.new("L", (width, height), 255)
    ap = alpha.load()
    bp = barrier.load()
    for y in range(height):
        for x in range(width):
            if bp[x, y] == sentinel:
                ap[x, y] = 0

    # 收一点边、轻微羽化，避免白色描边残留
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.6))

    rgba = work.convert("RGBA")
    rgba.putalpha(alpha)
    if scale < 1.0:
        rgba = rgba.resize(img.size, Image.LANCZOS)
    return rgba


def trim(img: Image.Image) -> Image.Image:
    bbox = img.getbbox()
    if not bbox:
        return img
    return img.crop(bbox)


def square_with_padding(img: Image.Image) -> Image.Image:
    side = max(img.size)
    pad = int(side * PADDING_RATIO)
    canvas = Image.new("RGBA", (side + pad * 2, side + pad * 2), (0, 0, 0, 0))
    canvas.paste(img, ((canvas.width - img.width) // 2, (canvas.height - img.height) // 2), img)
    return canvas


def build_from_source() -> None:
    src = Image.open(SOURCE)
    print("源图:", src.size, src.mode)
    cut = cut_background(src)
    cut = trim(cut)
    print("裁边后:", cut.size)
    art = square_with_padding(cut)

    base = art.resize((256, 256), Image.LANCZOS)
    base.save(OUT_ICO, format="ICO", sizes=SIZES)
    base.save(OUT_PNG)
    print("written", OUT_ICO, "and", OUT_PNG)


# ---------------------------------------------------------- 备用：手绘钟表图标

def build_fallback() -> None:
    scale, size = 4, 256
    big = size * scale
    top, bottom = (44, 58, 86), (18, 20, 26)

    grad = Image.new("RGB", (1, big), top)
    for y in range(big):
        t = y / max(1, big - 1)
        grad.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    plate = grad.resize((big, big)).convert("RGBA")

    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=int(big * 0.22), fill=255)

    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    canvas.paste(plate, (0, 0), mask)

    draw = ImageDraw.Draw(canvas)
    center = big / 2
    ring = big * 0.31
    width = int(big * 0.062)
    draw.arc((center - ring, center - ring, center + ring, center + ring), start=-70, end=290,
             fill=(76, 194, 255), width=width)
    knob_w, knob_h = big * 0.11, big * 0.075
    draw.rounded_rectangle((center - knob_w / 2, center - ring - knob_h * 0.78,
                            center + knob_w / 2, center - ring + knob_h * 0.32),
                           radius=knob_h * 0.34, fill=(76, 194, 255))
    hand_w = int(big * 0.035)
    draw.line((center, center, center, center - ring * 0.60), fill=(233, 236, 243), width=hand_w)
    draw.line((center, center, center + ring * 0.46, center + ring * 0.16), fill=(233, 236, 243), width=hand_w)
    dot = big * 0.03
    draw.ellipse((center - dot, center - dot, center + dot, center + dot), fill=(255, 122, 89))

    canvas = Image.alpha_composite(canvas.filter(ImageFilter.GaussianBlur(big * 0.012)), canvas)
    icon = canvas.resize((size, size), Image.LANCZOS)
    icon.save(OUT_ICO, format="ICO", sizes=SIZES)
    icon.save(OUT_PNG)
    print("written", OUT_ICO, "and", OUT_PNG, "(fallback)")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if SOURCE.exists():
        build_from_source()
    else:
        print("未找到", SOURCE, "→ 使用内置图标")
        build_fallback()
