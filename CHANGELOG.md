# Changelog

本文件记录 Multi-Tracker 所有值得记录的变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循[语义化版本（SemVer）](https://semver.org/lang/zh-CN/)。

> **本仓现状（2026-10-18 实测）**：本仓**尚未建立版本化发布与版本位** —— 无 tag、无 Release（`gh api` 实测 tags 与 releases 均为 0 条），亦无任何仓内版本声明（`pyproject.toml` / `setup.py` / `VERSION` / `version.txt` 均不存在，`package.json` 无 `version` 字段）。
> 因此本文件当前**只保留 `[Unreleased]`**；待建立版本位并完成首次发版后，再按 Keep a Changelog 将 `[Unreleased]` 归入 `[X.Y.Z] - YYYY-MM-DD`。
> 下列条目回填自本仓 commit 历史（仅收可溯源者），条目末括注提交短哈希，可据此复核。

## [Unreleased]

### Added

- 新增按 tag 触发的 GitHub Release 发布工作流（`.github/workflows/release.yml`）。(`eef9998d`)
- 新增 Python 语法完整性检查（排除 `_` 探针脚本）与 pytest 门禁 CI（`.github/workflows/ci.yml`）。(`6e1f5c8b`)
- 补全 Apache-2.0 许可证文件（`LICENSE`）。(`8dccbd4c`)
- 补齐协作资产与限流版 Dependabot 配置。(`96b23e41`)
- 补全根 README 缺失的依赖安装步骤与 License / 版权行。(`f0123e20`)
- 完成转写内容回写工作流。(`e9c294ce`)
- 新增本仓发布 / 回滚规范 `docs/release-governance.md`（对齐 `ReSerendipity/.github` 治理规范 §10）。(`1e0712c2`)

### Changed

- 停止跟踪 `.qoder/` AI 工具链产物，并将其收编进 `.gitignore`。(`c665d6ab`, `271bcdb0`)
- `.gitignore` 增加忽略 `node_modules` 的规则。(`e465c63f`)

### Fixed

- 修正文档中安装不上的 npm 包名（改用飞书官方 CLI，并补上遗漏的替换处）。(`b9312060`, `8861dd4d`)
- 对齐「分享包」的许可证与仓库许可证。(`20af1f43`)
- 修正两处与仓库实际不符的文档表述。(`436818db`)
