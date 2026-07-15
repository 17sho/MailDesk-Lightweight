# MailDesk macOS 版

MailDesk macOS 版由 GitHub 的真实 macOS Runner 构建，分别提供 Apple Silicon 与 Intel 包。它不是在 Windows 上交叉编译或简单改名得到的文件。

## 下载选择

- `arm64`：Apple Silicon，适用于 M1、M2、M3、M4、M5 等芯片。
- `x64`：Intel Mac。
- `.dmg`：推荐普通用户使用，打开后把 `MailDesk.app` 拖到“应用程序”。
- `.zip`：适合便携存放或手动部署。

最低目标系统为 macOS 13。首次启动前请使用 Release 中的 `SHA256SUMS-macos.txt` 核对下载文件。

## 首次打开与 Gatekeeper

当前项目没有 Apple Developer ID 证书，因此应用未进行 Apple 公证。macOS 可能提示“无法验证开发者”。这不代表 SHA-256 或 GitHub Release 签名失效，但系统无法确认商业开发者身份。

推荐操作：

1. 只从项目官方 GitHub Release 下载并核对 SHA-256。
2. 将 `MailDesk.app` 移到“应用程序”。
3. 在 Finder 中按住 Control 点击 MailDesk，选择“打开”，再确认一次“打开”。
4. 如果仍被阻止，进入“系统设置 → 隐私与安全性”，在安全提示下选择“仍要打开”。

不要从不明网盘、群文件或二次打包站下载。项目不会要求关闭系统完整性保护。

## 数据与凭据

- 数据目录：`~/Library/Application Support/MailDesk`
- 数据库：`maildesk.db`
- 日志：`logs/`
- 原始邮件：`eml/`
- 随机 Fernet 主密钥存放在当前 macOS 用户的“钥匙串”中。
- 数据目录中的 `master.key.keychain` 只是钥匙串项目标记，不包含明文主密钥。

首次访问钥匙串时，macOS 可能请求当前用户确认。删除 MailDesk 的钥匙串项目后，已有加密凭据将无法恢复。

## 功能与限制

IMAP、POP3、SMTP、Microsoft Graph、OAuth2、邮件阅读器、附件、翻译、搜索、导入导出、分组、代理和批量任务使用与 Windows 版相同的核心代码。

当前 macOS 预览版不执行 Windows PowerShell 自动替换流程。应用内检查更新只用于提示新版本；macOS 更新需要从 Release 手动下载并替换 `MailDesk.app`。系统托盘在 macOS 中显示为菜单栏图标。

## 从源码构建

必须在真实 macOS 上构建：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python build_macos.py --clean
```

输出位置为 `dist/MailDesk.app`。构建脚本会生成 ICNS 图标，并由 PyInstaller 创建原生 `.app` 目录。
