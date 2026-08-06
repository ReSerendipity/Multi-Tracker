# 贡献指南

感谢你关注本项目！欢迎以各种方式参与贡献。

## 如何贡献

### 报告问题

如果你发现了 bug 或有功能建议，欢迎通过 [GitHub Issues](https://github.com/你的用户名/仓库名/issues) 提交问题。报告时请尽量包含：

- 操作系统和版本
- Python / Node.js 版本
- 重现步骤
- 期望行为 vs 实际行为
- 相关错误信息或截图

### 提交代码

1. **Fork** 本仓库
2. 创建你的功能分支：`git checkout -b feature/your-feature-name`
3. 完成开发并确保代码能正常运行
4. 提交更改：`git commit -m "feat: 简明描述改动内容"`
5. 推送到你的分支：`git push origin feature/your-feature-name`
6. 向本仓库发起 **Pull Request**

### 提交信息规范

推荐使用以下前缀：

- `feat:` — 新增功能
- `fix:` — 修复 bug
- `docs:` — 文档改动
- `refactor:` — 代码重构（非功能变动）
- `chore:` — 构建流程或辅助工具变动

### 代码风格

- Python 代码遵循 [PEP 8](https://peps.python.org/pep-0008/) 规范
- Node.js / JavaScript 使用现代 ES Module 语法（`.mjs`）
- 尽可能添加注释说明复杂逻辑
- 变量和函数命名使用英文，注释可用中文

## 开发环境设置

```powershell
# 克隆仓库后进入项目目录
cd sharing-package-multi-platform-tracker

# Python 环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Node.js 依赖
npm install

# 环境检查
python check_environment.py
```

## 行为准则

参与本项目即表示你同意：

- 尊重每一位贡献者和用户
- 保持友善和专业的讨论氛围
- 不发布违法违规或侵犯他人权利的内容
- 遵守各平台的服务条款

## 许可证说明

本项目基于 [Apache License 2.0](./LICENSE.md) 开源。提交贡献即表示你同意你的贡献将以相同许可证发布。

---

如有其他问题，欢迎通过 Issues 或 Discussions 交流。
