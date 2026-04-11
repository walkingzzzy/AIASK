import os
from pathlib import Path


def _load_dotenv_values() -> dict[str, str]:
    values: dict[str, str] = {}
    candidates = [
        Path(__file__).resolve().parents[2] / ".env",
        Path.cwd() / ".env",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in values:
                    values[key] = value
        except Exception:
            continue
    return values


_DOTENV_VALUES = _load_dotenv_values()


def _resolve_setting(name: str, default: str = "") -> str:
    return os.getenv(name, "").strip() or _DOTENV_VALUES.get(name, "").strip() or default


TUSHARE_TOKEN = _resolve_setting("TUSHARE_TOKEN")
TUSHARE_HTTP_URL = _resolve_setting("TUSHARE_HTTP_URL", "http://api.tushare.pro")


def ensure_tushare_token() -> None:
    if not TUSHARE_TOKEN:
        raise RuntimeError("未配置 TUSHARE_TOKEN：请在环境变量或 packages/akshare-mcp/.env 中设置")
