import json, subprocess, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = "ZCf1bxiooaqQHPsEKQAcIaARndf"
TABLE = "tblx1hxfoi1Y4lk0"

env = {**os.environ, "LARK_CLI_NO_PROXY": "1"}
env.pop("HERMES_HOME", None)
env.pop("HERMES_GIT_BASH_PATH", None)

# 先拿到一个博主的 record_id
r = subprocess.run(
    ["lark-cli", "--profile", "default", "base", "+record-list", "--as", "user",
     "--base-token", BASE, "--table-id", TABLE, "--limit", "3",
     "--field-id", "博主名称", "--field-id", "是否持续跟踪", "--format", "json"],
    cwd=str(ROOT), capture_output=True, text=True,
    encoding="utf-8", errors="replace", env=env,
)

data = json.loads(r.stdout[r.stdout.find("{"):])
d = data["data"]
for rec_id, vals in zip(d["record_id_list"], d["data"][:3]):
    print(f"record_id: {rec_id}")
    print(f"  vals: {vals}")
    print(f"  name: {vals[0]}, tracking: {vals[1] if len(vals)>1 else '?'}")
    print()

# 尝试开启第一个博主的追踪
first_rec = d["record_id_list"][0]
first_name = d["data"][0][0]
print(f"尝试开启 {first_name} (record_id={first_rec})...")

import tempfile
fields = json.dumps({"是否持续跟踪": True}, ensure_ascii=False)
tmp = ROOT / ".tmp-lark"
tmp.mkdir(exist_ok=True)
pf = tmp / "track.json"
pf.write_text(fields, encoding="utf-8")

r2 = subprocess.run(
    ["lark-cli", "--profile", "default", "base", "+record-upsert", "--as", "user",
     "--base-token", BASE, "--table-id", TABLE, "--record-id", first_rec,
     "--json", f"@{pf.relative_to(ROOT)}", "--format", "json"],
    cwd=str(ROOT), capture_output=True, text=True,
    encoding="utf-8", errors="replace", env=env,
)

print(f"stdout: {r2.stdout[:500]}")
print(f"stderr: {r2.stderr[:500]}")
pf.unlink(missing_ok=True)
