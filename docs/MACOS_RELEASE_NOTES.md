## MailDesk macOS Preview

这是 MailDesk 首个公开的 macOS 预览版本，由 GitHub 官方 macOS Runner 原生构建。

### 提供的架构

- Apple Silicon `arm64`：M1、M2、M3、M4、M5 等芯片。
- Intel `x64`：Intel Mac。

每种架构同时提供 DMG 和 ZIP。普通用户推荐下载 DMG。

### 安全存储

随机 Fernet 主密钥保存到当前 macOS 用户的系统钥匙串；本地标记文件不保存明文主密钥。邮箱密码、应用专用密码、Refresh Token 与 TOTP 密钥仍以字段级密文写入 SQLite。

### 重要说明

本预览版尚未使用 Apple Developer ID 证书，也未完成 Apple 公证。首次打开时请在 Finder 中 Control-点击应用并选择“打开”，或在“系统设置 → 隐私与安全性”中确认“仍要打开”。请先使用 `SHA256SUMS-macos.txt` 核对文件。

macOS 版目前采用手动更新，不执行 Windows PowerShell 自动替换流程。详细说明见仓库中的 `docs/MACOS.md`。
