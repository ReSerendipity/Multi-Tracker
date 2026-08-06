"""
更新飞书博主表：全部关闭持续跟踪，只保留指定的几个
"""
import json
import subprocess
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "feishu-base-config.json"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def run_lark(config, base_args, *, timeout=60):
    env = os.environ.copy()
    env.pop("HERMES_HOME", None)
    env.pop("HERMES_GIT_BASH_PATH", None)
    env["LARK_CLI_NO_PROXY"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    
    args = ["lark-cli", "--profile", config["profile"], "base", *base_args, "--format", "json"]
    
    import shutil
    executable = shutil.which(args[0]) or args[0]
    suffix = Path(executable).suffix.lower()
    if suffix in {".cmd", ".bat"}:
        args = ["cmd", "/c", executable, *args[1:]]
    else:
        args = [executable, *args[1:]]
    
    result = subprocess.run(
        args,
        cwd=str(ROOT),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    
    stdout = result.stdout
    start = stdout.find("{")
    if start < 0:
        raise RuntimeError(f"command did not return JSON: {stdout[:500]}\nstderr: {result.stderr[-500:]}")
    
    decoder = json.JSONDecoder()
    data, _ = decoder.raw_decode(stdout[start:])
    
    if result.returncode != 0 or not data.get("ok"):
        raise RuntimeError(
            f"lark-cli failed\nargs: {args}\n"
            f"stdout: {stdout[-2000:]}\nstderr: {result.stderr[-2000:]}"
        )
    
    return data


def list_all_creators(config):
    """获取所有博主的 record_id 和 MID"""
    table_id = config["tables"]["creators"]["table_id"]
    rows = []
    offset = 0
    
    while True:
        args = [
            "+record-list",
            "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--limit", "200",
            "--offset", str(offset),
            "--field-id", "fldvXdhHGY",  # B站MID
        ]
        data = run_lark(config, args)
        payload = data["data"]
        
        for record_id, values in zip(payload["record_id_list"], payload["data"]):
            mid = str(values[0] or "").strip()
            if mid:
                rows.append({"mid": mid, "record_id": record_id})
        
        if not payload.get("has_more"):
            break
        offset += 200
    
    return rows


def batch_update_tracking(config, creators_to_enable):
    """更新持续跟踪状态：全部关闭，指定的开启"""
    table_id = config["tables"]["creators"]["table_id"]
    all_creators = list_all_creators(config)
    
    print(f"飞书表中共有 {len(all_creators)} 个博主")
    
    enable_mids = set(creators_to_enable)
    print(f"需要开启持续跟踪: {len(enable_mids)} 个")
    for mid in enable_mids:
        matched = [c for c in all_creators if c["mid"] == mid]
        if matched:
            print(f"  ✓ MID {mid} 已找到")
        else:
            print(f"  ✗ MID {mid} 未找到！")
    
    # 逐条更新（简单可靠）
    tmp_dir = ROOT / ".tmp-lark"
    tmp_dir.mkdir(exist_ok=True)
    
    updated = 0
    for i, c in enumerate(all_creators, 1):
        tracking = c["mid"] in enable_mids
        payload = {"是否持续跟踪": tracking}
        
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=tmp_dir, delete=False) as f:
            json.dump(payload, f, ensure_ascii=False)
            payload_path = Path(f.name)
        
        args = [
            "+record-upsert",
            "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--record-id", c["record_id"],
            "--json", f"@{payload_path.relative_to(ROOT)}",
        ]
        
        try:
            run_lark(config, args, timeout=30)
            updated += 1
            if i % 50 == 0 or i == len(all_creators):
                print(f"  已更新 {i}/{len(all_creators)}...")
        except Exception as e:
            print(f"  更新 MID {c['mid']} 失败: {e}")
        finally:
            try:
                payload_path.unlink(missing_ok=True)
            except:
                pass
    
    return updated


def main():
    config = load_config()
    
    # 要开启持续跟踪的 MID 列表（5个不同领域）
    enable_mids = [
        "25876945",    # 极客湾Geekerwan - 科技数码
        "254463269",   # 毕导 - 知识科普
        "66607740",    # 宋浩老师官方 - 教育学习
        "90183256",    # 36氪 - 商业财经
        "946974",      # 影视飓风 - 影视创作
    ]
    
    print("=" * 50)
    print("更新飞书博主表 - 持续跟踪状态")
    print("=" * 50)
    
    updated = batch_update_tracking(config, enable_mids)
    
    print(f"\n✅ 完成！共更新 {updated} 条记录")
    print(f"   其中 {len(enable_mids)} 个开启持续跟踪，其余关闭")


if __name__ == "__main__":
    main()
