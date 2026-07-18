from __future__ import annotations

import json

from mailbox_manager.domain.models import ProtocolType, SecurityMode
from mailbox_manager.importers.file_importer import import_file
from mailbox_manager.importers.smart_parser import SmartAccountParser


def test_parser_understands_imap_provider_and_graph_lines() -> None:
    parser = SmartAccountParser()
    preview = parser.parse_text(
        "custom@example.org----pw----imap.example.org----993\n"
        "user@qq.com----ignored-main-password----authorization-code\n"
        "owner@outlook.com----long-refresh-token-value----"
        "00000000-0000-0000-0000-000000000001"
    )

    accounts = preview.valid_accounts
    assert preview.error_count == 0
    assert accounts[0].host == "imap.example.org"
    assert accounts[1].host == "imap.qq.com"
    assert accounts[1].secret == "authorization-code"
    assert accounts[2].protocol is ProtocolType.GRAPH
    assert accounts[2].refresh_token == "long-refresh-token-value"


def test_parser_understands_four_field_outlook_oauth_in_both_orders() -> None:
    parser = SmartAccountParser()
    client_id = "00000000-0000-0000-0000-000000000001"
    preview = parser.parse_text(
        f"first@outlook.com----password----{client_id}----first-refresh-token-value\n"
        f"second@outlook.com----password----second-refresh-token-value----{client_id}"
    )

    assert preview.error_count == 0
    first, second = preview.valid_accounts
    assert first.protocol is ProtocolType.GRAPH
    assert first.client_id == client_id
    assert first.refresh_token == "first-refresh-token-value"
    assert second.protocol is ProtocolType.GRAPH
    assert second.refresh_token == "second-refresh-token-value"
    assert first.secret == "password"
    assert second.secret == "password"


def test_oauth_mapping_preserves_an_optional_password() -> None:
    client_id = "00000000-0000-0000-0000-000000000001"
    preview = SmartAccountParser().parse_records(
        [
            {
                "邮箱地址": "owner@outlook.com",
                "密码": "outlook-password",
                "RefreshToken": "long-refresh-token-value",
                "ClientID": client_id,
            }
        ]
    )

    assert preview.error_count == 0
    account = preview.valid_accounts[0]
    assert account.protocol is ProtocolType.GRAPH
    assert account.secret == "outlook-password"


def test_freeform_outlook_oauth_distinguishes_password_from_refresh_token() -> None:
    client_id = "00000000-0000-0000-0000-000000000001"
    preview = SmartAccountParser().parse_text(
        f"owner@outlook.com outlook-password {client_id} "
        "M.C515_BL2.0.U.MsaArtifacts-long-refresh-token"
    )

    assert preview.error_count == 0
    account = preview.valid_accounts[0]
    assert account.secret == "outlook-password"
    assert account.refresh_token == "M.C515_BL2.0.U.MsaArtifacts-long-refresh-token"


def test_parser_does_not_silently_treat_malformed_outlook_oauth_as_password() -> None:
    preview = SmartAccountParser().parse_text(
        "owner@outlook.com----password----not-a-client-id----long-refresh-token-value"
    )

    assert preview.error_count == 1
    assert "Client ID" in preview.rows[0].error


def test_parser_reports_invalid_rows_without_echoing_secret() -> None:
    preview = SmartAccountParser().parse_text("not-an-email----do-not-leak")

    assert preview.error_count == 1
    assert "do-not-leak" not in preview.rows[0].raw_masked


def test_json_file_import_supports_accounts_wrapper(tmp_path) -> None:
    source = tmp_path / "accounts.json"
    source.write_text(
        json.dumps({"accounts": [{"email": "a@163.com", "secret": "auth-code"}]}),
        encoding="utf-8",
    )

    preview = import_file(source)

    assert preview.valid_accounts[0].host == "imap.163.com"


def test_freeform_parser_extracts_email_adjacent_secret_and_ignores_proxy() -> None:
    preview = SmartAccountParser().parse_text(
        "业务A | user@qq.com authorization-code | 127.0.0.1:1080:proxy:pass"
    )

    assert preview.error_count == 0
    account = preview.valid_accounts[0]
    assert account.email == "user@qq.com"
    assert account.secret == "authorization-code"
    assert account.host == "imap.qq.com"
    assert any("代理" in warning for warning in preview.rows[0].warnings)


def test_freeform_custom_domain_uses_reviewable_discovery_candidate() -> None:
    preview = SmartAccountParser().parse_text("owner@company.example app-password")

    account = preview.valid_accounts[0]
    assert account.host == "imap.company.example"
    assert preview.rows[0].confidence == "low"
    assert any("自动发现" in warning for warning in preview.rows[0].warnings)


def test_json_import_can_select_pop3_protocol(tmp_path) -> None:
    source = tmp_path / "pop.json"
    source.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "email": "owner@163.com",
                        "secret": "auth-code",
                        "protocol": "pop3",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    account = import_file(source).valid_accounts[0]

    assert account.protocol is ProtocolType.POP3
    assert account.host == "pop.163.com"
    assert account.port == 995


def test_gmail_oauth_txt_and_google_workspace_are_not_misclassified() -> None:
    client_id = "123456789-example.apps.googleusercontent.com"
    preview = SmartAccountParser().parse_text(
        f"owner@gmail.com----google-refresh-token----{client_id}\n"
        f"owner@workspace.example----workspace-refresh-token----{client_id}"
    )

    assert preview.error_count == 0
    gmail, workspace = preview.valid_accounts
    assert gmail.oauth_provider == "google"
    assert gmail.refresh_token == "google-refresh-token"
    assert gmail.secret == ""
    assert workspace.provider == "Gmail"
    assert workspace.protocol is ProtocolType.IMAP
    assert workspace.host == "imap.gmail.com"
    assert workspace.oauth_provider == "google"


def test_gmail_app_password_spaces_are_normalized_in_text_and_records() -> None:
    parser = SmartAccountParser()
    delimited = parser.parse_text("first@gmail.com----abcd efgh ijkl mnop").valid_accounts[0]
    freeform = parser.parse_text("second@gmail.com abcd efgh ijkl mnop").valid_accounts[0]
    mapped = parser.parse_records(
        [{"email": "third@gmail.com", "password": "abcd efgh ijkl mnop"}]
    ).valid_accounts[0]

    assert delimited.secret == "abcdefghijklmnop"
    assert freeform.secret == "abcdefghijklmnop"
    assert mapped.secret == "abcdefghijklmnop"


def test_txt_can_infer_pop3_and_mapping_honors_security_modes() -> None:
    pop = (
        SmartAccountParser()
        .parse_text("owner@example.org----password----pop.example.org----995")
        .valid_accounts[0]
    )
    mapped = (
        SmartAccountParser()
        .parse_records(
            [
                {
                    "email": "owner@example.org",
                    "password": "password",
                    "host": "imap.example.org",
                    "port": "143",
                    "security": "plain",
                    "smtp_host": "smtp.example.org",
                    "smtp_port": "587",
                    "smtp_security": "starttls",
                }
            ]
        )
        .valid_accounts[0]
    )

    assert pop.protocol is ProtocolType.POP3
    assert pop.port == 995
    assert mapped.security is SecurityMode.PLAIN
    assert mapped.smtp_security is SecurityMode.STARTTLS


def test_delimited_custom_domain_with_password_uses_discovery_candidate() -> None:
    preview = SmartAccountParser().parse_text("owner@company.example----application-password")

    assert preview.error_count == 0
    account = preview.valid_accounts[0]
    assert account.provider == "custom"
    assert account.host == "imap.company.example"
    assert account.port == 993
    assert account.secret == "application-password"
    assert preview.rows[0].confidence == "low"
    assert any("自动发现" in warning for warning in preview.rows[0].warnings)


def test_csv_import_accepts_chinese_headers_and_infers_pop3(tmp_path) -> None:
    source = tmp_path / "accounts.csv"
    source.write_text(
        "邮箱地址;密码;服务器;端口;连接加密\n"
        "owner@example.org;app-password;pop.example.org;995;SSL/TLS\n",
        encoding="utf-8-sig",
    )

    preview = import_file(source)

    assert preview.error_count == 0
    account = preview.valid_accounts[0]
    assert account.protocol is ProtocolType.POP3
    assert account.host == "pop.example.org"
    assert account.port == 995
    assert account.security is SecurityMode.SSL


def test_headerless_csv_uses_the_same_account_formats_as_txt(tmp_path) -> None:
    source = tmp_path / "accounts.csv"
    client_id = "00000000-0000-0000-0000-000000000001"
    source.write_text(
        "owner@qq.com,ignored-password,qq-auth-code\n"
        f"owner@outlook.com,outlook-refresh-token,{client_id}\n",
        encoding="utf-8",
    )

    preview = import_file(source)

    assert preview.error_count == 0
    qq, outlook = preview.valid_accounts
    assert qq.secret == "qq-auth-code"
    assert outlook.protocol is ProtocolType.GRAPH
    assert outlook.refresh_token == "outlook-refresh-token"


def test_google_workspace_app_password_can_be_selected_in_mapping() -> None:
    preview = SmartAccountParser().parse_records(
        [
            {
                "邮箱": "owner@workspace.example",
                "应用专用密码": "abcd efgh ijkl mnop",
                "邮箱类型": "Google Workspace",
            }
        ]
    )

    assert preview.error_count == 0
    account = preview.valid_accounts[0]
    assert account.provider == "Gmail"
    assert account.host == "imap.gmail.com"
    assert account.secret == "abcdefghijklmnop"
