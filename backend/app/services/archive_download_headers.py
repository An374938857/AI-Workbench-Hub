from __future__ import annotations

from urllib.parse import quote


def build_archive_download_headers(filename: str) -> dict[str, str]:
    safe_name = (filename or "archive.zip").strip() or "archive.zip"
    ascii_fallback = safe_name.encode("ascii", errors="ignore").decode("ascii").strip()
    if not ascii_fallback:
        ascii_fallback = "archive.zip"
    encoded = quote(safe_name)
    encoded = quote(safe_name)
    return {
        "Content-Disposition": f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}",
        "X-Archive-Filename": encoded,
    }
