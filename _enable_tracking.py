import json, subprocess, os, tempfile, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = "ZCf1bxiooaqQHPsEKQAcIaARndf"
TABLE = "tblx1hxfoi1Y4lk0"

targets = ["36氪", "宋浩老师官方", "影视飓风", "极客湾Geekerwan",
           "歌白说Geslook", "赛雷三分钟", "epcdiy", "毕的二阶导"]


def lark_run(args, timeout=30):
    """调用 lark-cli 并返回 (stdout, stderr, returncode)"""
    env = os.environ.copy()
    env["LARK_CLI_NO_PROXY"] = "1"
    env.pop("HERMES_HOME", None)
    env.pop("HERMES_GIT_BASH_PATH", None)
    # 找到 lark-cli 的实际路径
    lark = shutil.which("lark-cli")
    if not lark:
        # 尝试在常见路径找
        for p in [Path(os.environ.get("APPDATA", "")) / "npm" / "lark-cli.cmd",
                  Path(os.environ.get("PROGRAMFILES", "")) / "nodejs" / "lark-cli.cmd"]:
            if p.exists():
                lark = str(p)
                break
    cmd = [lark or "lark-cli", "--profile", "default", "base", *args, "--format", "json"]
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env, timeout=timeout)
    return r.stdout, r.stderr, r.returncode


def parse_json(text):
    start = text.find("{")
    if start >= 0:
        return json.loads(text[start:])
    return None


# Step 1: 读取所有博主
print("Step 1: 读取博主表...")
stdout, stderr, rc = lark_run([
    "+record-list", "--as", "user",
    "--base-token", BASE, "--table-id", TABLE, "--limit", "200",
    "--field-id", "博主名称",
])
data = parse_json(stdout) or parse_json(stderr)
if not data or not data.get("ok"):
    print(f"  读取失败! rc={rc}")
    print(f"  stdout: {stdout[:300]}")
    print(f"  stderr: {stderr[:300]}")
    exit(1)

d = data["data"]
all_rids = d["record_id_list"]
all_names = [str(v[0] or "").strip() for v in d["data"]]
name_to_rid = dict(zip(all_names, all_rids))
print(f"  找到 {len(all_rids)} 个博主")

# Step 2: 批量关闭所有追踪
print("Step 2: 批量关闭所有追踪...")
tmp = ROOT / ".tmp-lark"
tmp.mkdir(exist_ok=True)
pf = tmp / "batch_close.json"
pf.write_text(json.dumps({"是否持续跟踪": False}, ensure_ascii=False), encoding="utf-8")

closed = 0
for i in range(0, len(all_rids), 100):
    batch = all_rids[i:i+100]
    args = ["+record-batch-update", "--as", "user",
            "--base-token", BASE, "--table-id", TABLE,
            "--json", f"@{pf.relative_to(ROOT)}", "--format", "json"]
    for rid in batch:
        args.extend(["--record-id", rid])
    stdout, stderr, rc = lark_run(args, timeout=60)
    result = parse_json(stdout) or parse_json(stderr)
    if result and result.get("ok"):
        closed += len(batch)
        print(f"  批次{i//100+1}: OK ({len(batch)}条)")
    else:
        print(f"  批次{i//100+1}: FAIL rc={rc}")
        if stderr:
            print(f"    {stderr[:200]}")
pf.unlink(missing_ok=True)
print(f"  已关闭: {closed}/{len(all_rids)}")

# Step 3: 开启目标博主
print("\nStep 3: 开启目标博主追踪...")
enabled = 0
for t in targets:
    if t not in name_to_rid:
        print(f"  {t}: 未找到")
        continue
    rid = name_to_rid[t]
    fields = json.dumps({"是否持续跟踪": True}, ensure_ascii=False)
    pf2 = tmp / "enable.json"
    pf2.write_text(fields, encoding="utf-8")
    stdout, stderr, rc = lark_run([
        "+record-upsert", "--as", "user",
        "--base-token", BASE, "--table-id", TABLE, "--record-id", rid,
        "--json", f"@{pf2.relative_to(ROOT)}", "--format", "json",
    ])
    result = parse_json(stdout) or parse_json(stderr)
    pf2.unlink(missing_ok=True)
    ok = result and result.get("ok")
    print(f"  {t}: {'OK' if ok else 'FAIL'}")
    if ok:
        enabled += 1

print(f"\n完成! 开启追踪: {enabled}/{len(targets)}")
