# MailDesk v0.1 Tasks

## Task 1: 工程骨架与领域契约

**Acceptance criteria:**
- [x] `src/mailbox_manager` 可导入并提供领域 dataclass/enum。
- [x] `EmailClientBase` 输入输出和错误语义统一。

**Verification:** `py -3.12 -m pytest -q tests/unit/test_domain.py`

**Dependencies:** None

**Files:** `pyproject.toml`, `src/mailbox_manager/domain/*`, `src/mailbox_manager/protocols/base.py`, `tests/unit/test_domain.py`

## Task 2: 加密存储

**Acceptance criteria:**
- [x] Windows 使用 DPAPI 保护 Fernet 主密钥。
- [x] SQLite 仅保存密文，账号 CRUD/去重可用。
- [x] groups/tags/messages/audit 的 schema 可迁移创建。

**Verification:** `py -3.12 -m pytest -q tests/integration/test_repository.py tests/unit/test_crypto.py`

**Dependencies:** Task 1

**Files:** `storage/crypto.py`, `storage/database.py`, `storage/repositories.py`, related tests

## Task 3: 导入与导出

**Acceptance criteria:**
- [x] TXT/CSV/JSON 和粘贴文本解析为预览行。
- [x] 常见 provider 自动补全，歧义/非法行可读。
- [x] CSV/TXT 导出排除秘密并转义公式。

**Verification:** `py -3.12 -m pytest -q tests/unit/test_importers.py tests/unit/test_export.py`

**Dependencies:** Tasks 1–2

**Files:** `importers/*`, `protocols/providers.py`, `services/export_service.py`, related tests

## Task 4: 邮件解析

**Acceptance criteria:**
- [x] multipart/charset 正文安全解析。
- [x] 提取 4–8 位验证码、关键词和 Catch-All 收件人。
- [x] 邮件大小与正文长度有上限。

**Verification:** `py -3.12 -m pytest -q tests/unit/test_mail_parser.py`

**Dependencies:** Task 1

**Files:** `mail/parser.py`, related tests

## Task 5: IMAP 与 Graph

**Acceptance criteria:**
- [x] IMAP 支持 SSL/STARTTLS、密码和 XOAUTH2。
- [x] Graph 使用 Refresh Token 获取 token 并有界分页拉取。
- [x] 主要网络/鉴权/限流错误映射为统一状态。

**Verification:** `py -3.12 -m pytest -q tests/unit/test_protocols.py`

**Dependencies:** Tasks 1, 4

**Files:** `protocols/imap_client.py`, `protocols/outlook_graph.py`, related tests

## Task 6: 服务编排与日志

**Acceptance criteria:**
- [x] FetchService 选择协议、存储结果、更新状态。
- [x] 日志自动掩码邮箱/Token/密码样式。

**Verification:** `py -3.12 -m pytest -q tests/unit/test_fetch_service.py tests/unit/test_logging.py`

**Dependencies:** Tasks 2, 4, 5

**Files:** `services/*`, `observability/logging_config.py`, related tests

## Task 7: PySide6 主界面

**Acceptance criteria:**
- [x] 账号表、分组树、邮件/正文/日志区和工具栏可创建。
- [x] 导入预览确认后写库，导出可选择路径。

**Verification:** `QT_QPA_PLATFORM=offscreen py -3.12 -m pytest -q tests/gui`

**Dependencies:** Tasks 2, 3, 6

**Files:** `gui/account_model.py`, `gui/import_dialog.py`, `gui/main_window.py`, related tests

## Task 8: 并发 worker

**Acceptance criteria:**
- [x] 并发限制 1–50，每账号任务发出状态和结果信号。
- [x] 停止为协作取消，不阻塞 GUI。

**Verification:** `QT_QPA_PLATFORM=offscreen py -3.12 -m pytest -q tests/gui/test_workers.py`

**Dependencies:** Tasks 6–7

**Files:** `gui/workers.py`, `gui/main_window.py`, related tests

## Task 9: 主题与安全扩展入口

**Acceptance criteria:**
- [x] 明暗主题可切换且状态不只靠颜色。
- [x] 托盘和 TOTP 仅在用户显式操作时启用；秘密不进入剪贴板日志。

**Verification:** GUI offscreen tests + manual keyboard check

**Dependencies:** Tasks 7–8

**Files:** `gui/theme.py`, `gui/main_window.py`, `services/totp_service.py`, related tests

## Task 10: 打包

**Acceptance criteria:**
- [x] `build.py --mode onefile|onedir` 参数有效。
- [x] spec 收集 PySide6/cryptography/pywin32 所需资源。

**Verification:** `py -3.12 build.py --mode onedir --clean`

**Dependencies:** Tasks 1–9

**Files:** `build.py`, `mailbox-manager.spec`, `requirements*.txt`, `assets/app.ico`

## Task 11: 文档与发布验证

**Acceptance criteria:**
- [x] README 给出安装、运行、导入格式、Graph 配置、打包和安全限制。
- [x] 全量测试与 lint 通过，任务状态与实际一致。

**Verification:** full test/lint/build commands in `tasks/plan.md`

**Dependencies:** Tasks 1–10

**Files:** `README.md`, `tasks/*`, example data
