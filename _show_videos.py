import json, sys
text = sys.stdin.read()
data = json.loads(text[text.find("{"):])
d = data["data"]
print(f"共 {len(d['data'])} 条记录")
print()
for vals in d["data"]:
    bvid = vals[0] if vals[0] else "?"
    title = vals[1][:30] if len(vals) > 1 and vals[1] else "?"
    dl_status = vals[2] if len(vals) > 2 and vals[2] else "?"
    cmt_status = vals[3] if len(vals) > 3 and vals[3] else "?"
    print(f"  {bvid} | {dl_status:6s} | {cmt_status:6s} | {title}")
