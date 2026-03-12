import json

from cryptography.fernet import Fernet

from app.config import get_settings

settings = get_settings()


def _get_fernet() -> Fernet:
    key = settings.ENCRYPTION_KEY
    if not key:
        raise ValueError("ENCRYPTION_KEY 未配置，请在 .env 中设置")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_api_key(api_key: str) -> str:
    f = _get_fernet()
    return f.encrypt(api_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    f = _get_fernet()
    return f.decrypt(encrypted_key.encode()).decode()


def mask_api_key(api_key: str) -> str:
    if len(api_key) <= 8:
        return "****"
    return api_key[:4] + "****" + api_key[-4:]


def encrypt_mcp_config(config_json: dict) -> str:
    json_str = json.dumps(config_json, ensure_ascii=False)
    f = _get_fernet()
    return f.encrypt(json_str.encode()).decode()


def decrypt_mcp_config(encrypted: str) -> dict:
    f = _get_fernet()
    json_str = f.decrypt(encrypted.encode()).decode()
    return json.loads(json_str)
