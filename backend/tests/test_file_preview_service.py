from pathlib import Path
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services.file_preview_service import build_preview_payload


def test_markdown_preview_type(tmp_path: Path):
    md_file = tmp_path / "sample.md"
    md_file.write_text("# Title\n\nhello", encoding="utf-8")

    payload = build_preview_payload(
        file_path=md_file,
        file_type="md",
        filename="sample.md",
        file_size=md_file.stat().st_size,
        download_url="/download/sample.md",
    )

    assert payload["preview_type"] == "markdown"
    assert "Title" in payload.get("content", "")
    assert payload.get("download_url") == "/download/sample.md"


def test_invalid_pdf_fallback_to_text_notice(tmp_path: Path):
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_text("not a real pdf", encoding="utf-8")

    payload = build_preview_payload(
        file_path=fake_pdf,
        file_type="pdf",
        filename="fake.pdf",
        file_size=fake_pdf.stat().st_size,
        download_url="/download/fake.pdf",
    )

    assert payload["preview_type"] == "text"
    assert "不是有效的 PDF" in payload.get("content", "")
    assert payload.get("download_url") == "/download/fake.pdf"


def test_valid_pdf_preview_type(tmp_path: Path):
    from pypdf import PdfWriter

    pdf_file = tmp_path / "valid.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with pdf_file.open("wb") as f:
        writer.write(f)

    payload = build_preview_payload(
        file_path=pdf_file,
        file_type="pdf",
        filename="valid.pdf",
        file_size=pdf_file.stat().st_size,
        download_url="/download/valid.pdf",
    )

    assert payload["preview_type"] == "pdf"
    assert payload.get("preview_url") == "/download/valid.pdf"


def test_xlsx_preview_sheet_payload(tmp_path: Path):
    from openpyxl import Workbook

    xlsx_file = tmp_path / "table.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["name", "value"])
    ws.append(["a", 1])
    wb.save(xlsx_file)

    payload = build_preview_payload(
        file_path=xlsx_file,
        file_type="xlsx",
        filename="table.xlsx",
        file_size=xlsx_file.stat().st_size,
        download_url="/download/table.xlsx",
    )

    assert payload["preview_type"] == "xlsx_table"
    assert payload.get("sheet_count") == 1
    assert payload.get("sheets")


def test_unknown_file_type_download_only(tmp_path: Path):
    file = tmp_path / "data.bin"
    file.write_bytes(b"\x00\x01\x02")

    payload = build_preview_payload(
        file_path=file,
        file_type="bin",
        filename="data.bin",
        file_size=file.stat().st_size,
        download_url="/download/data.bin",
    )

    assert payload["preview_type"] == "download_only"
    assert payload.get("download_url") == "/download/data.bin"
