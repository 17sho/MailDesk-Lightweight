# MailDesk v0.3.5

本版本增加可记忆的关闭窗口选择，并缩减 Windows 安装包体积，同时保留完整的 HTML 邮件、内嵌图片和远程图片阅读能力。

## 主要变化

- 首次点击主窗口关闭按钮时，可以选择“最小化到托盘”或“退出应用”。
- 支持“记住我的选择，不再询问”；也可以在设置 → 工作台中随时改回“每次询问”。
- 没有可用系统托盘时直接正常退出，不显示无法执行的托盘选项。
- Windows 构建移除未使用的 Qt 3D、PDF、Multimedia、虚拟键盘、QML 调试器和多余翻译资源。
- 保留 QtWebEngine 及其真实依赖，邮件 HTML、附件、内嵌图片和远程图片功能不降级。
- 裁剪后的 Windows onedir 解压体积较 v0.3.4 降低约 19.6%。

## 下载选择

- Windows 日常使用：`MailDesk-v0.3.5-windows-x64-onedir.zip`
- Windows 单文件：`MailDesk-v0.3.5-windows-x64-onefile.zip`
- Apple Silicon Mac：`MailDesk-v0.3.5-macos-arm64.dmg`
- Intel Mac：`MailDesk-v0.3.5-macos-x64.dmg`

所有自动更新包继续使用 Ed25519 签名清单和 SHA-256 双重校验。
