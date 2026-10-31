# -*- coding: utf-8 -*-
"""线性扫描定位两版页面文本的差异（144KB 上用 SequenceMatcher 会卡死）。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")


def load(name):
    text = open(os.path.join(ROOT, "output/playwright", name), encoding="utf-8",
                errors="replace").read()
    for marker in ("### Ran Playwright code", "```js", "```"):
        text = text.replace(marker, "")
    return text


a, b = load("t_before.txt"), load("t_after.txt")
print(f"长度: {len(a)} vs {len(b)}")

if a == b:
    print("*** 完全相同 ***")
    sys.exit(0)

n = min(len(a), len(b))
diffs = [i for i in range(n) if a[i] != b[i]]
print(f"不同字符位置数: {len(diffs)}   （若为 0 则只是尾部长度差）")

if diffs:
    # 把相邻位置合并成区间
    groups, cur = [], [diffs[0]]
    for i in diffs[1:]:
        if i - cur[-1] <= 30:
            cur.append(i)
        else:
            groups.append(cur)
            cur = [i]
    groups.append(cur)
    print(f"差异区间数: {len(groups)}\n")
    for g in groups[:12]:
        s, e = g[0], g[-1]
        print(f"位置 {s}..{e}")
        print(f"  上文 …{a[max(0,s-60):s]!r}")
        print(f"  原版 {a[s:e+1]!r}")
        print(f"  新版 {b[s:e+1]!r}")
        print(f"  下文 {a[e+1:e+61]!r}…")
        print()
