"""
将 B 站关注列表批量导入飞书博主表
"""
import json
import subprocess
import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "feishu-base-config.json"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def run_lark(config, base_args, *, timeout=60):
    """运行 lark-cli 命令并返回解析后的 JSON"""
    env = os.environ.copy()
    env.pop("HERMES_HOME", None)
    env.pop("HERMES_GIT_BASH_PATH", None)
    env["LARK_CLI_NO_PROXY"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    
    args = ["lark-cli", "--profile", config["profile"], "base", *base_args, "--format", "json"]
    
    # 处理 .cmd 后缀
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
    
    # 从 stdout 中提取 JSON
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


def list_existing_creators(config):
    """获取飞书表中已有的博主"""
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
        offset += 500
    
    return rows


def batch_create_creators(config, creators, batch_size=200):
    """批量创建博主记录"""
    table_id = config["tables"]["creators"]["table_id"]
    total = len(creators)
    created = 0
    
    tmp_dir = ROOT / ".tmp-lark"
    tmp_dir.mkdir(exist_ok=True)
    
    for i in range(0, total, batch_size):
        batch = creators[i:i+batch_size]
        
        # 构造 fields + rows 格式（lark-cli 标准格式）
        fields = ["博主名称", "B站MID", "主页链接", "是否持续跟踪"]
        rows = []
        for c in batch:
            rows.append([
                c["name"],
                c["mid"],
                f"https://space.bilibili.com/{c['mid']}",
                True,
            ])
        
        payload = {"fields": fields, "rows": rows}
        
        # 写入临时 JSON 文件
        import tempfile
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=tmp_dir, delete=False) as f:
            json.dump(payload, f, ensure_ascii=False)
            payload_path = Path(f.name)
        
        args = [
            "+record-batch-create",
            "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--json", f"@{payload_path.relative_to(ROOT)}",
        ]
        
        try:
            data = run_lark(config, args, timeout=120)
            batch_created = len(data["data"].get("record_id_list", []))
            created += batch_created
            print(f"  第 {i//batch_size + 1} 批: 成功创建 {batch_created} 条 ({i+1}-{min(i+batch_size, total)})")
        except Exception as e:
            print(f"  第 {i//batch_size + 1} 批失败: {e}")
        finally:
            try:
                payload_path.unlink(missing_ok=True)
            except:
                pass
    
    return created


def main():
    # 1. 加载配置
    config = load_config()
    
    # 2. 读取关注列表
    input_file = ROOT / "博主ID.txt"
    if not input_file.exists():
        print(f"错误: 找不到文件 {input_file}")
        sys.exit(1)
    
    with open(input_file, "r", encoding="utf-8") as f:
        following = json.load(f)
    
    print(f"读取到 {len(following)} 个关注的 UP 主")
    
    # 3. 获取已存在的博主（按 MID 去重）
    print("\n正在检查飞书表中已有的博主...")
    existing = list_existing_creators(config)
    existing_mids = {c["mid"] for c in existing}
    print(f"飞书表中已有 {len(existing_mids)} 个博主")
    
    # 4. 过滤掉已存在的
    new_creators = [c for c in following if c["mid"] not in existing_mids]
    print(f"需要新增 {len(new_creators)} 个博主")
    
    if not new_creators:
        print("\n没有新的博主需要添加，全部已存在。")
        return
    
    # 5. 批量创建
    print(f"\n开始批量导入到飞书博主表...")
    created = batch_create_creators(config, new_creators)
    print(f"\n✅ 完成！成功导入 {created}/{len(new_creators)} 个新博主")
    print(f"   飞书博主表现在共有 {len(existing_mids) + created} 个博主")


if __name__ == "__main__":
    main()
