from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mailbox_manager.domain.models import EmailAccount, ProtocolType, SecurityMode
from mailbox_manager.gui.icons import line_icon
from mailbox_manager.importers.smart_parser import EMAIL_PATTERN
from mailbox_manager.protocols.providers import PROVIDERS, ProviderConfig


@dataclass(frozen=True, slots=True)
class ProviderOption:
    key: str
    title: str
    caption: str
    preset_domain: str = ""
    allowed_domains: tuple[str, ...] = ()


PROVIDER_OPTIONS = (
    ProviderOption(
        "microsoft",
        "Outlook / Microsoft 365",
        "使用 Microsoft Graph OAuth2，适合 Outlook、Hotmail、Live 和企业 Microsoft 365。",
    ),
    ProviderOption(
        "gmail",
        "Gmail / Google Workspace",
        "推荐使用 16 位应用专用密码，也支持已有的 OAuth2 Refresh Token。",
        "gmail.com",
    ),
    ProviderOption(
        "qq.com",
        "QQ 邮箱",
        "使用 QQ 邮箱客户端授权码，不要填写 QQ 登录密码。",
        "qq.com",
        ("qq.com",),
    ),
    ProviderOption(
        "foxmail.com",
        "Foxmail",
        "使用 Foxmail/QQ 邮箱授权码，通过腾讯邮箱服务器收取。",
        "foxmail.com",
        ("foxmail.com",),
    ),
    ProviderOption(
        "163.com",
        "163 邮箱",
        "需要在网易邮箱设置中开启客户端服务并生成授权码。",
        "163.com",
        ("163.com",),
    ),
    ProviderOption(
        "126.com",
        "126 邮箱",
        "需要在网易邮箱设置中开启客户端服务并生成授权码。",
        "126.com",
        ("126.com",),
    ),
    ProviderOption(
        "yeah.net",
        "Yeah.net 邮箱",
        "需要在网易邮箱设置中开启客户端服务并生成授权码。",
        "yeah.net",
        ("yeah.net",),
    ),
    ProviderOption(
        "sina.com",
        "新浪邮箱",
        "使用新浪邮箱授权码或服务商允许的客户端密码。",
        "sina.com",
        ("sina.com",),
    ),
    ProviderOption(
        "88.com",
        "88 邮箱",
        "使用邮箱服务商提供的授权码或客户端专用密码。",
        "88.com",
        ("88.com",),
    ),
    ProviderOption(
        "custom",
        "企业邮箱 / 自定义域名",
        "支持腾讯企业邮、阿里企业邮、自建邮箱及其他标准 IMAP/POP3 服务。",
    ),
)


class AddAccountDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("addAccountDialog")
        self.setWindowTitle("MailDesk · 添加邮箱")
        font_delta = max(0, self.font().pointSize() - 10)
        minimum_width = min(980, 760 + font_delta * 25)
        self.setMinimumSize(minimum_width, 560)
        available = self.screen().availableGeometry()
        self.resize(
            min(1040, max(minimum_width, available.width() - 100)),
            min(720, max(560, available.height() - 100)),
        )
        self._account: EmailAccount | None = None
        self._current_provider_key = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        shell = QFrame()
        shell.setObjectName("settingsShell")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(self._build_provider_sidebar())
        shell_layout.addWidget(self._build_form_area(), 1)
        root.addWidget(shell, 1)
        root.addWidget(self._build_footer())

        self.provider_list.currentRowChanged.connect(self._provider_changed)
        self.auth_mode.currentIndexChanged.connect(self._sync_auth_fields)
        self.protocol.currentIndexChanged.connect(self._sync_custom_protocol)
        self.email.textChanged.connect(self._update_server_placeholders)
        self.provider_list.setCurrentRow(0)

    @property
    def account(self) -> EmailAccount | None:
        return self._account

    @property
    def selected_provider_key(self) -> str:
        item = self.provider_list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item is not None else ""

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("settingsHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(26, 20, 26, 18)
        layout.setSpacing(13)
        mark = QLabel()
        mark.setObjectName("settingsHeaderIcon")
        mark.setFixedSize(42, 42)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setPixmap(line_icon("mail-plus", "#2563eb", 22).pixmap(22, 22))
        copy = QVBoxLayout()
        copy.setSpacing(2)
        title = QLabel("添加邮箱")
        title.setObjectName("settingsTitle")
        subtitle = QLabel("先选择邮箱服务商，再填写对应的授权信息")
        subtitle.setObjectName("settingsSubtitle")
        copy.addWidget(title)
        copy.addWidget(subtitle)
        layout.addWidget(mark)
        layout.addLayout(copy)
        layout.addStretch(1)
        return header

    def _build_provider_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("settingsSidebar")
        sidebar.setFixedWidth(260)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 18, 14, 16)
        layout.setSpacing(9)
        caption = QLabel("选择邮箱类型")
        caption.setObjectName("settingsNavCaption")
        layout.addWidget(caption)
        self.provider_list = QListWidget()
        self.provider_list.setObjectName("settingsNavigation")
        self.provider_list.setSpacing(2)
        self.provider_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.provider_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        for option in PROVIDER_OPTIONS:
            item = QListWidgetItem(
                line_icon(
                    "globe" if option.key == "custom" else "mail",
                    "#64748b",
                    16,
                ),
                option.title,
            )
            item.setData(Qt.ItemDataRole.UserRole, option.key)
            item.setToolTip(option.title)
            self.provider_list.addItem(item)
        layout.addWidget(self.provider_list, 1)
        hint = QLabel("密码、授权码和 Token\n将使用本机密钥加密保存")
        hint.setObjectName("settingsPrivacyHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return sidebar

    def _build_form_area(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page = QWidget()
        page.setObjectName("settingsPage")
        self.page_layout = QVBoxLayout(page)
        self.page_layout.setContentsMargins(26, 22, 26, 26)
        self.page_layout.setSpacing(15)

        self.page_title = QLabel()
        self.page_title.setObjectName("settingsPageTitle")
        self.page_caption = QLabel()
        self.page_caption.setObjectName("settingsPageCaption")
        self.page_caption.setWordWrap(True)
        self.page_layout.addWidget(self.page_title)
        self.page_layout.addWidget(self.page_caption)
        self._build_identity_card()
        self._build_oauth_card()
        self._build_server_card()
        self._build_provider_info()
        self.page_layout.addStretch(1)
        scroll.setWidget(page)
        return scroll

    def _new_card(self, title_text: str, caption_text: str = "") -> tuple[QFrame, QFormLayout]:
        card = QFrame()
        card.setObjectName("settingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(7)
        title = QLabel(title_text)
        title.setObjectName("settingsCardTitle")
        layout.addWidget(title)
        if caption_text:
            caption = QLabel(caption_text)
            caption.setObjectName("settingsCardCaption")
            caption.setWordWrap(True)
            layout.addWidget(caption)
        form = QFormLayout()
        form.setContentsMargins(0, 9, 0, 0)
        form.setHorizontalSpacing(28)
        form.setVerticalSpacing(13)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        layout.addLayout(form)
        self.page_layout.addWidget(card)
        return card, form

    @staticmethod
    def _row(form: QFormLayout, text: str, field: QWidget) -> QLabel:
        label = QLabel(text)
        label.setObjectName("settingsFieldLabel")
        form.addRow(label, field)
        return label

    @staticmethod
    def _line(placeholder: str = "") -> QLineEdit:
        editor = QLineEdit()
        editor.setClearButtonEnabled(True)
        editor.setPlaceholderText(placeholder)
        return editor

    def _build_identity_card(self) -> None:
        self.identity_card, form = self._new_card(
            "账号与登录方式",
            "请使用你本人拥有或获授权管理的邮箱账号。",
        )
        self.email = self._line("name@example.com")
        self.auth_mode = QComboBox()
        self.auth_mode.addItem("应用专用密码（推荐）", "app_password")
        self.auth_mode.addItem("OAuth2 Refresh Token", "oauth")
        self.secret = self._line()
        self.secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret.setPlaceholderText("输入授权码或应用专用密码")
        self.totp_secret = self._line("可选，仅用于本地生成 2FA 动态码")
        self.email_label = self._row(form, "邮箱地址", self.email)
        self.auth_mode_label = self._row(form, "登录方式", self.auth_mode)
        self.secret_label = self._row(form, "授权凭据", self.secret)
        self.totp_label = self._row(form, "TOTP 密钥", self.totp_secret)

    def _build_oauth_card(self) -> None:
        self.oauth_card, form = self._new_card(
            "OAuth2 授权",
            "只接收官方 OAuth2 Refresh Token；MailDesk 不会打开或模拟登录页面。",
        )
        self.client_id = self._line("00000000-0000-0000-0000-000000000000")
        self.refresh_token = QPlainTextEdit()
        self.refresh_token.setObjectName("credentialTextArea")
        self.refresh_token.setPlaceholderText("粘贴 Refresh Token")
        self.refresh_token.setMinimumHeight(94)
        self.refresh_token.setTabChangesFocus(True)
        self.tenant = self._line("common")
        self.tenant.setText("common")
        self._row(form, "Client ID", self.client_id)
        self._row(form, "Refresh Token", self.refresh_token)
        self.tenant_label = self._row(form, "Tenant", self.tenant)

    def _build_server_card(self) -> None:
        self.server_card, form = self._new_card(
            "收件服务器",
            "不知道服务器时可先留空，程序会使用 imap.域名 作为候选配置。",
        )
        self.protocol = QComboBox()
        self.protocol.addItem("IMAP（推荐）", ProtocolType.IMAP.value)
        self.protocol.addItem("POP3", ProtocolType.POP3.value)
        self.host = self._line("imap.example.com")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(993)
        self.security = QComboBox()
        self.security.addItem("SSL/TLS", SecurityMode.SSL.value)
        self.security.addItem("STARTTLS", SecurityMode.STARTTLS.value)
        self.security.addItem("无加密（不推荐）", SecurityMode.PLAIN.value)
        self.smtp_host = self._line("可选，例如 smtp.example.com")
        self.smtp_port = QSpinBox()
        self.smtp_port.setRange(0, 65535)
        self.smtp_port.setSpecialValueText("未配置")
        self.smtp_port.setValue(0)
        self.smtp_security = QComboBox()
        self.smtp_security.addItem("SSL/TLS", SecurityMode.SSL.value)
        self.smtp_security.addItem("STARTTLS", SecurityMode.STARTTLS.value)
        self.smtp_security.addItem("无加密（不推荐）", SecurityMode.PLAIN.value)
        self._row(form, "收件协议", self.protocol)
        self._row(form, "服务器", self.host)
        self._row(form, "端口", self.port)
        self._row(form, "连接加密", self.security)
        self._row(form, "SMTP 服务器", self.smtp_host)
        self._row(form, "SMTP 端口", self.smtp_port)
        self._row(form, "SMTP 加密", self.smtp_security)

    def _build_provider_info(self) -> None:
        self.provider_info = QFrame()
        self.provider_info.setObjectName("providerInfoCard")
        layout = QHBoxLayout(self.provider_info)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(10)
        icon = QLabel()
        icon.setObjectName("providerInfoIcon")
        icon.setFixedSize(30, 30)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(line_icon("info", "#2563eb", 16).pixmap(16, 16))
        self.provider_info_text = QLabel()
        self.provider_info_text.setObjectName("providerInfoText")
        self.provider_info_text.setWordWrap(True)
        layout.addWidget(icon)
        layout.addWidget(self.provider_info_text, 1)
        self.page_layout.addWidget(self.provider_info)

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("settingsFooter")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(24, 14, 24, 14)
        hint = QLabel("添加后可以立即取件，也可以继续批量导入其他账号")
        hint.setObjectName("settingsFooterHint")
        layout.addWidget(hint)
        layout.addStretch(1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        add_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        add_button.setText("添加邮箱")
        add_button.setObjectName("primaryButton")
        add_button.setDefault(True)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_button.setText("取消")
        cancel_button.setObjectName("secondaryButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        return footer

    def _provider_changed(self, row: int) -> None:
        if not 0 <= row < len(PROVIDER_OPTIONS):
            return
        option = PROVIDER_OPTIONS[row]
        if self._current_provider_key and option.key != self._current_provider_key:
            self.secret.clear()
            self.client_id.clear()
            self.refresh_token.clear()
            self.tenant.setText("common")
        self._current_provider_key = option.key
        self.page_title.setText(option.title)
        self.page_caption.setText(option.caption)
        is_microsoft = option.key == "microsoft"
        is_gmail = option.key == "gmail"
        is_custom = option.key == "custom"
        self.auth_mode_label.setVisible(is_gmail)
        self.auth_mode.setVisible(is_gmail)
        self.server_card.setVisible(is_custom)
        self.totp_label.setVisible(not is_microsoft)
        self.totp_secret.setVisible(not is_microsoft)
        if is_gmail:
            self.auth_mode.setCurrentIndex(0)
        self._sync_auth_fields()
        self._update_server_placeholders()
        self.email.setFocus()

    def _sync_auth_fields(self, _index: int | None = None) -> None:
        provider_key = self.selected_provider_key
        oauth = provider_key == "microsoft" or (
            provider_key == "gmail" and self.auth_mode.currentData() == "oauth"
        )
        self.oauth_card.setVisible(oauth)
        self.secret_label.setVisible(not oauth)
        self.secret.setVisible(not oauth)
        self.tenant_label.setVisible(provider_key == "microsoft")
        self.tenant.setVisible(provider_key == "microsoft")
        self.client_id.setPlaceholderText(
            "00000000-0000-0000-0000-000000000000"
            if provider_key == "microsoft"
            else "1234567890-example.apps.googleusercontent.com"
        )
        if provider_key == "gmail":
            self.secret_label.setText("应用专用密码")
        elif provider_key == "custom":
            self.secret_label.setText("密码或授权码")
        else:
            self.secret_label.setText("邮箱授权码")
        self.provider_info_text.setText(self._connection_summary(provider_key))

    def _sync_custom_protocol(self, _index: int | None = None) -> None:
        if self.protocol.currentData() == ProtocolType.POP3.value:
            self.port.setValue(995)
        else:
            self.port.setValue(993)
        self.security.setCurrentIndex(0)
        self._update_server_placeholders()

    def _update_server_placeholders(self, _text: str = "") -> None:
        email = self.email.text().strip().casefold()
        domain = email.rsplit("@", 1)[-1] if "@" in email else "example.com"
        prefix = "pop" if self.protocol.currentData() == ProtocolType.POP3.value else "imap"
        self.host.setPlaceholderText(f"{prefix}.{domain}")

    @staticmethod
    def _connection_summary(provider_key: str) -> str:
        if provider_key == "microsoft":
            return "连接方式：Microsoft Graph API · 不保存账号密码"
        if provider_key == "gmail":
            return "默认连接：imap.gmail.com:993 SSL · smtp.gmail.com:465 SSL"
        if provider_key == "custom":
            return "支持 IMAP 993/143、POP3 995/110，以及可选 SMTP 配置"
        config = PROVIDERS.get(provider_key)
        if config is None:
            return "请确认邮箱服务商已开放客户端协议。"
        return (
            f"默认连接：{config.imap_host}:{config.imap_port} SSL · "
            f"{config.smtp_host}:{config.smtp_port}"
        )

    def _build_account(self) -> EmailAccount:
        email = self.email.text().strip().casefold()
        if not EMAIL_PATTERN.fullmatch(email):
            raise ValueError("邮箱地址格式不正确")
        option = next(
            item for item in PROVIDER_OPTIONS if item.key == self.selected_provider_key
        )
        domain = email.rsplit("@", 1)[1]
        if option.allowed_domains and domain not in option.allowed_domains:
            expected = "、".join(f"@{item}" for item in option.allowed_domains)
            raise ValueError(f"该邮箱类型只接受 {expected}；其他域名请选择企业邮箱/自定义域名")
        if option.key == "microsoft":
            client_id, refresh_token = self._oauth_values(require_uuid=True)
            return EmailAccount(
                email=email,
                provider="Outlook",
                protocol=ProtocolType.GRAPH,
                username=email,
                refresh_token=refresh_token,
                client_id=client_id,
                tenant=self.tenant.text().strip() or "common",
                oauth_provider="microsoft",
            )
        if option.key == "gmail" and self.auth_mode.currentData() == "oauth":
            client_id, refresh_token = self._oauth_values(require_uuid=False)
            config = PROVIDERS["gmail.com"]
            return self._preset_account(
                email,
                config,
                refresh_token=refresh_token,
                client_id=client_id,
                oauth_provider="google",
            )
        if option.key == "custom":
            return self._custom_account(email, domain)
        config = PROVIDERS[option.preset_domain]
        secret = self.secret.text().strip()
        if option.key == "gmail":
            secret = "".join(secret.split())
        if not secret:
            raise ValueError("请填写授权码或应用专用密码")
        return self._preset_account(email, config, secret=secret)

    def _oauth_values(self, *, require_uuid: bool) -> tuple[str, str]:
        client_id = self.client_id.text().strip()
        refresh_token = self.refresh_token.toPlainText().strip()
        if not client_id:
            raise ValueError("请填写 Client ID")
        if require_uuid:
            try:
                UUID(client_id)
            except ValueError as exc:
                raise ValueError("Microsoft Client ID 必须是有效的 UUID") from exc
        if not refresh_token:
            raise ValueError("请填写 Refresh Token")
        return client_id, refresh_token

    def _preset_account(
        self,
        email: str,
        config: ProviderConfig,
        *,
        secret: str = "",
        refresh_token: str = "",
        client_id: str = "",
        oauth_provider: str = "",
    ) -> EmailAccount:
        return EmailAccount(
            email=email,
            provider=config.name,
            protocol=ProtocolType.IMAP,
            host=config.imap_host,
            port=config.imap_port,
            security=config.security,
            username=email,
            secret=secret,
            refresh_token=refresh_token,
            client_id=client_id,
            oauth_provider=oauth_provider,
            smtp_host=config.smtp_host,
            smtp_port=config.smtp_port,
            smtp_security=config.smtp_security,
            totp_secret=self.totp_secret.text().strip(),
        )

    def _custom_account(self, email: str, domain: str) -> EmailAccount:
        protocol = ProtocolType(str(self.protocol.currentData()))
        host = self.host.text().strip().casefold()
        if not host:
            prefix = "pop" if protocol is ProtocolType.POP3 else "imap"
            host = f"{prefix}.{domain}"
        secret = self.secret.text().strip()
        if not secret:
            raise ValueError("请填写密码或授权码")
        smtp_host = self.smtp_host.text().strip().casefold()
        smtp_port = self.smtp_port.value()
        if smtp_host and not smtp_port:
            raise ValueError("填写 SMTP 服务器后还需要设置 SMTP 端口")
        if smtp_port and not smtp_host:
            raise ValueError("填写 SMTP 端口后还需要设置 SMTP 服务器")
        return EmailAccount(
            email=email,
            provider="custom",
            protocol=protocol,
            host=host,
            port=self.port.value(),
            security=SecurityMode(str(self.security.currentData())),
            username=email,
            secret=secret,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_security=SecurityMode(str(self.smtp_security.currentData())),
            totp_secret=self.totp_secret.text().strip(),
        )

    def accept(self) -> None:
        try:
            self._account = self._build_account()
        except (StopIteration, ValueError) as exc:
            QMessageBox.warning(self, "无法添加邮箱", str(exc))
            return
        super().accept()
