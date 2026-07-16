# MailDesk Lightweight v0.4.3

本版本将收件流程改为“邮件列表优先、正文按需加载”。

## 主要变化

- IMAP 使用批量 `BODY.PEEK[HEADER.FIELDS]` 获取邮件头，不再在同步列表时下载每封 `RFC822` 原文。
- Microsoft Graph 列表请求不再包含 `body`，也不会逐封请求附件。
- POP3 优先使用 `TOP 0` 获取邮件头；仅在服务器不支持 TOP 时回退完整邮件。
- 单击邮件列表项后，在后台加载该封正文、HTML、CID 图片和附件，界面不会卡住。
- SQLite 增加正文加载状态，邮件头刷新不会清空已经保存的正文、匹配结果或 EML 路径。
- 每账号取件数量默认改为 `0`，明确表示不限制；升级时会执行一次设置迁移。
- 账号邮件列表取消默认 500 封显示上限。

## 验证

- Ruff 静态检查通过。
- 完整测试：`347 passed, 3 skipped`。
- Windows onefile/onedir 启动探针。
- macOS arm64/x64 原生构建、启动探针和更新包验证。
- Chromium、QtWebEngine、QtQuick、QML、WebChannel 零残留检查。
