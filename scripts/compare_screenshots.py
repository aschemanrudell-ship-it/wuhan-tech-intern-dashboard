# -*- coding: utf-8 -*-
"""对比切换前后两张截图的像素差异，定位变化区域。"""
import os
import sys

from PIL import Image, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

before = Image.open(os.path.join(ROOT, "output/playwright/before.png")).convert("RGB")
after = Image.open(os.path.join(ROOT, "output/playwright/after2.png")).convert("RGB")

print(f"原版尺寸: {before.size}")
print(f"新版尺寸: {after.size}")
if before.size != after.size:
    print("!! 尺寸不同，无法逐像素比较")
    sys.exit(1)

diff = ImageChops.difference(before, after)
bbox = diff.getbbox()
print(f"差异包围盒: {bbox}")

if bbox is None:
    print("\n*** 逐像素完全相同 ***")
    sys.exit(0)

# 统计差异强度
pix = diff.load()
w, h = before.size
changed = 0
strong = 0
rows = {}
x0, y0, x1, y1 = bbox
for y in range(y0, y1):
    for x in range(x0, x1):
        r, g, b = pix[x, y]
        if r + g + b > 0:
            changed += 1
            rows[y] = rows.get(y, 0) + 1
            if r + g + b > 60:
                strong += 1

total = w * h
print(f"画布像素: {total:,}")
print(f"有差异像素: {changed:,} ({changed/total*100:.3f}%)")
print(f"显著差异像素(单通道>20): {strong:,} ({strong/total*100:.3f}%)")

# 找出差异集中的横向条带
print("\n差异集中的区域（按 y 分组成连续区间）：")
hot = sorted(y for y, c in rows.items() if c > 3)
if hot:
    groups, cur = [], [hot[0]]
    for y in hot[1:]:
        if y - cur[-1] <= 8:
            cur.append(y)
        else:
            groups.append(cur)
            cur = [y]
    groups.append(cur)
    for g in groups:
        y_a, y_b = g[0], g[-1]
        if y_b - y_a < 2:
            continue
        crop = diff.crop((0, y_a, w, y_b + 1))
        cb = crop.getbbox()
        print(f"  y={y_a:5d}..{y_b:5d}  高度 {y_b-y_a+1:4d}px  横向 x={cb[0]}..{cb[2]}  "
              f"差异像素 {sum(rows.get(y,0) for y in g):,}")
        crop.save(os.path.join(ROOT, f"output/playwright/diff_{y_a}_{y_b}.png"))
else:
    print("  （无显著集中区域）")

# 生成可视化差异图（差异处标红）
mask = diff.convert("L").point(lambda v: 255 if v > 24 else 0)
red = Image.new("RGB", before.size, (255, 0, 0))
vis = Image.composite(red, before, mask)
out = os.path.join(ROOT, "output/playwright/diff_highlight.png")
vis.save(out)
print(f"\n差异高亮图: {out}")
