# -*- coding: utf-8 -*-
"""发布前脱敏：把原始快照里夹带的 1 个手机号替换掉。

只处理 data/ 下的文件；就地替换并统计。
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHONE = re.compile(r"1[3-9]\d{9}")
MASK = "[REDACTED_PHONE]"

# 18/19 个匹配是 job_id / url 里的数字串，不能碰 —— 只处理 tags 里那一个。
targets = [
    os.path.join(ROOT, "data", "raw", "jobs_master.json"),
    os.path.join(ROOT, "data", "raw", "zhilian_jd.json"),
    os.path.join(ROOT, "data", "raw", "zhilian_positions.jsonl"),
]

changed = 0
for path in targets:
    if not os.path.exists(path):
        continue
    text = open(path, encoding="utf-8").read()
    if not PHONE.search(text):
        print(f"{os.path.basename(path)}: 无匹配")
        continue

    # 只在 JSON 字符串值的位置替换；用解析再序列化会改动格式，
    # 所以按「只替换出现在 tags 数组里的纯数字字符串」来定位。
    def fix_tags(match):
        global changed
        changed += 1
        return '"' + MASK + '"'

    # tags 里的号码形如  "15387120086"  —— 前后都是引号或逗号
    new = re.sub(r'"1[3-9]\d{9}"', fix_tags, text)
    if new != text:
        open(path, "w", encoding="utf-8", newline="\n").write(new)
        print(f"{os.path.basename(path)}: 替换 {changed} 处")
    else:
        print(f"{os.path.basename(path)}: 匹配但未替换（可能是 job_id 片段）")

print(f"\n合计替换 {changed} 处")
