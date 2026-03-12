"""从 MCP 工具返回结果中检测文件路径"""
import json
import os
import re

_FILE_EXTS = {
    "pdf", "xlsx", "xls", "docx", "doc", "csv", "tsv",
    "png", "jpg", "jpeg", "gif", "svg", "webp",
    "md", "txt", "json", "html", "xml", "yaml", "yml",
    "zip", "tar", "gz", "pptx", "mp3", "wav", "mp4",
}

# 匹配简单路径（无空格/特殊字符）
_SIMPLE_PATH_RE = re.compile(r'(?:/[\w.\-]+)+\.(\w+)')


def detect_files(text: str) -> list[str]:
    """从文本中提取真实存在的文件路径列表。"""
    seen = set()
    paths = []

    def _add(p: str):
        if p not in seen:
            ext = p.rsplit(".", 1)[-1].lower() if "." in p else ""
            if ext in _FILE_EXTS and os.path.isfile(p):
                seen.add(p)
                paths.append(p)

    # 策略1：从 JSON 字符串值中提取以 / 开头的路径
    try:
        _extract_from_json(json.loads(text), _add)
    except (json.JSONDecodeError, TypeError):
        pass

    # 策略2：正则匹配简单路径
    for m in _SIMPLE_PATH_RE.finditer(text):
        _add(m.group(0))

    return paths


def _extract_from_json(obj, callback):
    if isinstance(obj, str) and obj.startswith("/"):
        callback(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _extract_from_json(v, callback)
    elif isinstance(obj, list):
        for v in obj:
            _extract_from_json(v, callback)
