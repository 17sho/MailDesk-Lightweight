from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QMessageBox

from mailbox_manager.domain.models import EmailAccount, MailMessage, ProtocolType
from mailbox_manager.gui.mail_viewer_dialog import MailViewerDialog


def _account() -> EmailAccount:
    return EmailAccount(
        account_id=1,
        email="owner@example.com",
        provider="custom",
        protocol=ProtocolType.IMAP,
        host="imap.example.com",
        port=993,
        secret="secret",
    )


class _TranslationStub:
    def __init__(self, result: str = "翻译后的正文") -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def translate(self, text: str, *, target_language: str) -> str:
        self.calls.append((text, target_language))
        return self.result


def test_mail_viewer_translates_and_toggles_original_and_translation(
    qtbot, monkeypatch
) -> None:
    service = _TranslationStub()
    dialog = MailViewerDialog(
        _account(),
        [
            MailMessage(
                message_id=1,
                provider_message_id="translate-one",
                folder="INBOX",
                subject="Notice",
                text_body="Original body",
            )
        ],
        translation_service=service,  # type: ignore[arg-type]
        translation_language="ja",
        translation_confirm=False,
    )
    qtbot.addWidget(dialog)
    dialog.show()
    monkeypatch.setattr(dialog._pool, "start", lambda worker: worker.run())

    assert "日语" in dialog.translation_language_label.text()
    assert dialog.translate_button.isEnabled() is True
    dialog.translate_button.click()

    assert service.calls == [("Original body", "ja")]
    assert dialog.body.toPlainText() == "翻译后的正文"
    assert dialog.translation_toggle_button.text() == "查看原文"
    assert dialog.translation_toggle_button.isHidden() is False

    dialog.translation_toggle_button.click()
    assert dialog.body.toPlainText() == "Original body"
    assert dialog.translation_toggle_button.text() == "查看译文"

    dialog.translation_toggle_button.click()
    assert dialog.body.toPlainText() == "翻译后的正文"
    assert dialog.translation_toggle_button.text() == "查看原文"


def test_mail_viewer_translation_confirmation_and_live_settings_update(
    qtbot, monkeypatch
) -> None:
    service = _TranslationStub("Texte traduit")
    dialog = MailViewerDialog(
        _account(),
        [
            MailMessage(
                provider_message_id="confirm",
                folder="INBOX",
                text_body="Body to translate",
            )
        ],
        translation_service=service,  # type: ignore[arg-type]
        translation_confirm=True,
    )
    qtbot.addWidget(dialog)
    dialog.show()
    monkeypatch.setattr(dialog._pool, "start", lambda worker: worker.run())
    confirmations: list[str] = []

    def cancel_translation(_parent, _title, message, *_args, **_kwargs):
        confirmations.append(message)
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "question", cancel_translation)
    dialog.translate_button.click()

    assert len(confirmations) == 1
    assert service.calls == []

    dialog.update_translation_settings("fr", False)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("关闭确认后不应再弹出确认框")
        ),
    )
    dialog.translate_button.click()

    assert "法语" in dialog.translation_language_label.text()
    assert "翻译前确认" not in dialog.translation_language_label.text()
    assert service.calls == [("Body to translate", "fr")]
    assert dialog.body.toPlainText() == "Texte traduit"


def test_mail_viewer_ignores_translation_result_after_switching_message(
    qtbot, monkeypatch
) -> None:
    service = _TranslationStub()
    dialog = MailViewerDialog(
        _account(),
        [
            MailMessage(
                message_id=1,
                provider_message_id="first",
                folder="INBOX",
                subject="First",
                text_body="First body",
            ),
            MailMessage(
                message_id=2,
                provider_message_id="second",
                folder="INBOX",
                subject="Second",
                text_body="Second body",
            ),
        ],
        selected_message_id=1,
        translation_service=service,  # type: ignore[arg-type]
        translation_confirm=False,
    )
    qtbot.addWidget(dialog)
    dialog.show()
    workers = []
    monkeypatch.setattr(dialog._pool, "start", workers.append)

    dialog.translate_button.click()
    first_worker = workers.pop()
    dialog.inbox_list.setCurrentRow(1)
    first_worker.signals.result.emit(first_worker.generation, "STALE RESULT", None)
    first_worker.signals.finished.emit(first_worker.generation)

    assert dialog.subject_label.text() == "Second"
    assert dialog.body.toPlainText() == "Second body"
    assert dialog._translated_text == ""
    assert dialog.translation_toggle_button.isHidden() is True

    dialog.translate_button.click()
    second_worker = workers.pop()
    second_worker.signals.result.emit(second_worker.generation, "CURRENT RESULT", None)
    second_worker.signals.finished.emit(second_worker.generation)

    assert dialog.body.toPlainText() == "CURRENT RESULT"
    assert dialog.translation_toggle_button.isHidden() is False


def test_mail_viewer_ignores_translation_result_after_close(qtbot, monkeypatch) -> None:
    dialog = MailViewerDialog(
        _account(),
        [
            MailMessage(
                provider_message_id="closing",
                folder="INBOX",
                text_body="Body",
            )
        ],
        translation_service=_TranslationStub(),  # type: ignore[arg-type]
        translation_confirm=False,
    )
    qtbot.addWidget(dialog)
    dialog.show()
    workers = []
    monkeypatch.setattr(dialog._pool, "start", workers.append)

    dialog.translate_button.click()
    worker = workers.pop()
    dialog.close()
    worker.signals.result.emit(worker.generation, "LATE RESULT", None)
    worker.signals.finished.emit(worker.generation)

    assert dialog._translated_text == ""
