# MailDesk v0.3.4

本版本改善代理配置、更新入口和通用 IMAP 收件性能。Windows 与 macOS 继续使用同一正式版本；macOS 安装包需要由 GitHub Actions 的原生 macOS Runner 构建。

## 主要变化

- 设置 → 网络代理新增“添加单个代理”，支持命名、HTTP/SOCKS5、主机、端口、认证信息和默认代理。
- 代理密码继续使用设备本地密钥加密保存；默认代理在全局代理池中优先使用。
- 设置新增“系统更新”页面，可手动检查最新正式版，无需登录 GitHub。
- 通用 IMAP 从每封邮件一次 `UID FETCH` 改为每批最多 25 封，60 封邮件通常由约 60 次下载往返降为 3 次。
- 对不返回标准 UID 元数据或不支持批量 FETCH 的邮箱服务端保留逐封回退。
- 数据库架构升级到版本 6，旧数据库会自动增加代理名称和默认代理字段。

## 下载选择

- Windows 日常使用：`MailDesk-v0.3.4-windows-x64-onedir.zip`
- Windows 单文件：`MailDesk-v0.3.4-windows-x64-onefile.zip`
- Apple Silicon Mac：`MailDesk-v0.3.4-macos-arm64.dmg`
- Intel Mac：`MailDesk-v0.3.4-macos-x64.dmg`

自动更新仅接受带有效 Ed25519 签名且 SHA-256、版本、平台、架构和文件大小都与清单一致的正式 Release 资产。
