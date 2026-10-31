# -*- coding: utf-8 -*-
"""对比切换前后页面渲染出的文本内容。"""
import hashlib
import os
import re
import sys
import difflib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

def load(name):
    path = os.path.join(ROOT, "output/playwright", name)
    raw = open(path, "rb").read()
    # playwright-cli 输出可能带装饰行，剥离最后一个 JS 代码块之后的内容
    text = raw.decode("utf-8", errors="replace")
    # 去掉 CLI 的包裹标记
    for marker in ("### Ran Playwright code", "```js", "```"):
        text = text.replace(marker, "")
    return text

before = load("t_before.txt")
after = load("t_after.txt")

print(f"原版字节 {len(before.encode()):,}  新版字节 {len(after.encode()):,}")
hb = hashlib.sha256(before.encode()).hexdigest()[:16]
ha = hashlib.sha256(after.encode()).hexdigest()[:16]
print(f"原版 sha256 {hb}")
print(f"新版 sha256 {ha}")
print()

if before == after:
    print("*** 页面文本完全相同 ***")
else:
    bl, al = before.split("\n"), after.split("\n")
    print(f"行数 {len(bl)} vs {len(al)}")
    d = list(difflib.unified_diff(bl, al, "before", "after", lineterm="", n=0))
    print(f"差异行数: {sum(1 for x in d if x.startswith(('+', '-')) and not x.startswith(('+++', '---')))}")
    for line in d[:40]:
        print("  " + line[:200])

# 抽取关键数字做独立核对
def grab(label, text):
    m = re.search(re.escape(label) + r"[^\d]{0,12}([\d,]+)", text)
    return m.group(1) if m else None

print("\n关键数字对照：")
for label in ["岗位共", "样本 ", "P25", "P75", "洪山区", "江夏区",
              "本科", "硕士", "Java（", "Python（", "MySQL（"]:
    print(f"  {label:10s} before={grab(label, before)!s:>10s}  after={grab(label, after)!s:>10s}")
