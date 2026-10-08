# 贡献指南

本仓是多平台视频采集 / 转写 / 发布流水线（Python 为主，Playwright 走 npm 依赖）。
下面这些命令与约定**都取自仓库现状**（`requirements.txt`、`package.json`、`.github/workflows/ci.yml`、`.env.example`），不是理想化描述。

## 环境

- Python **3.11**（CI 用的就是这个版本，本地对齐可避免"本地绿、CI 红"）
- `pip install -r requirements.txt`（yt-dlp / openai-whisper / torch / numpy / tqdm / requests）
- 需要浏览器自动化时：`npm install`（只装 `playwright`），再 `npx playwright install`
- 转写默认走本地 Whisper：设备与模型由 `.env` 的 `WHISPER_DEVICE` / `WHISPER_MODEL` 决定

## 配置

```
cp .env.example .env
```

`.env` 不入库。可配置项见 `.env.example`，含 `DOUYIN_CDP_BRIDGE_PORT`、`XIAOHONGSHU_CDP_BRIDGE_PORT`、
`CHROME_CDP_PORT`、`WHISPER_DEVICE`、`WHISPER_MODEL`。

## 提交前自测（与 CI 同口径）

```
python -m pytest tests/ -q
```

CI 还有一个"语法完整性"检查，规则是：**跳过文件名以 `_` 开头的脚本**。
本仓根目录的 `_*.py` 是开发期一次性探针/修补脚本，不属于运行路径，因此不参与编译检查；
新增正式模块时**不要**用 `_` 前缀命名，否则它会静默绕过这道检查。

复现该检查（与 `ci.yml` 内联脚本同逻辑）：

```
python - <<'PY'
import pathlib, sys
bad = []
for p in sorted(pathlib.Path('.').rglob('*.py')):
    if p.name.startswith('_') or '.git' in p.parts:
        continue
    try:
        compile(p.read_text(encoding='utf-8'), str(p), 'exec')
    except SyntaxError as e:
        bad.append(f'{p}: line {e.lineno}: {e.msg}')
print("\n".join(bad) or "syntax OK")
sys.exit(1 if bad else 0)
PY
```

## CI 会做什么

`.github/workflows/ci.yml` 在 push 到 `main` 与每个 pull request 上跑两个 job：
`Python syntax integrity (main modules; _* dev probes excluded)` 和 `Pytest`。
`.github/workflows/release.yml` 只在打 `v*` tag 时跑，日常提交不会触发发布。

## Pull Request 要求

- 说清动机与影响面（涉及哪个平台的采集/转写/发布环节）
- 说明如何验证：贴 `pytest` 输出，或描述对哪条流水线跑过实采
- **不要**提交 `.env`、`downloads/` 产物、飞书凭据、以及任何真实账号标识
- 改动若触及 `_*.py` 探针，请在描述里说明它是一次性脚本还是要转正的模块
