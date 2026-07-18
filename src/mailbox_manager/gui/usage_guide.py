from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mailbox_manager.gui.icons import line_icon
from mailbox_manager.gui.window_geometry import configure_resizable_window

_GUIDE_ASSETS = Path(__file__).resolve().parents[1] / "assets" / "guide"


def _label(text: str, object_name: str = "guideBody") -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    return label


class _AnnotatedScreenshot(QWidget):
    def __init__(
        self,
        pixmap: QPixmap,
        markers: tuple[tuple[float, float], ...],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._original = pixmap
        self._markers = markers
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

    def hasHeightForWidth(self) -> bool:
        return not self._original.isNull()

    def heightForWidth(self, width: int) -> int:
        if self._original.isNull() or self._original.width() <= 0:
            return 120
        return max(120, round(width * self._original.height() / self._original.width()))

    def sizeHint(self) -> QSize:
        width = min(1000, max(320, self._original.width()))
        return QSize(width, self.heightForWidth(width))

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        if self._original.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        target = QRectF(self.rect())
        painter.drawPixmap(target.toRect(), self._original)
        diameter = max(20, min(30, round(self.width() / 42)))
        font = QFont(self.font())
        font.setPixelSize(max(10, round(diameter * 0.45)))
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        for number, (x_ratio, y_ratio) in enumerate(self._markers, 1):
            center_x = target.left() + target.width() * x_ratio
            center_y = target.top() + target.height() * y_ratio
            badge = QRectF(
                center_x - diameter / 2,
                center_y - diameter / 2,
                diameter,
                diameter,
            )
            painter.setPen(QColor("#ffffff"))
            painter.setBrush(QColor("#2563eb"))
            painter.drawEllipse(badge)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, str(number))
        painter.end()


class GuideScreenshot(QFrame):
    """A real MailDesk screenshot with an accessible numbered legend."""

    def __init__(
        self,
        title: str,
        filename: str,
        legend: str,
        markers: tuple[tuple[float, float], ...],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("settingsCard")
        self.setAccessibleName(title)
        self.source_path = _GUIDE_ASSETS / filename
        self.original_pixmap = QPixmap(str(self.source_path))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)
        layout.addWidget(_label(title, "settingsCardTitle"))
        if self.original_pixmap.isNull():
            missing = _label("说明图片暂时不可用，请重新安装完整版本。")
            missing.setAccessibleName("使用说明图片加载失败")
            layout.addWidget(missing)
        else:
            image = _AnnotatedScreenshot(self.original_pixmap, markers)
            image.setAccessibleName(f"{title}，图片中的编号与下方说明对应")
            layout.addWidget(image)
        self.legend_label = _label(legend, "settingsCardCaption")
        layout.addWidget(self.legend_label)


class UsageGuidePage(QScrollArea):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsScroll")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        page = QWidget()
        page.setObjectName("settingsPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 23, 26, 26)
        layout.setSpacing(16)
        layout.addWidget(_label("使用说明", "settingsPageTitle"))
        layout.addWidget(
            _label(
                "以下图片由当前 MailDesk 界面直接截图并添加编号，"
                "按钮位置会随系统、字体和窗口宽度自动调整。",
                "settingsPageCaption",
            )
        )
        self._add_card(
            layout,
            "快速开始",
            "1. 点击【添加邮箱】添加单个账号，或从【批量导入】选择文件/粘贴文本。\n"
            "2. 在账号表第一列勾选账号，再点击【开始并发取件】；单账号可用【立即取件】。\n"
            "3. 邮件列表会先快速显示，点击某封邮件后再加载正文、内嵌图片和附件。\n"
            "4. 首次使用请在【系统设置】确认收件上限、代理、翻译、主题与关闭行为。",
        )
        layout.addWidget(
            GuideScreenshot(
                "工作台与全局操作",
                "dashboard-annotated.png",
                "1 工作台/账号导航　　2 添加与批量导入　　3 开始/停止取件　　"
                "4 工具菜单与使用说明　　5 主题和系统设置",
                ((0.09, 0.085), (0.069, 0.028), (0.119, 0.028), (0.91, 0.028), (0.962, 0.028)),
            )
        )
        self._add_primary_actions(layout)
        layout.addWidget(
            GuideScreenshot(
                "账号与邮件管理",
                "accounts-annotated.png",
                "1 账号勾选框　　2 邮箱地址（单击复制）　　3 密码/授权码（遮罩显示，单击复制）　　"
                "4 立即取件与批量发件　　5 邮件搜索、阅读器和筛选导出",
                ((0.21, 0.34), (0.32, 0.34), (0.43, 0.34), (0.75, 0.15), (0.74, 0.71)),
            )
        )
        self._add_mail_actions(layout)
        layout.addWidget(
            GuideScreenshot(
                "系统设置与保存",
                "settings-annotated.png",
                "1 设置分类　　2 当前页面选项　　3 恢复默认设置　　4 保存设置　　5 取消本次修改",
                ((0.16, 0.22), (0.7, 0.32), (0.23, 0.96), (0.82, 0.96), (0.95, 0.96)),
            )
        )
        self._add_settings(layout)
        self._add_troubleshooting(layout)
        layout.addStretch(1)
        self.setWidget(page)

    @staticmethod
    def _add_card(layout: QVBoxLayout, title: str, body: str) -> None:
        card = QFrame()
        card.setObjectName("settingsCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 18)
        card_layout.setSpacing(8)
        card_layout.addWidget(_label(title, "settingsCardTitle"))
        card_layout.addWidget(_label(body))
        layout.addWidget(card)

    def _add_primary_actions(self, layout: QVBoxLayout) -> None:
        self._add_card(
            layout,
            "顶部按钮与工作台",
            "【添加邮箱】按 Outlook、Gmail、QQ/163 或自定义服务器添加账号。\n"
            "【批量导入】支持 TXT、CSV、JSON 和粘贴导入；确认前会显示映射预览。\n"
            "【批量导出】导出账号及状态；【写邮件】支持单发、批量发件和附件。\n"
            "【开始并发取件】按并发任务数处理勾选账号；【停止取件】安全停止任务。\n"
            "【工具】包含运行日志、使用说明、检查更新、重置布局和审计报告。\n"
            "太阳/月亮按钮临时切换明暗模式，再切回时恢复之前选择的主题；齿轮打开系统设置。",
        )

    def _add_mail_actions(self, layout: QVBoxLayout) -> None:
        self._add_card(
            layout,
            "账号、搜索、阅读器与发件",
            "账号第一列用于勾选；邮箱地址和遮罩密码/授权码都可单击复制，完整凭据不会显示在表格。\n"
            "【显示列】控制账号字段；【移动】调整分组；右键可设置标签、固定代理、"
            "复制 2FA 或 SMTP 自检。\n"
            "【邮件搜索】可针对当前邮箱或全部邮箱搜索主题、发件人、收件人和已保存正文。\n"
            "【筛选导出】提取指定文字、链接或正则；【联网深度筛选】按需补齐尚未加载的正文。\n"
            "【阅读器】查看发件人、正文、链接和附件；链接可复制，附件可单独或全部保存。\n"
            "【翻译邮件】使用设置中的目标语言；【查看原文/查看译文】可随时切换。\n"
            "【批量发件】让每个已勾选且支持 SMTP 的账号独立发送正文和附件。",
        )
        self._add_card(
            layout,
            "分组、代理、日志与托盘",
            "左侧分组树支持新建、子分组、重命名和删除；【异常账号】集中显示失败或限流账号。\n"
            "账号固定代理优先于全局代理；全局代理关闭或没有可用代理时使用本地网络。\n"
            "【显示运行日志】展开底部抽屉；【清空】只清除当前显示，【收起】隐藏抽屉。\n"
            "关闭行为设为托盘时软件继续后台运行，双击托盘图标可恢复窗口。",
        )

    def _add_settings(self, layout: QVBoxLayout) -> None:
        self._add_card(
            layout,
            "系统设置各项功能",
            "【收件与处理】设置文件夹、单次新增上限（0=不限）、特殊文件夹、EML、提取规则和后处理。\n"
            "【调度与节流】设置当前分组定时取件、随机登录间隔和单 IP 并发。\n"
            "【网络代理】启停全局代理、添加单个代理或批量导入 HTTP/SOCKS5。\n"
            "【Webhook 对接】设置 HTTPS 推送地址、允许主机和签名密钥。\n"
            "【自动化规则】配置正则、命中动作、Webhook 与转发目标；副作用必须明确确认。\n"
            "【邮件翻译】选择目标语言和发送正文前是否确认。\n"
            "【外观与字体】选择主题、字体、9–18 pt 字号和字重；设置会持久保存并随更新保留。\n"
            "【工作台】排列四个快捷入口；【关闭与托盘】修改关闭按钮行为。\n"
            "【系统更新】后台检查、下载并校验正式发布包，不需要登录 GitHub。\n"
            "【恢复默认设置】不删除账号和邮件；【保存设置】应用修改，【取消】放弃修改。",
        )

    def _add_troubleshooting(self, layout: QVBoxLayout) -> None:
        self._add_card(
            layout,
            "常见问题",
            "无法登录：确认 IMAP/SMTP 已开启；Gmail 使用应用专用密码，QQ/163 使用授权码。\n"
            "取件超时：先关闭代理测试本地网络，再核对主机、端口、SSL、防火墙和并发数。\n"
            "有列表但正文空：点击邮件等待按需加载；旧邮件可使用联网深度筛选补齐。\n"
            "窗口拥挤：拖动窗口边缘调整大小，或在外观设置中调整字号。",
        )
        self._add_card(
            layout,
            "数据与安全",
            "密码、授权码、Refresh Token、代理密码和 Webhook 密钥均使用设备安全密钥加密。\n"
            "表格只显示凭据前三位和星号；完整值仅在用户明确点击复制时进入系统剪贴板，"
            "不会写入日志或普通导出。\n"
            "更新只替换程序文件，不覆盖软件目录中的用户数据库和设置；更新前仍建议备份用户数据目录。",
        )


class UsageGuideDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsDialog")
        self.setWindowTitle("MailDesk · 使用说明")
        configure_resizable_window(
            self,
            preferred=QSize(1040, 760),
            minimum=QSize(640, 480),
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QFrame()
        header.setObjectName("settingsHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(26, 18, 26, 17)
        icon = QLabel()
        icon.setObjectName("settingsHeaderIcon")
        icon.setFixedSize(42, 42)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(line_icon("info", "#2563eb", 22).pixmap(22, 22))
        header_layout.addWidget(icon)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        copy.addWidget(_label("MailDesk 使用说明", "settingsTitle"))
        copy.addWidget(_label("可在阅读说明时继续操作主窗口", "settingsSubtitle"))
        header_layout.addLayout(copy)
        header_layout.addStretch(1)
        layout.addWidget(header)
        layout.addWidget(UsageGuidePage(), 1)

        footer = QFrame()
        footer.setObjectName("settingsFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 12, 24, 12)
        footer_layout.addStretch(1)
        close_button = QPushButton("关闭")
        close_button.setObjectName("primaryButton")
        close_button.clicked.connect(self.close)
        footer_layout.addWidget(close_button)
        layout.addWidget(footer)
