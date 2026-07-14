from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from mailbox_manager.domain.models import ImportPreview
from mailbox_manager.importers.smart_parser import SmartAccountParser

MAX_FILE_SIZE = 20 * 1024 * 1024
_CSV_EMAIL_HEADERS = {
    "email",
    "account",
    "username",
    "账号",
    "邮箱",
    "邮箱账号",
    "邮箱地址",
}


def _read_text(path: Path) -> str:
    if path.stat().st_size > MAX_FILE_SIZE:
        raise ValueError("导入文件不能超过 20 MiB")
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("文件编码不受支持，请使用 UTF-8")


def import_file(path: Path, parser: SmartAccountParser | None = None) -> ImportPreview:
    path = Path(path)
    parser = parser or SmartAccountParser()
    suffix = path.suffix.casefold()
    text = _read_text(path)
    if suffix == ".txt":
        return parser.parse_text(text)
    if suffix == ".csv":
        return _import_csv(text, parser)
    if suffix == ".json":
        payload = json.loads(text)
        records = payload.get("accounts") if isinstance(payload, dict) else payload
        if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
            raise ValueError("JSON 必须是账号对象数组或包含 accounts 数组")
        return parser.parse_records(records)
    raise ValueError("仅支持 TXT、CSV、JSON 文件")


def _import_csv(text: str, parser: SmartAccountParser) -> ImportPreview:
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [row for row in csv.reader(io.StringIO(text), dialect=dialect) if any(row)]
    if not rows:
        return ImportPreview(())
    header = {
        re.sub(r"[\s_-]+", "", value.strip().casefold()) for value in rows[0]
    }
    normalized_headers = {
        re.sub(r"[\s_-]+", "", value.casefold()) for value in _CSV_EMAIL_HEADERS
    }
    if header & normalized_headers:
        return parser.parse_records(
            csv.DictReader(io.StringIO(text), dialect=dialect)
        )
    positional_text = "\n".join(
        "----".join(column.strip() for column in row) for row in rows
    )
    return parser.parse_text(positional_text)
