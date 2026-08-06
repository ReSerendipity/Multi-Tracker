"""
CDP 版本的 B 站视频抓取脚本
通过 Edge 远程调试（已登录态）获取视频完整信息并下载

用法:
    python cdp_bili_download.py --max-creators 5 --videos-per-creator 3
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "feishu-base-config.json"
DOWNLOAD_ROOT = ROOT / "downloads"
VIDEOS_ROOT = DOWNLOAD_ROOT / "videos"
MANIFEST_ROOT = DOWNLOAD_ROOT / "manifests"
CDP_ENDPOINT_URL = "http://127.0.0.1:9222/json/version"
COMMENTS_SCRIPT = ROOT / ".agents" / "skills" / "bilibili-comments" / "scripts" / "fetch_comments.mjs"


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ts_slug():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def get_cdp_endpoint():
    """获取 CDP WebSocket 端点"""
    resp = urllib.request.urlopen(CDP_ENDPOINT_URL)
    info = json.loads(resp.read())
    return info["webSocketDebuggerUrl"]


def run_command(args, *, timeout=None, check=True, cwd=None):
    """运行命令"""
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    
    # 把虚拟环境加到 PATH
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
        raise RuntimeError(
            f"command failed\nargs: {args}\n"
            f"stdout: {result.stdout[-2000:]}\nstderr: {result.stderr[-2000:]}"
        )
    return result


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def run_lark(config, base_args, *, timeout=60):
    """运行 lark-cli 命令"""
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
    # lark-cli 可能将 JSON 输出到 stdout 或 stderr
    for text in [stdout, result.stderr]:
        start = text.find("{")
        if start >= 0:
            decoder = json.JSONDecoder()
            data, _ = decoder.raw_decode(text[start:])
            if result.returncode != 0 or not data.get("ok"):
                raise RuntimeError(f"lark-cli failed: {text[-2000:]}")
            return data
    
    raise RuntimeError(f"lark-cli no JSON: {stdout[:500]}\nstderr: {result.stderr[-500:]}")


def load_creators(config, max_creators=None):
    """加载持续跟踪的博主"""
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
            "--field-id", "博主名称",
            "--field-id", "B站MID",
            "--field-id", "是否持续跟踪",
        ]
        data = run_lark(config, args)
        payload = data["data"]
        
        for record_id, values in zip(payload["record_id_list"], payload["data"]):
            name = str(values[0] or "").strip()
            mid = str(values[1] or "").strip()
            tracking = values[2] is True
            if tracking and mid:
                rows.append({
                    "name": name,
                    "mid": mid,
                    "space_url": f"https://space.bilibili.com/{mid}/video",
                    "record_id": record_id,
                })
        
        if not payload.get("has_more"):
            break
        offset += 200
    
    if max_creators:
        rows = rows[:max_creators]
    return rows


def existing_bvids(config):
    """获取已存在的 BVID"""
    table_id = config["tables"]["videos"]["table_id"]
    bvids = set()
    offset = 0
    
    while True:
        args = [
            "+record-list",
            "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--limit", "200",
            "--offset", str(offset),
            "--field-id", "BVID",
        ]
        data = run_lark(config, args)
        payload = data["data"]
        
        for values in payload["data"]:
            bvid = str(values[0] or "").strip()
            if bvid:
                bvids.add(bvid)
        
        if not payload.get("has_more"):
            break
        offset += 200
    
    return bvids


def fetch_creator_videos_cdp(page, mid, per_creator=3):
    """通过 CDP 访问 UP 主空间页面，提取最新视频列表"""
    url = f"https://space.bilibili.com/{mid}/video"
    
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)  # 等待列表加载
        
        videos = page.evaluate(f"""() => {{
            const out = [];
            const seen = new Set();
            const links = document.querySelectorAll('a[href*="/video/BV"]');
            for (const a of links) {{
                const match = a.href.match(/\\/video\\/(BV[0-9A-Za-z]{{10}})/);
                if (!match || seen.has(match[1])) continue;
                const bvid = match[1];
                const title = (a.textContent || '').trim();
                if (!title || title.length < 2) continue;
                // 只在视频列表区域找
                const card = a.closest('.small-item, .video-item, .list-item, .cube-item, .bili-video-card');
                if (!card) continue;
                seen.add(bvid);
                out.push({{
                    bvid: bvid,
                    title: title,
                    url: `https://www.bilibili.com/video/${{bvid}}`,
                }});
                if (out.length >= {per_creator}) break;
            }}
            return out;
        }}""")
        
        return videos[:per_creator] if videos else None
    except Exception as e:
        print(f"    CDP 页面方式失败: {e}")
        return None


def fetch_creator_videos(mid, per_creator=3, page=None):
    """获取博主最新视频列表：先试 yt-dlp，失败用 CDP"""
    # 先用 CDP 方式（更稳定，有登录态）
    if page is not None:
        videos = fetch_creator_videos_cdp(page, mid, per_creator)
        if videos:
            return videos
    
    # 回退：yt-dlp
    space_url = f"https://space.bilibili.com/{mid}/video"
    
    args = [
        "yt-dlp",
        "--no-update",
        "--flat-playlist",
        "--playlist-items", f"1:{per_creator}",
        "--dump-json",
        space_url,
    ]
    
    result = run_command(args, timeout=90, check=False)
    
    videos = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            entry = json.loads(line)
            bvid = entry.get("id") or entry.get("webpage_url_basename")
            title = entry.get("title", "")
            url = entry.get("url") or entry.get("webpage_url") or f"https://www.bilibili.com/video/{bvid}"
            if bvid:
                videos.append({
                    "bvid": bvid,
                    "title": title,
                    "url": url,
                })
        except:
            pass
    
    return videos[:per_creator] if videos else None


def download_video_ytdlp(bvid, out_dir):
    """用 yt-dlp 下载视频（不带 cookies）"""
    url = f"https://www.bilibili.com/video/{bvid}"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    args = [
        "yt-dlp",
        "--no-update",
        "--write-info-json",
        "--write-thumbnail",
        "--output", str(out_dir / f"{bvid}.%(ext)s"),
        "--merge-output-format", "mp4",
        url,
    ]
    
    result = run_command(args, timeout=300, check=False)
    
    # 找下载的文件
    info_path = out_dir / f"{bvid}.info.json"
    media_path = None
    for p in out_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".mp4", ".mkv", ".webm", ".flv"}:
            if p.name != f"{bvid}.info.json" and not p.name.endswith(".part"):
                media_path = p
                break
    
    if media_path and info_path.exists():
        return media_path, info_path
    
    raise RuntimeError(f"下载失败: {result.stderr[-500:] if result.stderr else 'unknown'}")


def fetch_video_stats_cdp(page, bvid):
    """通过 CDP 获取视频统计数据"""
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    content = page.evaluate("() => document.body.innerText")
    data = json.loads(content)
    
    if data.get("code") != 0:
        raise RuntimeError(f"获取视频信息失败: {data.get('message')}")
    
    d = data["data"]
    stat = d.get("stat", {})
    from datetime import datetime
    pubdate_ts = d.get("pubdate", 0)
    pubdate_str = datetime.fromtimestamp(pubdate_ts).strftime("%Y-%m-%d %H:%M:%S") if pubdate_ts else ""
    return {
        "aid": d["aid"],
        "bvid": d["bvid"],
        "title": d["title"],
        "desc": d.get("desc", ""),
        "pic": d.get("pic", ""),
        "owner": d.get("owner", {}),
        "duration": d.get("duration", 0),
        "pubdate": pubdate_ts,
        "pubdate_str": pubdate_str,
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


def fetch_comments_cdp(bvid, output_path, max_root=50, cdp_endpoint=None):
    """通过 CDP 脚本抓取评论"""
    args = [
        "node",
        str(COMMENTS_SCRIPT),
        "--video", bvid,
        "--max-root", str(max_root),
        "--no-replies",
        "--output", str(output_path),
    ]
    if cdp_endpoint:
        args.extend(["--cdp-endpoint", cdp_endpoint])
    
    result = run_command(args, timeout=120, check=False)
    
    # 从输出文件统计评论数
    stats = {"root_comments": 0, "reply_comments": 0, "total_rows": 0}
    
    if output_path.exists():
        count = 0
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        stats["total_rows"] = count
        stats["root_comments"] = count
    
    # 同时尝试从输出中解析 JSON
    all_output = result.stdout + "\n" + result.stderr
    for line in all_output.splitlines():
        line = line.strip()
        if line.startswith("{") and "root_comments" in line:
            try:
                s = json.loads(line)
                stats["root_comments"] = s.get("root_comments", stats["root_comments"])
                stats["reply_comments"] = s.get("reply_comments", 0)
                stats["title"] = s.get("title", "")
                if s.get("total_rows", 0) > stats["total_rows"]:
                    stats["total_rows"] = s["total_rows"]
            except:
                pass
    
    return stats


def create_video_record(config, creator, video_info, media_path, info_path, desc_path, cover_path, comments_path, comment_count):
    """在飞书创建视频记录"""
    table_id = config["tables"]["videos"]["table_id"]
    
    tmp_dir = ROOT / ".tmp-lark"
    tmp_dir.mkdir(exist_ok=True)
    
    fields = {
        "BVID": video_info["bvid"],
        "平台": "B站",
        "平台视频ID": str(video_info.get("aid", "")),
        "关联博主": [{"id": creator["record_id"]}],
        "视频标题": video_info.get("title", ""),
        "视频文案": video_info.get("desc", "")[:2000] if video_info.get("desc") else "",
        "视频文件路径": str(media_path) if media_path else "",
        "元数据文件路径": str(info_path) if info_path else "",
        "视频文案路径": str(desc_path) if desc_path else "",
        "封面文件路径": str(cover_path) if cover_path else "",
        "评论文件路径": str(comments_path) if comments_path else "",
        "已抓评论数": int(comment_count),
        "视频下载状态": "已下载" if media_path else "失败",
        "评论抓取状态": "已抓取" if comments_path and comment_count > 0 else "未抓取",
        "视频链接": f"https://www.bilibili.com/video/{video_info['bvid']}",
        "时长秒": int(video_info.get("duration", 0)),
        "发布时间": video_info.get("pubdate_str", ""),
        "最近采集时间": now_str(),
    }
    
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=tmp_dir, delete=False) as f:
        json.dump(fields, f, ensure_ascii=False)
        payload_path = Path(f.name)
    
    try:
        data = run_lark(config, [
            "+record-upsert",
            "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--json", f"@{payload_path.relative_to(ROOT)}",
        ], timeout=60)
        
        record_id = data["data"]["record"]["record_id_list"][0] if data["data"].get("record", {}).get("record_id_list") else data["data"].get("record_id")
        
        # 上传封面附件
        if cover_path and cover_path.exists() and record_id:
            try:
                run_lark(config, [
                    "+record-upload-attachment",
                    "--as", "user",
                    "--base-token", config["base_token"],
                    "--table-id", table_id,
                    "--record-id", record_id,
                    "--field-id", "封面",
                    "--file", str(cover_path.relative_to(ROOT)),
                ], timeout=60)
            except Exception as e:
                print(f"    ⚠️ 封面上传失败: {e}")
        
        return record_id
    finally:
        try:
            payload_path.unlink(missing_ok=True)
        except:
            pass


def create_metric_snapshot(config, video_record_id, stat, bvid):
    """创建数据快照"""
    table_id = config["tables"]["video_metric_snapshots"]["table_id"]
    
    tmp_dir = ROOT / ".tmp-lark"
    tmp_dir.mkdir(exist_ok=True)
    
    fields = {
        "关联视频": [{"id": video_record_id}],
        "播放量": stat.get("view", 0),
        "点赞量": stat.get("like", 0),
        "投币数": stat.get("coin", 0),
        "收藏数": stat.get("favorite", 0),
        "分享数": stat.get("share", 0),
        "评论数": stat.get("reply", 0),
        "弹幕数": stat.get("danmaku", 0),
        "快照时间": now_str(),
    }
    
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=tmp_dir, delete=False) as f:
        json.dump(fields, f, ensure_ascii=False)
        payload_path = Path(f.name)
    
    try:
        data = run_lark(config, [
            "+record-upsert",
            "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--json", f"@{payload_path.relative_to(ROOT)}",
        ], timeout=60)
        
        return data["data"]["record"]["record_id_list"][0] if data["data"].get("record", {}).get("record_id_list") else data["data"].get("record_id")
    finally:
        try:
            payload_path.unlink(missing_ok=True)
        except:
            pass


def download_cover(page, pic_url, out_dir, bvid):
    """下载封面图"""
    if not pic_url:
        return None
    
    if pic_url.startswith("//"):
        pic_url = "https:" + pic_url
    
    cover_path = out_dir / f"{bvid}.cover.jpg"
    
    try:
        page.goto(pic_url, wait_until="domcontentloaded", timeout=15000)
        # 截图方式获取图片
        page.screenshot(path=str(cover_path), full_page=False)
        return cover_path
    except Exception as e:
        print(f"    封面下载失败: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="CDP 版本 B 站视频抓取")
    parser.add_argument("--max-creators", type=int, default=None, help="最多处理多少个博主")
    parser.add_argument("--videos-per-creator", type=int, default=3, help="每个博主抓几条最新视频")
    parser.add_argument("--max-total-videos", type=int, default=None, help="总共最多抓多少条")
    parser.add_argument("--comment-limit", type=int, default=50, help="每个视频抓多少条一级评论")
    args = parser.parse_args()
    
    started_at = now_str()
    started_perf = time.perf_counter()
    
    print("=" * 60)
    print(f"CDP B站视频抓取 - {started_at}")
    print("=" * 60)
    
    # 1. 初始化
    config = load_config()
    VIDEOS_ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST_ROOT.mkdir(parents=True, exist_ok=True)
    
    # 2. 获取 CDP 端点
    print("\n[1/5] 连接浏览器...")
    cdp_endpoint = get_cdp_endpoint()
    print(f"  CDP端点: {cdp_endpoint[:60]}...")
    
    # 3. 加载博主
    print("\n[2/5] 加载持续跟踪的博主...")
    creators = load_creators(config, args.max_creators)
    print(f"  找到 {len(creators)} 个持续跟踪的博主")
    for c in creators:
        print(f"    - {c['name']} (MID: {c['mid']})")
    
    # 4. 获取已存在的 BVID
    existing = existing_bvids(config)
    print(f"  飞书已有 {len(existing)} 条视频记录")
    
    # 5. 逐个处理
    print("\n[3/5] 开始抓取视频...")
    successes = []
    failures = []
    skipped = []
    total_downloaded = 0
    
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_endpoint)
        context = browser.contexts[0]
        page = context.new_page()
        
        # 验证登录态
        page.goto("https://api.bilibili.com/x/web-interface/nav", wait_until="domcontentloaded", timeout=30000)
        nav_data = json.loads(page.evaluate("() => document.body.innerText"))
        if nav_data.get("code") == 0:
            print(f"  ✅ 登录态验证: {nav_data['data']['uname']} (Lv{nav_data['data']['level_info']['current_level']})")
        else:
            print(f"  ⚠️  登录态: {nav_data.get('message')}")
        
        for ci, creator in enumerate(creators, 1):
            print(f"\n[{ci}/{len(creators)}] {creator['name']} (MID: {creator['mid']})")
            
            # 获取视频列表
            try:
                videos = fetch_creator_videos(creator["mid"], args.videos_per_creator, page=page)
                if not videos:
                    print(f"  ⚠️  未获取到视频列表")
                    continue
                print(f"  最新 {len(videos)} 条视频:")
                for v in videos:
                    print(f"    - {v['title'][:40]} ({v['bvid']})")
            except Exception as e:
                print(f"  ❌ 获取视频列表失败: {e}")
                continue
            
            for vi, video in enumerate(videos, 1):
                bvid = video["bvid"]
                
                if args.max_total_videos and total_downloaded >= args.max_total_videos:
                    break
                
                if bvid in existing:
                    print(f"  ⏭️  {bvid} 已存在，跳过")
                    skipped.append(bvid)
                    continue
                
                print(f"\n  [{vi}/{len(videos)}] 处理 {bvid}: {video['title'][:40]}...")
                out_dir = VIDEOS_ROOT / creator["mid"] / bvid
                out_dir.mkdir(parents=True, exist_ok=True)
                
                try:
                    # 1. 获取详细统计数据
                    print(f"    获取视频数据...")
                    video_info = fetch_video_stats_cdp(page, bvid)
                    stat = video_info["stat"]
                    print(f"    播放:{stat['view']} 点赞:{stat['like']} 投币:{stat['coin']} 收藏:{stat['favorite']} 评论:{stat['reply']}")
                    
                    # 2. 保存数据快照
                    metrics_path = out_dir / "metrics-snapshot.json"
                    with open(metrics_path, "w", encoding="utf-8") as f:
                        json.dump({
                            "captured_at": now_str(),
                            "bvid": bvid,
                            "aid": video_info["aid"],
                            "metrics": stat,
                            "raw_stat": stat,
                        }, f, ensure_ascii=False, indent=2)
                    
                    # 3. 保存视频文案
                    desc_path = out_dir / "video-description.txt"
                    with open(desc_path, "w", encoding="utf-8") as f:
                        f.write(video_info.get("desc", ""))
                    
                    # 4. 下载封面
                    print(f"    下载封面...")
                    cover_path = download_cover(page, video_info.get("pic", ""), out_dir, bvid)
                    
                    # 5. 下载视频
                    print(f"    下载视频...")
                    media_path, info_path = download_video_ytdlp(bvid, out_dir)
                    print(f"    视频下载完成: {media_path.name} ({media_path.stat().st_size // 1024}KB)")
                    
                    # 6. 抓取评论
                    print(f"    抓取评论...")
                    comments_path = out_dir / "comments.jsonl"
                    comment_stats = fetch_comments_cdp(
                        bvid, comments_path, 
                        max_root=args.comment_limit,
                        cdp_endpoint=cdp_endpoint
                    )
                    comment_count = comment_stats.get("total_rows", 0)
                    print(f"    评论抓取完成: {comment_count} 条")
                    
                    # 7. 写入飞书视频表
                    print(f"    写入飞书...")
                    record_id = create_video_record(
                        config, creator, video_info,
                        media_path, info_path, desc_path, cover_path,
                        comments_path if comment_count > 0 else None, comment_count
                    )
                    
                    # 8. 写入数据快照表
                    snapshot_id = create_metric_snapshot(config, record_id, stat, bvid)
                    
                    successes.append({
                        "creator": creator["name"],
                        "mid": creator["mid"],
                        "bvid": bvid,
                        "title": video.get("title", ""),
                        "video_path": str(media_path),
                        "info_path": str(info_path),
                        "description_path": str(desc_path),
                        "cover_path": str(cover_path) if cover_path else None,
                        "comments_path": str(comments_path),
                        "comment_count": comment_count,
                        "metrics_path": str(metrics_path),
                        "record_id": record_id,
                        "snapshot_id": snapshot_id,
                    })
                    
                    total_downloaded += 1
                    existing.add(bvid)
                    print(f"    ✅ 完成")
                    
                except Exception as e:
                    print(f"    ❌ 失败: {e}")
                    failures.append({"bvid": bvid, "creator": creator["name"], "error": str(e)[:200]})
    
    # 6. 写 manifest
    print("\n[4/5] 保存任务清单...")
    manifest = {
        "started_at": started_at,
        "ended_at": now_str(),
        "creator_count": len(creators),
        "successes": successes,
        "failures": failures,
        "skipped_existing": skipped,
        "summary": {
            "downloaded": len(successes),
            "failed": len(failures),
            "skipped_existing": len(skipped),
            "created_video_records": len(successes),
            "created_metric_snapshots": len(successes),
        },
        "total_seconds": round(time.perf_counter() - started_perf, 3),
    }
    
    manifest_path = MANIFEST_ROOT / f"{ts_slug()}-cdp-bili-download.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    # 7. 输出结果
    print("\n" + "=" * 60)
    print("完成!")
    print("=" * 60)
    print(f"  成功: {len(successes)}")
    print(f"  失败: {len(failures)}")
    print(f"  跳过(已存在): {len(skipped)}")
    print(f"  总耗时: {round(time.perf_counter() - started_perf, 1)} 秒")
    print(f"  Manifest: {manifest_path}")
    
    if failures:
        print("\n失败列表:")
        for f in failures[:5]:
            print(f"  - {f['bvid']} ({f['creator']}): {f['error'][:80]}")


if __name__ == "__main__":
    main()
