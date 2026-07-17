from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRect, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QKeyEvent, QMouseEvent, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QHeaderView,
    QStyle,
    QStyleOptionButton,
    QTableView,
    QWidget,
)

from mailbox_manager.domain.models import EmailAccount
from mailbox_manager.domain.status import STATUS_LABELS, AccountStatus

_ROOT_INDEX = QModelIndex()


class AccountTableModel(QAbstractTableModel):
    checkedChanged = Signal()
    HEADERS = ("", "账号", "邮箱类型", "协议", "服务器", "标签", "最近收件", "状态")

    def __init__(self, accounts: list[EmailAccount] | None = None) -> None:
        super().__init__()
        self._accounts = list(accounts or [])
        self._checked_ids: set[int] = set()

    def rowCount(self, _parent: QModelIndex = _ROOT_INDEX) -> int:
        return len(self._accounts)

    def columnCount(self, _parent: QModelIndex = _ROOT_INDEX) -> int:
        return len(self.HEADERS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        if role == Qt.ItemDataRole.ToolTipRole and section == 0:
            return "全选或取消当前列表中的账号"
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._accounts):
            return None
        account = self._accounts[index.row()]
        if role == Qt.ItemDataRole.CheckStateRole and index.column() == 0:
            return (
                Qt.CheckState.Checked
                if account.account_id in self._checked_ids
                else Qt.CheckState.Unchecked
            )
        if role == Qt.ItemDataRole.DisplayRole:
            values = (
                "",
                account.email,
                account.provider,
                account.protocol.value.upper(),
                f"{account.host}:{account.port}" if account.host else "Microsoft Graph",
                " · ".join(account.tags) or "—",
                _format_time(account.last_fetch_at),
                STATUS_LABELS[account.status],
            )
            return values[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole:
            if index.column() == 1:
                return "单击复制邮箱地址"
            return account.status_detail or STATUS_LABELS[account.status]
        if role == Qt.ItemDataRole.UserRole:
            return account.account_id
        if role == Qt.ItemDataRole.ForegroundRole and index.column() == 7:
            return _status_color(account.status)
        if role == Qt.ItemDataRole.FontRole and index.column() in {1, 7}:
            application = QApplication.instance()
            font = QFont(application.font()) if application is not None else QFont()
            font.setWeight(
                QFont.Weight(max(int(font.weight()), int(QFont.Weight.DemiBold)))
            )
            return font
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() in {0, 3, 6, 7}:
            return Qt.AlignmentFlag.AlignCenter
        if role == Qt.ItemDataRole.AccessibleTextRole:
            state = "已勾选" if account.account_id in self._checked_ids else "未勾选"
            return f"{state}，{account.email}，状态 {STATUS_LABELS[account.status]}"
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 0:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def setData(
        self,
        index: QModelIndex,
        value: object,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        if (
            role != Qt.ItemDataRole.CheckStateRole
            or not index.isValid()
            or index.column() != 0
        ):
            return False
        self.set_checked(index.row(), value == Qt.CheckState.Checked)
        return True

    def set_accounts(self, accounts: list[EmailAccount]) -> None:
        previous = set(self._checked_ids)
        visible_ids = {
            account.account_id for account in accounts if account.account_id is not None
        }
        self.beginResetModel()
        self._accounts = list(accounts)
        self._checked_ids.intersection_update(visible_ids)
        self.endResetModel()
        if previous != self._checked_ids:
            self.checkedChanged.emit()

    def account_at(self, row: int) -> EmailAccount | None:
        if 0 <= row < len(self._accounts):
            return self._accounts[row]
        return None

    def accounts(self) -> list[EmailAccount]:
        return list(self._accounts)

    def checked_accounts(self) -> list[EmailAccount]:
        return [
            account for account in self._accounts if account.account_id in self._checked_ids
        ]

    def is_checked(self, row: int) -> bool:
        account = self.account_at(row)
        return bool(account and account.account_id in self._checked_ids)

    def set_checked(self, row: int, checked: bool, *, exclusive: bool = False) -> None:
        account = self.account_at(row)
        if account is None or account.account_id is None:
            return
        previous = set(self._checked_ids)
        if exclusive:
            self._checked_ids.clear()
        if checked:
            self._checked_ids.add(account.account_id)
        else:
            self._checked_ids.discard(account.account_id)
        if previous == self._checked_ids:
            return
        if exclusive:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(max(0, self.rowCount() - 1), 0),
                [Qt.ItemDataRole.CheckStateRole],
            )
        else:
            index = self.index(row, 0)
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 0)
        self.checkedChanged.emit()

    def set_all_checked(self, checked: bool) -> None:
        previous = set(self._checked_ids)
        self._checked_ids = (
            {
                account.account_id
                for account in self._accounts
                if account.account_id is not None
            }
            if checked
            else set()
        )
        if previous == self._checked_ids:
            return
        if self.rowCount():
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self.rowCount() - 1, 0),
                [Qt.ItemDataRole.CheckStateRole],
            )
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 0)
        self.checkedChanged.emit()

    def aggregate_check_state(self) -> Qt.CheckState:
        checked = len(self.checked_accounts())
        if checked == 0:
            return Qt.CheckState.Unchecked
        if checked == self.rowCount():
            return Qt.CheckState.Checked
        return Qt.CheckState.PartiallyChecked


class AccountCheckHeader(QHeaderView):
    """Header with a native tri-state checkbox for visible account rows."""

    def __init__(self, model: AccountTableModel, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._account_model = model
        model.checkedChanged.connect(lambda: self.updateSection(0))
        self.setSectionsClickable(True)

    def paintSection(self, painter: QPainter, rect: QRect, logical_index: int) -> None:
        super().paintSection(painter, rect, logical_index)
        if logical_index != 0 or not rect.isValid():
            return
        option = QStyleOptionButton()
        indicator_width = self.style().pixelMetric(
            QStyle.PixelMetric.PM_IndicatorWidth, option, self
        )
        indicator_height = self.style().pixelMetric(
            QStyle.PixelMetric.PM_IndicatorHeight, option, self
        )
        option.rect = QRect(
            rect.center().x() - indicator_width // 2,
            rect.center().y() - indicator_height // 2,
            indicator_width,
            indicator_height,
        )
        option.state = QStyle.StateFlag.State_Enabled
        state = self._account_model.aggregate_check_state()
        if state is Qt.CheckState.Checked:
            option.state |= QStyle.StateFlag.State_On
        elif state is Qt.CheckState.PartiallyChecked:
            option.state |= QStyle.StateFlag.State_NoChange
        else:
            option.state |= QStyle.StateFlag.State_Off
        self.style().drawControl(QStyle.ControlElement.CE_CheckBox, option, painter, self)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self.logicalIndexAt(event.position().toPoint()) == 0:
            checked = self._account_model.aggregate_check_state() is Qt.CheckState.Checked
            self._account_model.set_all_checked(not checked)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class AccountTableView(QTableView):
    """No-highlight table that still handles checkbox and detail clicks explicitly."""

    accountActivated = Signal(QModelIndex)
    emailCopyRequested = Signal(QModelIndex)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            index = self.indexAt(event.position().toPoint())
            if index.isValid() and index.column() == 1:
                self.emailCopyRequested.emit(index)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        index = self.indexAt(event.position().toPoint())
        cursor = (
            Qt.CursorShape.PointingHandCursor
            if index.isValid() and index.column() == 1
            else Qt.CursorShape.ArrowCursor
        )
        self.viewport().setCursor(QCursor(cursor))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            index = self.indexAt(event.position().toPoint())
            if index.isValid():
                self.setCurrentIndex(index)
                model = self.model()
                if index.column() == 0 and isinstance(model, AccountTableModel):
                    model.set_checked(index.row(), not model.is_checked(index.row()))
                self.accountActivated.emit(index)
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        index = self.currentIndex()
        model = self.model()
        if (
            event.key() == Qt.Key.Key_Space
            and index.isValid()
            and isinstance(model, AccountTableModel)
        ):
            model.set_checked(index.row(), not model.is_checked(index.row()))
            self.accountActivated.emit(index)
            event.accept()
            return
        super().keyPressEvent(event)


def _format_time(value: datetime | None) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S") if value else "—"


def _status_color(status: AccountStatus) -> QColor | None:
    colors = {
        AccountStatus.SUCCESS: QColor("#059669"),
        AccountStatus.AUTH_FAILED: QColor("#dc2626"),
        AccountStatus.BLOCKED: QColor("#dc2626"),
        AccountStatus.RATE_LIMITED: QColor("#d97706"),
        AccountStatus.CONNECTING: QColor("#2563eb"),
        AccountStatus.NETWORK_ERROR: QColor("#dc2626"),
        AccountStatus.TIMEOUT: QColor("#d97706"),
    }
    return colors.get(status)
