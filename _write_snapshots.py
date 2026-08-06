"""
只写入数据快照（视频记录已存在）
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "feishu-base-config.json"
VIDEOS_ROOT = ROOT / "downloads" / "videos"


def now_str():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def run_lark(config, base_args, *, timeout=60):
    args = ["lark-cli", "--profile", config["profile"], "base", *base_args, "--format", "json"]
    
    executable = shutil.which(args[0]) or args[0]
    suffix = Path(executable).suffix.lower()
    if suffix in {".cmd", ".bat"}:
        args = ["cmd", "/c", executable, *args[1:]]
    else:
        args = [executable, *args[1:]]
    
    env = os.environ.copy()
    env.pop("HERMES_HOME", None)
    env.pop("HERMES_GIT_BASH_PATH", None)
    env["LARK_CLI_NO_PROXY"] = "1"
    env["PYTHONUTF8"] = "1"
    
    result = subprocess.run(
        args, cwd=str(ROOT), env=env,
        text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
    )
    
    stdout = result.stdout
    start = stdout.find("{")
    if start < 0:
        raise RuntimeError(f"lark-cli no JSON: {stdout[:500]}\nstderr: {result.stderr[-500:]}")
    
    decoder = json.JSONDecoder()
    data, _ = decoder.raw_decode(stdout[start:])
    
    if result.returncode != 0 or not data.get("ok"):
        raise RuntimeError(f"lark-cli failed: {result.stderr[-1500:]}")
    
    return data


def get_record_id(data):
    d = data.get("data", {})
    if "record_id" in d:
        return d["record_id"]
    if "record" in d and isinstance(d["record"], dict):
        rids = d["record"].get("record_id_list", [])
        if rids:
            return rids[0]
    if "record_id_list" in d:
        rids = d["record_id_list"]
        if rids:
            return rids[0]
    return None


def list_video_records(config):
    """获取所有视频记录的 BVID -> record_id 映射"""
    table_id = config["tables"]["videos"]["table_id"]
    mapping = {}
    offset = 0
    
    while True:
        data = run_lark(config, [
            "+record-list", "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--limit", "200", "--offset", str(offset),
            "--field-id", "BVID",
        ])
        payload = data["data"]
        for record_id, values in zip(payload["record_id_list"], payload["data"]):
            bvid = str(values[0] or "").strip()
            if bvid:
                mapping[bvid] = record_id
        if not payload.get("has_more"):
            break
        offset += 200
    
    return mapping


def create_metric_snapshot(config, video_record_id, stat, bvid):
    table_id = config["tables"]["video_metric_snapshots"]["table_id"]
    tmp_dir = ROOT / ".tmp-lark"
    tmp_dir.mkdir(exist_ok=True)
    
    # 注意：快照表里没有 BVID 字段，只有关联视频
    fields = {
        "关联视频": [{"id": video_record_id}],
        "播放量": int(stat.get("view", 0)),
        "点赞量": int(stat.get("like", 0)),
        "投币数": int(stat.get("coin", 0)),
        "收藏数": int(stat.get("favorite", 0)),
        "分享数": int(stat.get("share", 0)),
        "评论数": int(stat.get("reply", 0)),
        "弹幕数": int(stat.get("danmaku", 0)),
        "快照时间": now_str(),
    }
    
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=tmp_dir, delete=False) as f:
        json.dump(fields, f, ensure_ascii=False)
        payload_path = Path(f.name)
    
    try:
        data = run_lark(config, [
            "+record-upsert", "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--json", f"@{payload_path.relative_to(ROOT)}",
        ], timeout=60)
        return get_record_id(data)
    finally:
        try:
            payload_path.unlink(missing_ok=True)
        except:
            pass


def main():
    config = load_config()
    
    # 获取视频记录映射
    video_map = list_video_records(config)
    print(f"飞书视频表: {len(video_map)} 条记录")
    for bvid, rid in list(video_map.items())[:10]:
        print(f"  {bvid} -> {rid}")
    
    # 从本地读取每个视频的 metrics-snapshot.json
    successes = []
    failures = []
    
    for mid_dir in VIDEOS_ROOT.iterdir():
        if not mid_dir.is_dir():
            continue
        for bv_dir in mid_dir.iterdir():
            if not bv_dir.is_dir():
                continue
            bvid = bv_dir.name
            metrics_file = bv_dir / "metrics-snapshot.json"
            
            if not metrics_file.exists():
                continue
            
            if bvid not in video_map:
                print(f"⚠️  {bvid} 在飞书视频表中找不到，跳过")
                continue
            
            try:
                with open(metrics_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                stat = data.get("metrics", data.get("raw_stat", {}))
                if not stat:
                    print(f"⚠️  {bvid} 没有统计数据，跳过")
                    continue
                
                print(f"写入快照: {bvid}...", end=" ")
                snapshot_id = create_metric_snapshot(config, video_map[bvid], stat, bvid)
                print(f"✅ {snapshot_id}")
                successes.append(bvid)
                
            except Exception as e:
                print(f"❌ {bvid}: {e}")
                failures.append({"bvid": bvid, "error": str(e)[:200]})
    
    print(f"\n完成! 成功: {len(successes)}, 失败: {len(failures)}")


if __name__ == "__main__":
    main()
