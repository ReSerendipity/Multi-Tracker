#!/usr/bin/env python3
"""环境检查脚本 - 验证项目依赖是否正确安装"""

import sys
import subprocess
import importlib
from pathlib import Path


def check_python_version():
    """检查Python版本"""
    version = sys.version_info
    print(f"[OK] Python版本: {version.major}.{version.minor}.{version.micro}")
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("[FAIL] 需要Python 3.8或更高版本")
        return False
    return True


def check_package(package_name, import_name=None):
    """检查Python包是否安装"""
    try:
        if import_name:
            importlib.import_module(import_name)
        else:
            importlib.import_module(package_name)
        print(f"[OK] {package_name} 已安装")
        return True
    except ImportError:
        print(f"[FAIL] {package_name} 未安装")
        return False


def check_command(command, name, extra_paths=None, version_flag="--version"):
    """检查外部命令是否可用"""
    # 先检查本地路径
    if extra_paths:
        for p in extra_paths:
            try:
                result = subprocess.run(
                    [str(p), version_flag],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                # ffmpeg 输出到 stderr，检查 stdout 和 stderr
                output = result.stdout + result.stderr
                if result.returncode == 0 and output:
                    print(f"[OK] {name} 已安装 (本地: {p})")
                    return True
                # 某些工具用 -h 也能返回 0
                if version_flag != "-h":
                    result2 = subprocess.run(
                        [str(p), "-h"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result2.returncode == 0:
                        print(f"[OK] {name} 已安装 (本地: {p})")
                        return True
            except Exception:
                pass
    # 再检查系统 PATH
    try:
        result = subprocess.run(
            [command, version_flag],
            capture_output=True,
            text=True,
            timeout=5
        )
        output = result.stdout + result.stderr
        if result.returncode == 0 and output:
            print(f"[OK] {name} 已安装")
            return True
        else:
            print(f"[FAIL] {name} 未正确安装")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print(f"[FAIL] {name} 未找到")
        return False


def check_project_files():
    """检查项目文件是否存在"""
    project_root = Path(__file__).parent
    required_files = [
        "feishu-base-config.json",
        "download_bili_following_latest.py",
        "download_douyin_latest.py",
        "download_xiaohongshu_latest.py",
        "download_kuaishou_latest.py",
        "download_all_platform_latest.py",
        "postprocess_bili_videos.py",
        "requirements.txt"
    ]
    
    missing_files = []
    for file_name in required_files:
        file_path = project_root / file_name
        if file_path.exists():
            print(f"[OK] {file_name} 存在")
        else:
            print(f"[FAIL] {file_name} 缺失")
            missing_files.append(file_name)
    
    return len(missing_files) == 0


def main():
    """主检查函数"""
    print("=" * 50)
    print("项目环境检查")
    print("=" * 50)
    
    all_ok = True
    
    # 检查Python版本
    print("\n1. Python版本检查:")
    if not check_python_version():
        all_ok = False
    
    # 检查Python包
    print("\n2. Python包检查:")
    packages = [
        ("yt-dlp", "yt_dlp"),
        ("openai-whisper", "whisper"),
        ("torch", "torch"),
        ("numpy", "numpy"),
        ("tqdm", "tqdm"),
        ("requests", "requests")
    ]
    
    for package_name, import_name in packages:
        if not check_package(package_name, import_name):
            all_ok = False
    
    # 检查外部命令
    print("\n3. 外部工具检查:")
    project_root = Path(__file__).parent
    ffmpeg_local = project_root / "tools" / "ffmpeg.exe"
    
    commands = [
        ("python", "Python", None),
        ("node", "Node.js", None),
        ("ffmpeg", "FFmpeg", [ffmpeg_local] if ffmpeg_local.exists() else None)
    ]
    
    for command, name, extra in commands:
        if not check_command(command, name, extra):
            all_ok = False
    
    # 检查项目文件
    print("\n4. 项目文件检查:")
    if not check_project_files():
        all_ok = False
    
    # 检查虚拟环境
    print("\n5. 虚拟环境检查:")
    venv_path = Path(__file__).parent / ".venv"
    if venv_path.exists():
        print("[OK] 虚拟环境目录存在")
    else:
        print("[FAIL] 虚拟环境目录不存在")
        all_ok = False
    
    # 总结
    print("\n" + "=" * 50)
    if all_ok:
        print("[OK] 所有检查通过! 项目环境已正确配置。")
        print("\n下一步:")
        print("1. 激活虚拟环境: .\\.venv\\Scripts\\Activate.ps1")
        print("2. 配置飞书信息: 编辑 feishu-base-config.json")
        print("3. 测试运行: python download_bili_following_latest.py --help")
    else:
        print("[FAIL] 部分检查未通过，请修复上述问题。")
        print("\n修复建议:")
        print("1. 安装缺失的Python包: pip install -r requirements.txt")
        print("2. 安装外部工具: ffmpeg, node.js")
        print("3. 确保项目文件完整")
    
    print("=" * 50)
    return all_ok


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)