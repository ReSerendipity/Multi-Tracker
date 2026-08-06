"""
测试四个平台的可用性
"""
import json
import urllib.request
import urllib.error
import sys
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

def test_bilibili():
    """测试 B站 API 和 CDP"""
    print("=" * 50)
    print("1/4 B站")
    print("=" * 50)
    
    # 测试 CDP
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=5)
        ver = json.loads(resp.read())
        print(f"  CDP: OK ({ver.get('Browser','?')})")
    except Exception as e:
        print(f"  CDP: FAIL ({e})")
        return False
    
    # 测试 B站 API
    try:
        resp = urllib.request.urlopen("https://api.bilibili.com/x/web-interface/view?bvid=BV1aQKb6QE1m", timeout=10)
        data = json.loads(resp.read())
        if data.get("data"):
            d = data["data"]
            title = d.get("title", "?")[:40]
            view = d.get("stat", {}).get("view", 0)
            print(f"  API: OK - {title} (播放:{view})")
        else:
            print(f"  API: FAIL - code={data.get('code')}, msg={data.get('message')}")
            return False
    except Exception as e:
        print(f"  API: FAIL ({e})")
        return False
    
    print("  结论: B站可用 ✅")
    return True


def test_douyin():
    """测试 抖音"""
    print("\n" + "=" * 50)
    print("2/4 抖音")
    print("=" * 50)
    
    # 检查 CDP bridge 脚本
    bridge_path = ROOT / ".agents" / "skills" / "douyin-comments" / "scripts" / "douyin_cdp_bridge.mjs"
    if bridge_path.exists():
        print(f"  CDP Bridge: OK ({bridge_path.name})")
    else:
        print(f"  CDP Bridge: FAIL - {bridge_path} 不存在")
        return False
    
    # 检查下载脚本
    dl_path = ROOT / "download_douyin_latest.py"
    if dl_path.exists():
        print(f"  下载脚本: OK ({dl_path.name})")
    else:
        print(f"  下载脚本: FAIL")
        return False
    
    # 检查飞书同步脚本
    sync_path = ROOT / "sync_douyin_to_feishu.py"
    if sync_path.exists():
        print(f"  飞书同步: OK ({sync_path.name})")
    else:
        print(f"  飞书同步: FAIL")
        return False
    
    # 检查评论技能
    comments_skill = ROOT / ".agents" / "skills" / "douyin-comments" / "SKILL.md"
    if comments_skill.exists():
        print(f"  评论技能: OK (douyin-comments)")
    else:
        print(f"  评论技能: FAIL")
    
    print("  注意: 抖音需要 Chrome 浏览器(不是Edge)运行调试模式")
    print("  结论: 抖音脚本完整，需要Chrome调试环境 ⚠️")
    return True


def test_kuaishou():
    """测试 快手"""
    print("\n" + "=" * 50)
    print("3/4 快手")
    print("=" * 50)
    
    # 检查 CDP bridge 脚本
    bridge_path = ROOT / ".agents" / "skills" / "kuaishou-comments" / "scripts" / "kuaishou_cdp_bridge.mjs"
    if bridge_path.exists():
        print(f"  CDP Bridge: OK")
    else:
        print(f"  CDP Bridge: 缺失 ({bridge_path})")
    
    # 检查下载脚本
    dl_path = ROOT / "download_kuaishou_latest.py"
    if dl_path.exists():
        print(f"  下载脚本: OK ({dl_path.name})")
    else:
        print(f"  下载脚本: FAIL")
        return False
    
    # 检查飞书同步脚本
    sync_path = ROOT / "sync_kuaishou_to_feishu.py"
    if sync_path.exists():
        print(f"  飞书同步: OK ({sync_path.name})")
    else:
        print(f"  飞书同步: FAIL")
        return False
    
    # 检查评论技能
    comments_skill = ROOT / ".agents" / "skills" / "kuaishou-comments" / "SKILL.md"
    if comments_skill.exists():
        print(f"  评论技能: OK")
    else:
        print(f"  评论技能: 缺失 (kuaishou-comments)")
    
    print("  结论: 快手有下载和同步，缺评论抓取 ⚠️")
    return True


def test_xiaohongshu():
    """测试 小红书"""
    print("\n" + "=" * 50)
    print("4/4 小红书")
    print("=" * 50)
    
    # 检查 CDP bridge 脚本
    bridge_path = ROOT / ".agents" / "skills" / "xiaohongshu-comments" / "scripts" / "xiaohongshu_cdp_bridge.mjs"
    if bridge_path.exists():
        print(f"  CDP Bridge: OK")
    else:
        print(f"  CDP Bridge: 缺失 ({bridge_path})")
    
    # 检查下载脚本
    dl_path = ROOT / "download_xiaohongshu_latest.py"
    if dl_path.exists():
        print(f"  下载脚本: OK ({dl_path.name})")
    else:
        print(f"  下载脚本: FAIL")
        return False
    
    # 检查飞书同步脚本
    sync_path = ROOT / "sync_xiaohongshu_to_feishu.py"
    if sync_path.exists():
        print(f"  飞书同步: OK ({sync_path.name})")
    else:
        print(f"  飞书同步: FAIL")
        return False
    
    # 检查评论技能
    comments_skill = ROOT / ".agents" / "skills" / "xiaohongshu-comments" / "SKILL.md"
    if comments_skill.exists():
        print(f"  评论技能: OK")
    else:
        print(f"  评论技能: 缺失 (xiaohongshu-comments)")
    
    print("  结论: 小红书有下载和同步，缺评论抓取 ⚠️")
    return True


def test_feishu():
    """测试飞书 CLI"""
    print("\n" + "=" * 50)
    print("飞书 CLI 状态")
    print("=" * 50)
    
    env = os.environ.copy()
    env["LARK_CLI_NO_PROXY"] = "1"
    
    try:
        result = subprocess.run(
            ["lark-cli", "auth", "status", "--profile", "default"],
            capture_output=True, text=True, timeout=10,
            env=env, encoding="utf-8", errors="replace"
        )
        output = result.stdout + result.stderr
        if "authenticated" in output.lower() or "ok" in output.lower():
            print("  认证: OK")
        else:
            print(f"  认证: {output[:200]}")
    except Exception as e:
        print(f"  认证: FAIL ({e})")
    
    # 测试读取飞书视频表
    try:
        result = subprocess.run(
            ["lark-cli", "--profile", "default", "base", "+record-list",
             "--as", "user",
             "--base-token", "ZCf1bxiooaqQHPsEKQAcIaARndf",
             "--table-id", "tblux1rdtJBP1hMZ",
             "--limit", "5",
             "--field-id", "BVID",
             "--field-id", "平台",
             "--field-id", "视频标题",
             "--format", "json"],
            capture_output=True, text=True, timeout=30,
            cwd=str(ROOT), env=env, encoding="utf-8", errors="replace"
        )
        start = result.stdout.find("{")
        if start >= 0:
            data = json.loads(result.stdout[start:])
            if data.get("ok"):
                records = data["data"]["data"]
                print(f"  视频表: OK ({len(records)} 条记录)")
                for rec in records[:5]:
                    bvid = rec[0] if rec[0] else "?"
                    platform = rec[1] if len(rec) > 1 and rec[1] else "?"
                    title = rec[2][:30] if len(rec) > 2 and rec[2] else "?"
                    print(f"    {platform} | {bvid} | {title}")
            else:
                print(f"  视频表: FAIL")
        else:
            print(f"  视频表: FAIL (no JSON)")
    except Exception as e:
        print(f"  视频表: FAIL ({e})")


def main():
    print("多平台可用性测试")
    print("=" * 50)
    
    results = {}
    results["bilibili"] = test_bilibili()
    results["douyin"] = test_douyin()
    results["kuaishou"] = test_kuaishou()
    results["xiaohongshu"] = test_xiaohongshu()
    test_feishu()
    
    print("\n" + "=" * 50)
    print("总结")
    print("=" * 50)
    for platform, ok in results.items():
        status = "✅" if ok else "❌"
        print(f"  {platform}: {status}")


if __name__ == "__main__":
    main()
