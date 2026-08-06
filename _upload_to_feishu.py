"""
把封面图上传为飞书附件字段，把视频文案写入文本字段
这样在飞书表格里就能直接预览内容了
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "feishu-base-config.json"
VIDEOS_ROOT = ROOT / "downloads" / "videos"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def run_lark(config, base_args, *, timeout=120):
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


def upload_cover(config, record_id, cover_path):
    """上传封面图到附件字段（需要相对路径）"""
    rel_path = cover_path.relative_to(ROOT)
    data = run_lark(config, [
        "+record-upload-attachment", "--as", "user",
        "--base-token", config["base_token"],
        "--table-id", config["tables"]["videos"]["table_id"],
        "--record-id", record_id,
        "--field-id", "封面",
        "--file", str(rel_path),
    ], timeout=120)
    return data.get("data", {}).get("file_tokens", [])


def update_video_desc(config, record_id, desc):
    """更新视频文案字段"""
    import tempfile
    tmp_dir = ROOT / ".tmp-lark"
    tmp_dir.mkdir(exist_ok=True)
    
    fields = {"视频文案": desc[:50000] if desc else ""}  # 飞书文本字段有限制
    
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=tmp_dir, delete=False) as f:
        json.dump(fields, f, ensure_ascii=False)
        payload_path = Path(f.name)
    
    try:
        data = run_lark(config, [
            "+record-upsert", "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", config["tables"]["videos"]["table_id"],
            "--record-id", record_id,
            "--json", f"@{payload_path.relative_to(ROOT)}",
        ], timeout=60)
        return True
    finally:
        try:
            payload_path.unlink(missing_ok=True)
        except:
            pass


def find_cover_file(bv_dir):
    """找封面文件"""
    # 优先找 *.cover.jpg
    covers = list(bv_dir.glob("*.cover.jpg"))
    if covers:
        return covers[0]
    
    # 再找 *.jpg (排除视频文件本身的缩略图，选第二大的)
    jpgs = sorted(bv_dir.glob("*.jpg"), key=lambda p: p.stat().st_size, reverse=True)
    for jpg in jpgs:
        if jpg.stat().st_size > 50000:  # 大于 50KB 大概率是封面
            return jpg
    
    return None


def find_desc_file(bv_dir):
    """找视频描述文件"""
    # 先找 video-description.txt
    desc_file = bv_dir / "video-description.txt"
    if desc_file.exists() and desc_file.stat().st_size > 0:
        return desc_file
    
    # 从 info.json 里读
    info_files = list(bv_dir.glob("*.info.json"))
    if not info_files:
        info_files = list(bv_dir.glob("info.json"))
    
    if info_files:
        try:
            with open(info_files[0], "r", encoding="utf-8") as f:
                info = json.load(f)
            desc = info.get("description", "") or info.get("desc", "")
            if desc:
                out = bv_dir / "video-description.txt"
                out.write_text(desc, encoding="utf-8")
                return out
        except:
            pass
    
    return None


def main():
    config = load_config()
    
    # 获取视频记录映射
    video_map = list_video_records(config)
    print(f"飞书视频表: {len(video_map)} 条记录")
    
    successes_cover = 0
    successes_desc = 0
    failures = []
    
    for bvid, record_id in video_map.items():
        # 找本地目录
        bv_dir = None
        for mid_dir in VIDEOS_ROOT.iterdir():
            if not mid_dir.is_dir():
                continue
            candidate = mid_dir / bvid
            if candidate.is_dir():
                bv_dir = candidate
                break
        
        if not bv_dir:
            print(f"⚠️  {bvid} 找不到本地目录，跳过")
            continue
        
        print(f"\n{bvid}:")
        
        # 上传封面
        cover = find_cover_file(bv_dir)
        if cover:
            try:
                print(f"  上传封面: {cover.name} ({cover.stat().st_size // 1024}KB)...", end=" ")
                tokens = upload_cover(config, record_id, cover)
                print(f"✅ ({len(tokens)} 个文件)")
                successes_cover += 1
            except Exception as e:
                print(f"❌ 封面上传失败: {e}")
                failures.append(f"{bvid} 封面: {str(e)[:100]}")
        else:
            print(f"  ⚠️  找不到封面文件")
        
        # 写入视频文案
        desc_file = find_desc_file(bv_dir)
        if desc_file:
            try:
                desc = desc_file.read_text(encoding="utf-8", errors="replace")
                print(f"  写入文案: {len(desc)} 字...", end=" ")
                update_video_desc(config, record_id, desc)
                print("✅")
                successes_desc += 1
            except Exception as e:
                print(f"❌ 文案写入失败: {e}")
                failures.append(f"{bvid} 文案: {str(e)[:100]}")
        else:
            print(f"  ⚠️  找不到视频文案")
    
    print(f"\n{'='*50}")
    print(f"完成! 封面: {successes_cover}/{len(video_map)}, 文案: {successes_desc}/{len(video_map)}")
    if failures:
        print(f"失败 {len(failures)} 项:")
        for f in failures:
            print(f"  - {f}")


if __name__ == "__main__":
    main()
