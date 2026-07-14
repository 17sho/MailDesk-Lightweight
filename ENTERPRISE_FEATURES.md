# MailDesk v0.2 企业功能矩阵

## 已实现

| 功能 | 状态 | 说明 |
|---|---|---|
| TXT / CSV / JSON / 拖放导入 | 已实现 | 文件大小、行数、编码和字段边界校验 |
| 任意文本智能粘贴 | 已实现 | 识别邮箱、相邻授权码、OAuth Client ID/Refresh Token、代理提示 |
| 导入预览、去重、状态分类 | 已实现 | 用户确认后才写入 SQLite |
| 安全导出 | 已实现 | 账号状态 CSV/TXT、邮件结果 CSV、单封 EML；不导出正文凭据 |
| DPAPI + Fernet | 已实现 | 主密钥绑定当前 Windows 用户，敏感字段为密文 |
| IMAP / POP3 | 已实现 | SSL、STARTTLS、超时、统一错误分类 |
| SMTP | 已实现 | 只向用户确认拥有的目标发送 UUID 自检；显式规则转发 EML |
| Outlook Graph | 已实现 | Refresh Token 换 Access Token、有界分页、邮件动作 |
| OAuth2 IMAP | 已实现 | Microsoft 与 Google Refresh Token、XOAUTH2 |
| 常见服务商自动补全 | 已实现 | QQ、163、126、Yeah、88、新浪、Gmail、Outlook、Foxmail |
| 自定义域名探测 | 已实现 | 显式启动，最多尝试 imap/mail × 993/143，成功后保存 |
| 并发取件 | 已实现 | QThreadPool 1–50、协作停止、单身份并发上限、账号间隔 |
| 固定代理 | 已实现 | HTTP/SOCKS5 批量导入、加密密码、账号 1v1 绑定、Graph/IMAP/POP3 |
| 跨文件夹扫描 | 已实现 | 自动识别 Junk/Spam/Trash flag 和常见多语言名称 |
| MIME/验证码/Catch-All | 已实现 | multipart、HTML、字符集、正则、To/X-Original-To |
| EML 原件 | 已实现 | 账号隔离、哈希文件名、原子保存、右键导出 |
| 邮件后处理 | 已实现 | 匹配后已读/移动/删除；必须勾选用户确认 |
| Webhook | 已实现 | HTTPS、主机允许列表、私网阻断、禁止重定向、HMAC 签名 |
| 定时任务与托盘 | 已实现 | 按组周期、托盘驻留、新邮件通知 |
| TOTP | 已实现 | 加密保存、右键复制、30 秒自动清空剪贴板 |
| 自动转发 | 已实现 | 规则匹配后通过当前账号 SMTP 转发 EML，必须显式确认 |
| 分组与标签 | 已实现 | 多层树、增删改、账号分配、标签过滤基础和状态着色 |
| 数据大屏 | 已实现 | 账号健康度饼图与按小时收件折线图 |
| 审计报告 | 已实现 | 脱敏 audit.csv、diagnostics.json、app.log 打包 ZIP |
| Outlook 安全检查 | 已实现 | 只读列出转发、重定向、删除规则，不自动修改 |
| PyInstaller | 已实现 | onefile / onedir、图标、Qt/cryptography/pywin32 依赖 |

## 安全替代

| 原始需求 | 安全替代 |
|---|---|
| 代理轮换规避风控 | 固定代理绑定、单身份并发限制、正常登录间隔、尊重服务商限流 |
| 批量改密/恢复邮箱 | 不执行；提供官方设置入口与只读安全审计 |
| 自动删除转发规则 | 不执行；只读报告规则，由用户在官方页面确认处理 |
| 隐式 Headless 登录/DOM 抓信 | 不执行；打开可见的官方邮箱页面，登录与设置由用户控制 |

## 不实现

- 绕过验证码、封禁、Rate Limit 或服务商安全策略。
- 未授权账号的批量凭据验证、接管或安全设置修改。
- 隐藏浏览器自动化、规避检测或自动开启服务商关闭的协议。
- 自动轮换身份/IP 来掩盖批量登录来源。

