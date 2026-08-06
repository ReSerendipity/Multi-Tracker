"""
重新写入已下载的视频到飞书（修复版）
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "feishu-base-config.json"
VIDEOS_ROOT = ROOT / "downloads" / "videos"
CDP_ENDPOINT_URL = "http://127.0.0.1:9222/json/version"
COMMENTS_SCRIPT = ROOT / ".agents" / "skills" / "bilibili-comments" / "scripts" / "fetch_comments.mjs"


def now_str():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_cdp_endpoint():
    import urllib.request
    resp = urllib.request.urlopen(CDP_ENDPOINT_URL)
    info = json.loads(resp.read())
    return info["webSocketDebuggerUrl"]


def run_command(args, *, timeout=None, check=True, cwd=None):
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    venv_scripts = str(ROOT / ".venv" / "Scripts")
    env["PATH"] = venv_scripts + os.pathsep + env.get("PATH", "")
    
    result = subprocess.run(
        args,
        cwd=str(cwd or ROOT),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"command failed: {result.stderr[-1000:]}")
    return result


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
        raise RuntimeError(f"lark-cli no JSON: {stdout[:500]}\nstderr: {result.stderr[-500:]}")
    
    decoder = json.JSONDecoder()
    data, _ = decoder.raw_decode(stdout[start:])
    
    if result.returncode != 0 or not data.get("ok"):
        raise RuntimeError(f"lark-cli failed: {result.stderr[-1500:]}")
    
    return data


def load_creators(config):
    table_id = config["tables"]["creators"]["table_id"]
    rows = []
    offset = 0
    
    while True:
        data = run_lark(config, [
            "+record-list", "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--limit", "200", "--offset", str(offset),
            "--field-id", "博主名称",
            "--field-id", "B站MID",
            "--field-id", "是否持续跟踪",
        ])
        payload = data["data"]
        
        for record_id, values in zip(payload["record_id_list"], payload["data"]):
            name = str(values[0] or "").strip()
            mid = str(values[1] or "").strip()
            tracking = values[2] is True
            if tracking and mid:
                rows.append({"name": name, "mid": mid, "record_id": record_id})
        
        if not payload.get("has_more"):
            break
        offset += 200
    
    return rows


def existing_bvids(config):
    table_id = config["tables"]["videos"]["table_id"]
    bvids = set()
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
        for values in payload["data"]:
            bvid = str(values[0] or "").strip()
            if bvid:
                bvids.add(bvid)
        if not payload.get("has_more"):
            break
        offset += 200
    
    return bvids


def get_record_id(data):
    """从 lark-cli 返回中提取 record_id"""
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


def fetch_video_stats_cdp(page, bvid):
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    content = page.evaluate("() => document.body.innerText")
    data = json.loads(content)
    
    if data.get("code") != 0:
        raise RuntimeError(f"获取视频信息失败: {data.get('message')}")
    
    d = data["data"]
    stat = d.get("stat", {})
    return {
        "aid": d["aid"],
        "bvid": d["bvid"],
        "title": d["title"],
        "desc": d.get("desc", ""),
        "pic": d.get("pic", ""),
        "duration": d.get("duration", 0),
        "pubdate": d.get("pubdate", 0),
        "owner": d.get("owner", {}),
        "stat": {
            "view": stat.get("view", 0),
            "danmaku": stat.get("danmaku", 0),
            "reply": stat.get("reply", 0),
            "favorite": stat.get("favorite", 0),
            "coin": stat.get("coin", 0),
            "share": stat.get("share", 0),
            "like": stat.get("like", 0),
        },
    }


def fetch_comments_cdp(bvid, output_path, max_root=20, cdp_endpoint=None):
    args = [
        "node", str(COMMENTS_SCRIPT),
        "--video", bvid,
        "--max-root", str(max_root),
        "--no-replies",
        "--output", str(output_path),
    ]
    if cdp_endpoint:
        args.extend(["--cdp-endpoint", cdp_endpoint])
    
    result = run_command(args, timeout=120, check=False)
    
    count = 0
    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
    return count


def create_video_record(config, creator, video_info, media_path, info_path, desc_path, cover_path, comments_path, comment_count):
    table_id = config["tables"]["videos"]["table_id"]
    tmp_dir = ROOT / ".tmp-lark"
    tmp_dir.mkdir(exist_ok=True)
    
    # 只使用飞书表里真实存在的字段
    from datetime import datetime
    pubdate = video_info.get("pubdate", 0)
    pubdate_str = datetime.fromtimestamp(pubdate).strftime("%Y-%m-%d %H:%M:%S") if pubdate else ""
    
    fields = {
        "BVID": video_info["bvid"],
        "平台": "B站",
        "平台视频ID": str(video_info.get("aid", "")),
        "关联博主": [{"id": creator["record_id"]}],
        "视频标题": video_info.get("title", ""),
        "视频文件路径": str(media_path) if media_path else "",
        "元数据文件路径": str(info_path) if info_path else "",
        "视频文案路径": str(desc_path) if desc_path else "",
        "封面文件路径": str(cover_path) if cover_path else "",
        "评论文件路径": str(comments_path) if comments_path and comment_count > 0 else "",
        "已抓评论数": int(comment_count),
        "视频下载状态": "已下载" if media_path else "失败",
        "评论抓取状态": "已抓取" if comments_path and comment_count > 0 else "未抓取",
        "视频链接": f"https://www.bilibili.com/video/{video_info['bvid']}",
        "时长秒": int(video_info.get("duration", 0)),
        "发布时间": pubdate_str,
        "最近采集时间": now_str(),
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


def create_metric_snapshot(config, video_record_id, stat, bvid):
    table_id = config["tables"]["video_metric_snapshots"]["table_id"]
    tmp_dir = ROOT / ".tmp-lark"
    tmp_dir.mkdir(exist_ok=True)
    
    fields = {
        "BVID": bvid,
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
    creators = load_creators(config)
    creator_map = {c["mid"]: c for c in creators}
    
    print(f"持续跟踪博主: {len(creators)} 个")
    
    # 先清掉飞书表里的测试记录
    existing = existing_bvids(config)
    print(f"飞书现有视频: {len(existing)} 条")
    
    cdp_endpoint = get_cdp_endpoint()
    print(f"CDP: {cdp_endpoint[:60]}...")
    
    # 找出已下载的视频
    to_process = []
    for mid_dir in VIDEOS_ROOT.iterdir():
        if not mid_dir.is_dir():
            continue
        mid = mid_dir.name
        if mid not in creator_map:
            continue
        
        for bv_dir in mid_dir.iterdir():
            if not bv_dir.is_dir():
                continue
            bvid = bv_dir.name
            
            mp4s = list(bv_dir.glob("*.mp4"))
            if not mp4s:
                continue
            
            info_json = bv_dir / f"{bvid}.info.json"
            if not info_json.exists():
                continue
            
            to_process.append({
                "mid": mid,
                "bvid": bvid,
                "dir": bv_dir,
                "media_path": mp4s[0],
                "info_path": info_json,
            })
    
    print(f"\n找到 {len(to_process)} 个已下载视频待写入飞书")
    
    successes = []
    failures = []
    
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_endpoint)
        context = browser.contexts[0]
        page = context.new_page()
        
        for i, item in enumerate(to_process, 1):
            bvid = item["bvid"]
            mid = item["mid"]
            creator = creator_map[mid]
            bv_dir = item["dir"]
            media_path = item["media_path"]
            info_path = item["info_path"]
            
            print(f"\n[{i}/{len(to_process)}] {bvid} - {creator['name']}")
            
            try:
                # 1. 获取视频统计数据
                print("  获取视频数据...")
                video_info = fetch_video_stats_cdp(page, bvid)
                stat = video_info["stat"]
                print(f"    播放:{stat['view']} 点赞:{stat['like']} 投币:{stat['coin']}")
                
                # 2. 保存文案
                desc_path = bv_dir / "video-description.txt"
                with open(desc_path, "w", encoding="utf-8") as f:
                    f.write(video_info.get("desc", ""))
                
                # 3. 保存数据快照
                metrics_path = bv_dir / "metrics-snapshot.json"
                with open(metrics_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "captured_at": now_str(),
                        "bvid": bvid,
                        "aid": video_info["aid"],
                        "metrics": stat,
                        "raw_stat": stat,
                    }, f, ensure_ascii=False, indent=2)
                
                # 4. 封面
                cover_path = bv_dir / f"{bvid}.cover.jpg"
                if not cover_path.exists() and video_info.get("pic"):
                    print("  下载封面...")
                    pic_url = video_info["pic"]
                    if pic_url.startswith("//"):
                        pic_url = "https:" + pic_url
                    try:
                        page.goto(pic_url, wait_until="domcontentloaded", timeout=15000)
                        page.screenshot(path=str(cover_path), full_page=False)
                    except Exception as e:
                        print(f"    封面下载失败: {e}")
                        cover_path = None
                
                # 5. 评论
                comments_path = bv_dir / "comments.jsonl"
                comment_count = 0
                if not comments_path.exists():
                    print("  抓取评论...")
                    comment_count = fetch_comments_cdp(bvid, comments_path, max_root=20, cdp_endpoint=cdp_endpoint)
                else:
                    with open(comments_path, "r", encoding="utf-8") as f:
                        comment_count = sum(1 for line in f if line.strip())
                print(f"    评论: {comment_count} 条")
                
                # 6. 写入飞书视频表
                print("  写入飞书视频表...")
                record_id = create_video_record(
                    config, creator, video_info,
                    media_path, info_path, desc_path, cover_path,
                    comments_path, comment_count
                )
                if not record_id:
                    raise RuntimeError("视频记录创建失败，未返回 record_id")
                print(f"    记录ID: {record_id}")
                
                # 7. 写入数据快照表
                print("  写入数据快照...")
                snapshot_id = create_metric_snapshot(config, record_id, stat, bvid)
                print(f"    快照ID: {snapshot_id}")
                
                successes.append({"bvid": bvid, "creator": creator["name"], "record_id": record_id})
                print("  ✅ 完成")
                
            except Exception as e:
                print(f"  ❌ 失败: {e}")
                failures.append({"bvid": bvid, "creator": creator["name"], "error": str(e)[:200]})
    
    print(f"\n{'='*50}")
    print(f"完成! 成功: {len(successes)}, 失败: {len(failures)}")
    if failures:
        print("失败列表:")
        for f in failures:
            print(f"  - {f['bvid']}: {f['error']}")


if __name__ == "__main__":
    main()
