from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from mailbox_manager.config import AppPaths
from mailbox_manager.gui.main_window import MainWindow
from mailbox_manager.gui.modern_style import install_modern_style
from mailbox_manager.observability.logging_config import configure_logging
from mailbox_manager.services.audit_report import AuditReportService
from mailbox_manager.services.automation_service import AutomationService
from mailbox_manager.services.client_factory import ProtocolClientFactory
from mailbox_manager.services.eml_store import EmlStore
from mailbox_manager.services.fetch_service import FetchService
from mailbox_manager.services.send_service import SendService
from mailbox_manager.services.throttle import ComplianceThrottle
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.enterprise_repositories import (
    AuditRepository,
    AutomationRuleRepository,
    GroupRepository,
    ProxyRepository,
    ScheduleRepository,
    SettingsRepository,
    StatisticsRepository,
    TagRepository,
    WebhookRepository,
)
from mailbox_manager.storage.repositories import AccountRepository, MessageRepository

_TRANSLATORS: list[QTranslator] = []


def create_main_window(paths: AppPaths | None = None) -> MainWindow:
    paths = paths or AppPaths.for_current_user()
    paths.ensure()
    database = Database(paths.database)
    database.initialize()
    cipher = CredentialCipher.load_or_create(paths.key_file)
    accounts = AccountRepository(database, cipher)
    messages = MessageRepository(database)
    settings = SettingsRepository(database)
    throttle_values = settings.get("enterprise_ui", {})
    throttle_values = throttle_values if isinstance(throttle_values, dict) else {}
    throttle = ComplianceThrottle(
        max_concurrency_per_identity=int(throttle_values.get("ip_concurrency", 2)),
        min_account_interval=float(throttle_values.get("login_interval_min", 0)),
        max_account_interval=float(throttle_values.get("login_interval_max", 0)),
    )
    eml_store = EmlStore(paths.eml)
    audits = AuditRepository(database)
    proxies = ProxyRepository(database, cipher)
    rules = AutomationRuleRepository(database)
    webhooks = WebhookRepository(database, cipher)
    automation = AutomationService(rules, webhooks, settings, audits)
    fetch_service = FetchService(
        accounts,
        messages,
        client_factory=ProtocolClientFactory(proxies, settings),
        eml_store=eml_store,
        audit_repository=audits,
        throttle=throttle,
        automation=automation,
    )
    return MainWindow(
        accounts,
        messages,
        fetch_service,
        groups=GroupRepository(database),
        tags=TagRepository(database),
        proxies=proxies,
        schedules=ScheduleRepository(database),
        settings=settings,
        webhooks=webhooks,
        rules=rules,
        statistics=StatisticsRepository(database),
        audit_reports=AuditReportService(audits, paths.logs),
        eml_store=eml_store,
        send_service=SendService(audit_repository=audits),
    )


def configure_ui_font(application: QApplication) -> None:
    windows_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for filename in ("msyh.ttc", "msyhbd.ttc"):
        font_path = windows_fonts / filename
        if not font_path.exists():
            continue
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                application.setFont(QFont(families[0], 9))
                return
    application.setFont(QFont("Microsoft YaHei UI", 9))


def configure_translations(application: QApplication) -> bool:
    translator = QTranslator(application)
    translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    loaded = translator.load(QLocale("zh_CN"), "qtbase", "_", translations_path)
    if not loaded:
        loaded = translator.load(str(Path(translations_path) / "qtbase_zh_CN.qm"))
    if loaded:
        application.installTranslator(translator)
        _TRANSLATORS.append(translator)
    return loaded


def run() -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("MailDesk")
    application.setOrganizationName("MailDesk")
    install_modern_style(application)
    configure_translations(application)
    configure_ui_font(application)
    icon_path = Path(__file__).parent / "assets" / "app.svg"
    if icon_path.exists():
        application.setWindowIcon(QIcon(str(icon_path)))
    paths = AppPaths.for_current_user()
    logger = configure_logging(paths.logs)
    try:
        window = create_main_window(paths)
    except Exception:
        logger.exception("应用初始化失败")
        QMessageBox.critical(None, "MailDesk 启动失败", "无法初始化安全存储，请查看本地日志。")
        return 1
    logger.info("MailDesk started")
    if QSystemTrayIcon.isSystemTrayAvailable():
        application.setQuitOnLastWindowClosed(False)
        tray = QSystemTrayIcon(application.windowIcon(), application)
        tray.setToolTip("MailDesk · 邮箱工作台")
        tray_menu = QMenu()
        show_action = tray_menu.addAction("显示主窗口")
        quit_action = tray_menu.addAction("退出")
        show_action.triggered.connect(window.restore_from_tray)
        quit_action.triggered.connect(window.request_quit)
        tray.activated.connect(
            lambda reason: window.restore_from_tray()
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick
            else None
        )
        tray.setContextMenu(tray_menu)
        window.enable_tray(tray)
        tray.show()
    window.show()
    code = application.exec()
    logging.shutdown()
    return code
