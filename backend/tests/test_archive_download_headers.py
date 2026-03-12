import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.archive_download_headers import build_archive_download_headers


def test_build_archive_download_headers_keeps_full_utf8_filename():
    filename = "薪酬BU拆分_新增支持薪酬代发场景.zip"
    headers = build_archive_download_headers(filename)

    assert headers["X-Archive-Filename"] == "%E8%96%AA%E9%85%ACBU%E6%8B%86%E5%88%86_%E6%96%B0%E5%A2%9E%E6%94%AF%E6%8C%81%E8%96%AA%E9%85%AC%E4%BB%A3%E5%8F%91%E5%9C%BA%E6%99%AF.zip"
    assert "filename*=UTF-8''" in headers["Content-Disposition"]
    assert "%E8%96%AA%E9%85%ACBU%E6%8B%86%E5%88%86_%E6%96%B0%E5%A2%9E%E6%94%AF%E6%8C%81%E8%96%AA%E9%85%AC%E4%BB%A3%E5%8F%91%E5%9C%BA%E6%99%AF.zip" in headers["Content-Disposition"]


def test_build_archive_download_headers_with_blank_filename_uses_fallback():
    headers = build_archive_download_headers("   ")
    assert headers["X-Archive-Filename"] == "archive.zip"
    assert "archive.zip" in headers["Content-Disposition"]
