# AI博主爬取 - 一键启动脚本
# 使用方法: powershell -ExecutionPolicy Bypass -File start.ps1 [命令]

param(
    [string]$Command = "help"
)

$ProjectRoot = $PSScriptRoot
$VenvActivate = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"
$ToolsPath = Join-Path $ProjectRoot "tools"

# 激活虚拟环境并设置 PATH
if (Test-Path $VenvActivate) {
    & $VenvActivate
    $env:PATH = "$ToolsPath;$env:PATH"
    Write-Host "[OK] Virtual environment activated" -ForegroundColor Green
} else {
    Write-Host "[ERROR] Virtual environment not found. Run: python -m venv .venv" -ForegroundColor Red
    exit 1
}

# 执行命令
switch ($Command) {
    "check" {
        python check_environment.py
    }
    "bili" {
        python download_bili_following_latest.py
    }
    "douyin" {
        python download_douyin_latest.py
    }
    "xiaohongshu" {
        python download_xiaohongshu_latest.py
    }
    "kuaishou" {
        python download_kuaishou_latest.py
    }
    "all" {
        python download_all_platform_latest.py --platform all
    }
    "postprocess" {
        python postprocess_bili_videos.py --model large-v3-turbo --device cuda
    }
    default {
        Write-Host "Usage: .\start.ps1 [check|bili|douyin|xiaohongshu|kuaishou|all|postprocess]"
    }
}