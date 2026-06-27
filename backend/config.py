"""配置读写，API Key AES 加密存储."""
import json
import logging
import os
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

CONFIG_DIR = Path(__file__).parent.parent / "config"
CONFIG_FILE = CONFIG_DIR / "settings.json"
KEY_FILE = CONFIG_DIR / ".key"

DEFAULT_CONFIG = {
    "api_key": "",
    "api_base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "continue_before_chars": 3000,
    "continue_after_chars": 500,
    "polish_before_chars": 500,
    "polish_after_chars": 200,
    "polish_expand_ratio": 1.3,
    "setting_file_path": "",
}


# NOTE: This provides obfuscation, not cryptographic security.
# The key is derived from hostname (low entropy). An attacker with
# filesystem access to the config directory can recover the API key.
# For the localhost-only threat model, this is acceptable.
def _derive_key() -> bytes:
    """基于机器标识派生加密密钥。"""
    import socket
    machine_id = socket.gethostname().encode()
    if KEY_FILE.exists():
        salt = KEY_FILE.read_bytes()
    else:
        salt = os.urandom(16)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        KEY_FILE.write_bytes(salt)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600000)
    return base64.urlsafe_b64encode(kdf.derive(machine_id))


def _encrypt(plain: str) -> str:
    f = Fernet(_derive_key())
    return f.encrypt(plain.encode()).decode()


def _decrypt(encrypted: str) -> str:
    f = Fernet(_derive_key())
    return f.decrypt(encrypted.encode()).decode()


def load_config() -> dict:
    """读取配置，不存在则返回默认。"""
    if CONFIG_FILE.exists():
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        cfg = {**DEFAULT_CONFIG, **data}
    else:
        cfg = dict(DEFAULT_CONFIG)
    if cfg["api_key"]:
        try:
            cfg["api_key"] = _decrypt(cfg["api_key"])
        except Exception:
            logging.warning(
                "API key decryption failed -- key may be from another machine. "
                "Original encrypted key preserved on disk."
            )
            cfg["api_key"] = ""
            cfg["_decryption_failed"] = True
    return cfg


def save_config(cfg: dict) -> None:
    """保存配置，加密 API Key。"""
    data = dict(cfg)
    if cfg.get("_decryption_failed") and not data.get("api_key"):
        # Preserve original encrypted key from disk to avoid overwriting
        # ciphertext with an empty string (permanent data loss).
        if CONFIG_FILE.exists():
            original = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            data["api_key"] = original.get("api_key", "")
    elif data.get("api_key"):
        data["api_key"] = _encrypt(data["api_key"])
    data.pop("_decryption_failed", None)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
