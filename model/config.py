"""model/ 실행 폴더 중앙 설정 — .env 환경변수 일괄 로드·관리.

모든 API 키·런타임 옵션은 이 파일에서만 정의한다.
ai_elec/config/settings.py 및 collector·agent 코드는 여기서 re-export 한다.

.env 탐색 순서 (앞이 우선, 뒤는 보조):
  1. 저장소 루트  ../.env
  2. model/       ./.env

사용:
    cd model
    import config
    config.DATA_GO_KR_KEY
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# 경로
# ---------------------------------------------------------------------------
MODEL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = MODEL_ROOT.parent

# ---------------------------------------------------------------------------
# .env 로드
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env", override=False)
    load_dotenv(MODEL_ROOT / ".env", override=False)
except Exception:  # python-dotenv 미설치여도 동작
    pass


def _env(*names: str, default: str = "") -> str:
    """여러 환경변수 이름 중 첫 번째 비어있지 않은 값을 반환."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value.strip()
    return default


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# 공공데이터 / API 인증키
# aiagriculture 호환 별칭: DATA_GO_KR_SERVICE_KEY, GOOGLE_API_KEY
# ---------------------------------------------------------------------------
DATA_GO_KR_KEY: str = _env("DATA_GO_KR_KEY", "DATA_GO_KR_SERVICE_KEY")
KMA_KEY: str = _env("KMA_KEY") or DATA_GO_KR_KEY
KOSIS_KEY: str = _env("KOSIS_KEY")

# ---------------------------------------------------------------------------
# Google / Gemini
# ---------------------------------------------------------------------------
GEMINI_API_KEY: str = _env("GEMINI_API_KEY", "GOOGLE_API_KEY")
GOOGLE_API_KEY: str = GEMINI_API_KEY  # 별칭
PMGO_VI_AUTH_TOKEN: str = _env("PMGO_VI_AUTH_TOKEN")
GOOGLE_SERVICE_ACCOUNT_KEY: str = _env("GOOGLE_SERVICE_ACCOUNT_KEY")

# ---------------------------------------------------------------------------
# 런타임 옵션
# ---------------------------------------------------------------------------
USE_MOCK: bool = _flag("USE_MOCK") or not DATA_GO_KR_KEY
CACHE_TTL_SECONDS: int = _int("CACHE_TTL_SECONDS", 300)
HTTP_TIMEOUT: int = _int("HTTP_TIMEOUT", 10)


def masked(value: str, visible: int = 4) -> str:
    """로그용 — 키 값 마스킹."""
    if not value:
        return "(미설정)"
    if len(value) <= visible * 2:
        return "*" * len(value)
    return f"{value[:visible]}...{value[-visible:]}"


def summary() -> dict[str, str]:
    """설정 요약 (민감값 마스킹)."""
    return {
        "DATA_GO_KR_KEY": masked(DATA_GO_KR_KEY),
        "KMA_KEY": masked(KMA_KEY),
        "KOSIS_KEY": masked(KOSIS_KEY),
        "GEMINI_API_KEY": masked(GEMINI_API_KEY),
        "PMGO_VI_AUTH_TOKEN": masked(PMGO_VI_AUTH_TOKEN),
        "GOOGLE_SERVICE_ACCOUNT_KEY": masked(GOOGLE_SERVICE_ACCOUNT_KEY),
        "USE_MOCK": str(USE_MOCK),
        "CACHE_TTL_SECONDS": str(CACHE_TTL_SECONDS),
        "HTTP_TIMEOUT": str(HTTP_TIMEOUT),
    }


__all__ = [
    "MODEL_ROOT",
    "REPO_ROOT",
    "DATA_GO_KR_KEY",
    "KMA_KEY",
    "KOSIS_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "PMGO_VI_AUTH_TOKEN",
    "GOOGLE_SERVICE_ACCOUNT_KEY",
    "USE_MOCK",
    "CACHE_TTL_SECONDS",
    "HTTP_TIMEOUT",
    "masked",
    "summary",
]
