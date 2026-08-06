import json, subprocess, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = "ZCf1bxiooaqQHPsEKQAcIaARndf"

env = os.environ.copy()
env["LARK_CLI_NO_PROXY"] = "1"
env.pop("HERMES_HOME", None)
env.pop("HERMES_GIT_BASH_PATH", None)

tmp = ROOT / ".tmp-lark"
tmp.mkdir(exist_ok=True)

# 测试1: 用已知有效的 record_id 写入快照表
print("测试1: 写入快照表（带关联视频）...")
payload = {
    "关联视频": [{"id": "recvrjllWuZ6CN"}],
    "播放量": 1000,
    "点赞量": 100,
    "快照时间": "2026-08-04 17:00:00"
}
pf = tmp / "test_snap.json"
pf.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

r = subprocess.run(
    ["lark-cli", "--profile", "default", "base", "+record-upsert",
     "--as", "user", "--base-token", BASE,
     "--table-id", "tblMVVv7wijHCULu",
     "--json", f"@{pf.relative_to(ROOT)}", "--format", "json"],
    cwd=str(ROOT), capture_output=True, text=True,
    encoding="utf-8", errors="replace", env=env, timeout=30,
)
print(f"  stdout: {r.stdout[:300]}")
print(f"  stderr: {r.stderr[:300]}")

# 测试2: 不带关联视频
print("\n测试2: 写入快照表（不带关联视频）...")
payload2 = {
    "播放量": 2000,
    "点赞量": 200,
    "快照时间": "2026-08-04 17:00:00"
}
pf2 = tmp / "test_snap2.json"
pf2.write_text(json.dumps(payload2, ensure_ascii=False), encoding="utf-8")

r2 = subprocess.run(
    ["lark-cli", "--profile", "default", "base", "+record-upsert",
     "--as", "user", "--base-token", BASE,
     "--table-id", "tblMVVv7wijHCULu",
     "--json", f"@{pf2.relative_to(ROOT)}", "--format", "json"],
    cwd=str(ROOT), capture_output=True, text=True,
    encoding="utf-8", errors="replace", env=env, timeout=30,
)
print(f"  stdout: {r2.stdout[:300]}")
print(f"  stderr: {r2.stderr[:300]}")

pf.unlink(missing_ok=True)
pf2.unlink(missing_ok=True)
