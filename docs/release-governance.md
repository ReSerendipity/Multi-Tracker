# 发布 / 回滚 规范（Multi-Tracker 本仓版）

> **来源与权威**：公共条款见 `ReSerendipity/.github` 的 `REPOSITORY_GUIDELINES.md` §10（发布 / 分发统一规范）；结构照 `RELEASE_GOVERNANCE_TEMPLATE.md`。
> 本文件只写**本仓特有**内容，不重写、不抵触 §10 公共条款。
> 事实采集日期：2026-10-18，全部以 `gh api` 现场核实（不假设）。

---

## 0. 远端优先（根原则，不可改写）

发布链的构建、打包、扫描、上传、推送**全部在 GitHub Actions 远端完成**；本地只做三件事：改版本位、落 CHANGELOG、`git tag` + `git push`。**本地不执行打包 / 镜像构建 / 发布上传。**

本仓落地情况：`release.yml` 的发布动作全部在远端 runner（`ubuntu-latest`）内以 `gh release` 完成，本地无任何交付物产出。本仓无容器镜像链，故不涉及镜像构建。

## 1. 版本号规范

- 遵循 **SemVer** `MAJOR.MINOR.PATCH`；预发布用 `-alpha.N` / `-beta.N` / `-rc.N`。
- **唯一权威版本位**：`待定（负责人 + 触发条件）`。实测本仓**当前不存在任何仓内版本声明**：
  - `pyproject.toml`、`setup.py`、`VERSION`、`version.txt` 均不存在（`gh api` 返回 404）；
  - `package.json` 仅有 `dependencies.playwright`，**无 `version` 字段**；
  - `package-lock.json` 根仅含 `lockfileVersion` 与依赖，**无版本号**。
  - 结论：本仓尚无版本位可选。一旦引入版本声明，须在此处回填「文件 + 字段 + 当前值」，并保持 §1 其余条目一致。
- 必须同步的其它版本位：`无`（当前无任何版本位）。
- 版本位漂移校验入口：`待定（负责人 + 触发条件）`——本仓 `tests/` 下仅 `conftest.py`、`test_transcript_content_flow.py`、`test_video_metric_snapshot_flow.py`，**无版本一致性测试**。
- 自动化方式：**手动 tag（人工）**。本仓无 release-please，`.github/workflows/` 仅 `ci.yml` 与 `release.yml` 两个文件。

## 2. CHANGELOG 管理

- 遵循 **Keep a Changelog**：`Added / Changed / Fixed / Deprecated / Removed / Security`。
- 每次合并 `main` 在 `[Unreleased]` 追加；type 映射 `feat→Added`、`fix→Fixed`、`refactor→Changed`；发版时 `[Unreleased]` → `[VERSION] - YYYY-MM-DD`。
- **本仓现状（2026-10-18 更新）**：根级 `CHANGELOG.md` **已建立**（此前 `gh api` 返回 404，本轮补建）。当前仅保留 `[Unreleased]` 段——本仓尚无版本位 / tag（见 §1），条目按 Keep a Changelog 归类并逐一回溯到 commit。
  - `release.yml` 仍以 `--generate-notes` 自动生成发行说明（见 §3）；CHANGELOG 与发行说明并行，互不替代。

## 3. 发布流程（远端）

1. 确认变更已合入 `main`。
2. 落/更新根级 `CHANGELOG.md` 的 `[Unreleased]` 条目（见 §2）。
3. 同步版本位（见 §1；当前无版本位，为「待定」）。
4. 本地打 tag 并推送：`git tag v<X.Y.Z>` → `git push origin v<X.Y.Z>`。
5. 远端凭 tag 触发 **`.github/workflows/release.yml`**：触发条件 `on: push: tags: ["v*"]`（即推送以 `v` 开头的 tag 时触发）。
6. 远端 job `release`（`Publish GitHub Release`）执行：
   `gh release create "$GITHUB_REF_NAME" --generate-notes --verify-tag`
   —— 直接以 tag 名建 **published Release**，发行说明由 GitHub 自动生成（`--generate-notes`），`--verify-tag` 要求 tag 已存在（与 §3 流程一致）。
7. 盯到终态：`gh run list` 确认绿；红了当场修或 revert 止损。

**发现（如实记录）**：本仓 `release.yml` 是**直接公开** Release（`gh release create` 不带 `--draft`），**没有「先 draft → 人工审核后 published」环节**，与 §10.2 规定的发布链存在差异。是否改造为 draft 流程：`待定（负责人 + 触发条件）`。本单不改 workflow。

## 4. 分发产物与完整性

| 产物 | 构建位置 | 标签 / 命名 | 完整性手段 |
|---|---|---|---|
| 无（本仓当前不构建任何可分发产物） | —— | Release 名 = tag 名（如 `v1.0.0`） | —— |

- **本仓现状（实测）**：`release.yml` 只调 `gh release create`，**不上传任何资产**；无 wheel / sdist / 容器镜像 / APK / 安装包等产物。本仓是脚本型 Python 工具（根目录大量 `*.py` 脚本 + `requirements.txt` + `分享包_多平台博主追踪系统/`），无打包链。
  - 是否引入可分发产物（如 wheel / 独立打包 bundle）：`待定（负责人 + 触发条件）`。若引入，须按 §10.3 + 本表回填「构建位置 / 命名规则 / 完整性手段」，且**不得以 floating `latest` 作发布基线**。
- **容器镜像**：本仓无镜像链 —— 无 `value=latest`、无 Trivy、无 `ghcr.io` 推送、无 `provenance` / `sbom`（`.github/workflows/` 两个文件内均无相关配置）。
- **完整性**：无 `SHA256SUMS.txt`；无 Tauri ed25519 `*.sig`（本仓非桌面壳仓，无 Tauri / NSIS / APK 链）。
- **不使用 GPG 分离签名**（§10.1 / §10.3 裁决）。本仓**从未存在** `gpg-signed-release.yml`（`gh api` 返回 404），无「待删」欠账。

## 5. 回滚

- **判定**：`待定（负责人 + 触发条件）`。本仓无监控 / 运行手册阈值可依，不编造数值。
- **执行**：以 `git revert <bad-commit>` 为主（保历史、可再 forward）；确需回退版本时，重新推送上一版 tag 触发 `release.yml`。
- **破坏性动作**：重指向 / 删除 tag、移动任何远端 ref → **须仓库所有者单独授权**。**注意**：本仓 `release.yml` 由 `push: tags: v*` 触发，移动已发布 tag 会当场重跑发布链并产生新 Release（§10.2 已警示的混年代资产风险）。
- **回滚后验证**：`待定（负责人 + 触发条件）`——本仓暂无健康端点 / smoke 命令。

## 6. SLA / 错误预算

- 目标可用性与错误预算：`待定（负责人 + 触发条件）`。本仓为本地运行的工具仓，无对外服务可用性指标可依，不套用固定数值。

## 7. 发布前检查清单

- [ ] 版本位全部同步（本仓当前无版本位，见 §1；若已引入则须逐项核对）
- [ ] 根级 `CHANGELOG.md` 的 `[Unreleased]` 已更新（本仓尚无版本位，暂不落 `[VERSION] - YYYY-MM-DD`，见 §2）
- [ ] `ci.yml` 两项检查通过：`Python syntax integrity`（非探针 `*.py` 可编译）+ `Pytest`（`python -m pytest tests/ -q`）
- [ ] 本地打 tag 并推送 `v<X.Y.Z>`，确认远端 `release.yml` 跑绿
- [ ] **本地未产出任何发布交付物**（全部远端构建）
- [ ] 未使用 GPG 分离签名；未保留 / 新建 GPG 流程

## 8. 本仓现状与欠账（对账 §10.6）

| 项 | 本仓实测现状 | 待收敛方向 |
|---|---|---|
| 发布总纲 | 本文件（`docs/release-governance.md`）为首次落地的本仓版 | 已按 §10 收敛，无其它发布文档需合并 |
| CHANGELOG | **已建立**（根级 `CHANGELOG.md`，仅 `[Unreleased]`，条目可回溯 commit） | 每次合并 `main` 在 `[Unreleased]` 追加（§10.2） |
| 版本位 | **不存在任何版本声明** | 引入后回填 §1 |
| 发布链触发 | `release.yml`，`push: tags: ["v*"]` | 符合 tag 驱动 |
| 发布产物 | 无资产，直接 published Release，`--generate-notes` | 是否改 draft 流程待定 |
| 镜像 `latest` | 不涉及（无镜像链） | —— |
| 镜像扫描 | 不涉及（无镜像链） | —— |
| SBOM / provenance | 不涉及（无镜像链） | —— |
| GPG 分离签名 | **本仓从未有** `gpg-signed-release.yml`（404） | 无需删除，符合 §10 裁决 |

---

## 禁止事项（沿用 §10 与模板，本仓不得违反）

- 不得重写 §10 公共条款（远端优先、tag 驱动、版本位一致、不可变标签、扫描阻断、无 GPG）。
- 不得引入 `latest` 作发布基线；不得保留或新建 GPG 签名流程。
- 不得留空占位符，不得编造阈值。
