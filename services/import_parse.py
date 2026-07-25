"""Parse CSV / Excel / free-text payloads into raw row dicts for AI import."""

from __future__ import annotations

import csv
import io
from pathlib import PurePosixPath

from openpyxl import load_workbook

from config import IMPORT_MAX_FILE_BYTES, IMPORT_MAX_ROWS

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


class ImportParseError(ValueError):
    """Raised when user payload cannot be parsed into rows."""


def _normalize_header(value: object, index: int) -> str:
    text = str(value).strip() if value is not None else ""
    return text or f"column_{index + 1}"


def _cell_to_str(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def parse_csv_bytes(data: bytes) -> list[dict[str, str]]:
    """Parse CSV bytes (utf-8 / utf-8-sig / cp1251 fallback) into row dicts."""
    text: str | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ImportParseError("Не вдалося прочитати CSV (кодування).")

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text), dialect)
    rows_list = list(reader)
    if not rows_list:
        raise ImportParseError("Файл порожній.")

    headers = [_normalize_header(h, i) for i, h in enumerate(rows_list[0])]
    result: list[dict[str, str]] = []
    for raw in rows_list[1:]:
        if not any(str(c).strip() for c in raw):
            continue
        row: dict[str, str] = {}
        for i, header in enumerate(headers):
            row[header] = _cell_to_str(raw[i]) if i < len(raw) else ""
        result.append(row)
        if len(result) > IMPORT_MAX_ROWS:
            raise ImportParseError(
                f"Занадто багато рядків (макс. {IMPORT_MAX_ROWS}). "
                "Розбий файл на кілька імпортів."
            )
    if not result:
        raise ImportParseError("У файлі немає рядків з даними.")
    return result


def parse_xlsx_bytes(data: bytes) -> list[dict[str, str]]:
    """Parse the first sheet of an .xlsx workbook into row dicts."""
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 — openpyxl raises many types
        raise ImportParseError("Не вдалося відкрити Excel-файл.") from exc

    try:
        ws = wb.active
        if ws is None:
            raise ImportParseError("У Excel-файлі немає аркушів.")

        rows_iter = ws.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration as exc:
            raise ImportParseError("Файл порожній.") from exc

        headers = [_normalize_header(h, i) for i, h in enumerate(header_row)]
        result: list[dict[str, str]] = []
        for raw in rows_iter:
            if raw is None or not any(c is not None and str(c).strip() for c in raw):
                continue
            row: dict[str, str] = {}
            for i, header in enumerate(headers):
                row[header] = _cell_to_str(raw[i]) if i < len(raw) else ""
            result.append(row)
            if len(result) > IMPORT_MAX_ROWS:
                raise ImportParseError(
                    f"Занадто багато рядків (макс. {IMPORT_MAX_ROWS}). "
                    "Розбий файл на кілька імпортів."
                )
        if not result:
            raise ImportParseError("У файлі немає рядків з даними.")
        return result
    finally:
        wb.close()


def parse_free_text(text: str) -> list[dict[str, str]]:
    """Wrap free-form text as a single raw payload for the LLM."""
    cleaned = text.strip()
    if not cleaned:
        raise ImportParseError("Повідомлення порожнє.")
    # Heuristic: tab/semicolon-separated mini-table
    lines = [ln for ln in cleaned.splitlines() if ln.strip()]
    if len(lines) >= 2 and ("\t" in lines[0] or ";" in lines[0]):
        delim = "\t" if "\t" in lines[0] else ";"
        headers = [_normalize_header(h, i) for i, h in enumerate(lines[0].split(delim))]
        result: list[dict[str, str]] = []
        for line in lines[1:]:
            parts = line.split(delim)
            if not any(p.strip() for p in parts):
                continue
            row = {
                headers[i]: (parts[i].strip() if i < len(parts) else "")
                for i in range(len(headers))
            }
            result.append(row)
            if len(result) > IMPORT_MAX_ROWS:
                raise ImportParseError(
                    f"Занадто багато рядків (макс. {IMPORT_MAX_ROWS})."
                )
        if result:
            return result
    return [{"_raw": cleaned}]


def extension_of(filename: str | None) -> str:
    if not filename:
        return ""
    return PurePosixPath(filename).suffix.lower()


def parse_document_bytes(filename: str | None, data: bytes) -> list[dict[str, str]]:
    """Dispatch file bytes to CSV or Excel parser by extension."""
    if len(data) > IMPORT_MAX_FILE_BYTES:
        mb = IMPORT_MAX_FILE_BYTES // (1024 * 1024)
        raise ImportParseError(f"Файл завеликий (макс. {mb} МБ).")

    ext = extension_of(filename)
    if ext == ".csv":
        return parse_csv_bytes(data)
    if ext in {".xlsx", ".xls"}:
        if ext == ".xls":
            raise ImportParseError(
                "Формат .xls не підтримується. Збережи файл як .xlsx або .csv."
            )
        return parse_xlsx_bytes(data)
    raise ImportParseError(
        "Підтримуються файли: .csv, .xlsx\n"
        "Або надішли дані звичайним повідомленням."
    )
