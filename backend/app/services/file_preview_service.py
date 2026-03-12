from pathlib import Path
import zipfile

from app.services.file_service import extract_text, extract_xlsx_table

TEXT_PREVIEW_TYPES = {
    "txt",
    "md",
    "markdown",
    "json",
    "csv",
    "xml",
    "yaml",
    "yml",
    "py",
    "js",
    "ts",
    "css",
}
MARKDOWN_TYPES = {"md", "markdown"}
HTML_TYPES = {"html", "htm"}
IMAGE_TYPES = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg"}


def build_preview_payload(
    *,
    file_path: str | Path,
    file_type: str,
    filename: str,
    file_size: int,
    download_url: str | None = None,
    image_preview_url: str | None = None,
    text_limit: int = 100000,
) -> dict:
    path = Path(file_path)
    normalized_type = (file_type or "").lower()

    if normalized_type in IMAGE_TYPES:
        payload = {
            "filename": filename,
            "file_type": normalized_type,
            "file_size": file_size,
            "preview_type": "image",
            "preview_url": image_preview_url or download_url,
        }
        if download_url:
            payload["download_url"] = download_url
        return payload

    if normalized_type in TEXT_PREVIEW_TYPES | HTML_TYPES:
        try:
            content = path.read_text(encoding="utf-8")
            payload = {
                "filename": filename,
                "file_type": normalized_type,
                "file_size": file_size,
                "preview_type": (
                    "markdown"
                    if normalized_type in MARKDOWN_TYPES
                    else "html"
                    if normalized_type in HTML_TYPES
                    else "text"
                ),
                "content": content[:text_limit],
                "truncated": len(content) > text_limit,
            }
            if download_url:
                payload["download_url"] = download_url
            return payload
        except Exception as exc:
            payload = {
                "filename": filename,
                "file_type": normalized_type,
                "file_size": file_size,
                "preview_type": "download_only",
                "preview_notice": f"读取文件失败: {str(exc)}",
            }
            if download_url:
                payload["download_url"] = download_url
            return payload

    if normalized_type == "pdf":
        try:
            with path.open("rb") as file:
                header = file.read(1024)
            if b"%PDF" not in header:
                snippet = header[:120].decode("utf-8", errors="replace")
                payload = {
                    "filename": filename,
                    "file_type": normalized_type,
                    "file_size": file_size,
                    "preview_type": "text",
                    "content": (
                        "该文件扩展名为 .pdf，但内容不是有效的 PDF 二进制文件，无法在线预览。\n\n"
                        f"文件头片段：{snippet}\n\n"
                        "建议：重新上传真实 PDF 文件，或先下载后确认文件内容。"
                    ),
                }
                if download_url:
                    payload["download_url"] = download_url
                return payload
        except Exception as exc:
            payload = {
                "filename": filename,
                "file_type": normalized_type,
                "file_size": file_size,
                "preview_type": "download_only",
                "preview_notice": f"读取 PDF 文件头失败: {str(exc)}",
            }
            if download_url:
                payload["download_url"] = download_url
            return payload

        payload = {
            "filename": filename,
            "file_type": normalized_type,
            "file_size": file_size,
            "preview_type": "pdf",
            "preview_url": download_url,
        }
        if download_url:
            payload["download_url"] = download_url
        return payload

    if normalized_type == "xlsx":
        try:
            table_data = extract_xlsx_table(str(path), max_rows=200, max_cols=50)
            payload = {
                "filename": filename,
                "file_type": normalized_type,
                "file_size": file_size,
                "preview_type": "xlsx_table",
                "sheets": table_data["sheets"],
                "sheet_count": len(table_data["sheets"]),
            }
            if download_url:
                payload["download_url"] = download_url
            return payload
        except Exception:
            payload = {
                "filename": filename,
                "file_type": normalized_type,
                "file_size": file_size,
                "preview_type": "text",
                "content": (
                    "表格预览失败，已降级为文本预览：\n\n"
                    f"{extract_text(str(path), 'xlsx')[:text_limit]}"
                ),
            }
            if download_url:
                payload["download_url"] = download_url
            return payload

    if normalized_type in {"docx", "zip"}:
        try:
            if normalized_type == "docx":
                content = extract_text(str(path), normalized_type)
            else:
                with zipfile.ZipFile(path, "r") as zip_file:
                    file_list = zip_file.namelist()
                content = "\n".join(file_list[:1000])
                if len(file_list) > 1000:
                    content += f"\n\n... 共 {len(file_list)} 个文件，当前仅展示前 1000 个条目"
            payload = {
                "filename": filename,
                "file_type": normalized_type,
                "file_size": file_size,
                "preview_type": "text",
                "content": content[:text_limit],
                "truncated": len(content) > text_limit,
            }
            if download_url:
                payload["download_url"] = download_url
            return payload
        except Exception as exc:
            payload = {
                "filename": filename,
                "file_type": normalized_type,
                "file_size": file_size,
                "preview_type": "download_only",
                "preview_notice": f"预览文件失败: {str(exc)}",
            }
            if download_url:
                payload["download_url"] = download_url
            return payload

    payload = {
        "filename": filename,
        "file_type": normalized_type,
        "file_size": file_size,
        "preview_type": "download_only",
    }
    if download_url:
        payload["download_url"] = download_url
    return payload
