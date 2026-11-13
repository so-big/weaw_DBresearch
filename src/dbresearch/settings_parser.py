"""Parser for setting.txt (Single source of truth)."""
import configparser
import os
import re
from pathlib import Path
from typing import Any, Dict


def parse_setting_file(filepath: Path | str | None = None) -> Dict[str, Dict[str, Any]]:
    """Parse setting.txt exclusively.
    
    - Ignores lines starting with '#' or ';' (comments).
    - Ignores empty lines.
    - Parses sections [web] and [mysql].
    """
    candidates = []
    if filepath:
        candidates.append(Path(filepath))

    env_file = os.environ.get("SETTING_FILE")
    if env_file:
        candidates.append(Path(env_file))

    candidates.extend([
        Path("setting.txt"),
        Path("/app/setting.txt"),
        Path("setting.txt.example"),
        Path("/app/setting.txt.example"),
    ])

    resolved_path = None
    for cand in candidates:
        if cand.is_file():
            resolved_path = cand
            break

    result: Dict[str, Dict[str, Any]] = {
        "web": {
            "port": 8120,
            "username": "admin",
            "password": "admin123456",
        },
        "mysql": {
            "host": "10.27.50.43",
            "port": 3307,
            "database": "weaw_dbresearch",
            "username": "weaw_ocr",
            "password": "",
            "ssl_ca": "mysql-ca.pem",
        },
    }

    if not resolved_path:
        return result

    raw_lines = resolved_path.read_text(encoding="utf-8-sig").splitlines()
    clean_lines = []
    for line in raw_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue
        clean_lines.append(stripped)

    has_sections = any(re.match(r"^\[.+\]$", line) for line in clean_lines)

    if has_sections:
        config = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
        try:
            config.read_string("\n".join(clean_lines))
            for section in config.sections():
                sec_lower = section.lower()
                if sec_lower in ("web", "app", "api"):
                    for k, v in config.items(section):
                        result["web"][k.lower()] = int(v) if k.lower() == "port" and v.isdigit() else v
                elif sec_lower in ("mysql", "database", "dbroot", "db"):
                    for k, v in config.items(section):
                        result["mysql"][k.lower()] = int(v) if k.lower() == "port" and v.isdigit() else v
        except Exception:
            pass

    # Environment variables override (if provided)
    if os.environ.get("PORT") and os.environ["PORT"].isdigit():
        result["web"]["port"] = int(os.environ["PORT"])
    if os.environ.get("ADMIN_USERNAME"):
        result["web"]["username"] = os.environ["ADMIN_USERNAME"]
    if os.environ.get("ADMIN_PASSWORD"):
        result["web"]["password"] = os.environ["ADMIN_PASSWORD"]

    if os.environ.get("MYSQL_HOST"):
        result["mysql"]["host"] = os.environ["MYSQL_HOST"]
    if os.environ.get("MYSQL_PORT") and os.environ["MYSQL_PORT"].isdigit():
        result["mysql"]["port"] = int(os.environ["MYSQL_PORT"])
    if os.environ.get("MYSQL_DATABASE"):
        result["mysql"]["database"] = os.environ["MYSQL_DATABASE"]
    if os.environ.get("MYSQL_USERNAME"):
        result["mysql"]["username"] = os.environ["MYSQL_USERNAME"]
    if os.environ.get("MYSQL_PASSWORD"):
        result["mysql"]["password"] = os.environ["MYSQL_PASSWORD"]

    return result


def get_web_credentials(filepath: Path | str | None = None) -> tuple[int, str, str]:
    cfg = parse_setting_file(filepath)
    web = cfg["web"]
    return int(web.get("port", 8120)), str(web.get("username", "admin")), str(web.get("password", "admin123456"))


def get_mysql_config(filepath: Path | str | None = None) -> Dict[str, Any]:
    cfg = parse_setting_file(filepath)
    return cfg["mysql"]
