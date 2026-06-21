"""중앙 설정: 공공데이터 API URL, 지역 격자좌표, 환경변수 로드.

모든 collector 가 여기서 URL/키를 가져온다. 키가 없으면 USE_MOCK 가 True 가 되어
collector 들이 mock 모드로 동작한다 (Graceful Degradation).
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECT_ROOT.parent

try:
    from dotenv import load_dotenv

    # aiagriculture 와 동일: repo 루트 .env 우선, 패키지 디렉터리 .env 보조
    load_dotenv(REPO_ROOT / ".env", override=False)
    load_dotenv(PROJECT_ROOT / ".env", override=False)
except Exception:  # python-dotenv 미설치여도 동작
    pass


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


# ---------------------------------------------------------------------------
# 인증키 (공공데이터포털 / 기상청 / Gemini)
# aiagriculture 호환: DATA_GO_KR_SERVICE_KEY, GOOGLE_API_KEY
# ---------------------------------------------------------------------------
DATA_GO_KR_KEY: str = _env("DATA_GO_KR_KEY", "DATA_GO_KR_SERVICE_KEY")
KMA_KEY: str = _env("KMA_KEY") or DATA_GO_KR_KEY
KOSIS_KEY: str = _env("KOSIS_KEY")
GEMINI_API_KEY: str = _env("GEMINI_API_KEY", "GOOGLE_API_KEY")

# 키가 하나도 없으면 전 구간 mock 으로 강제 (데모/오프라인 재현성)
USE_MOCK: bool = os.getenv("USE_MOCK", "").lower() in {"1", "true", "yes"} or not DATA_GO_KR_KEY

CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "300"))
HTTP_TIMEOUT: int = int(os.getenv("HTTP_TIMEOUT", "10"))


# ---------------------------------------------------------------------------
# 공공데이터 API endpoint
# ---------------------------------------------------------------------------
API = {
    # 전력거래소 — 시간별 전국 전력수요량 (odcloud, 15065266)
    # swagger: https://infuser.odcloud.kr/oas/docs?namespace=15065266/v1
    "kpx_hourly_demand": "https://api.odcloud.kr/api/15065266/v1/uddi:6ade08d2-0014-4d22-b10c-c811e3273c70",
    # 전력거래소 — 오늘전력수급현황조회
    "kpx_today_supply": "https://apis.data.go.kr/B552115/PowerSupplyStatusInfoService/getPowerSupplyStatusInfo",
    # 한국전력 — 지역별 용도별 전력사용량 (파일기반, 여기선 mock 위주)
    "kepco_region_usage": "https://bigdata.kepco.co.kr/openapi/v1/powerUsage/region.do",
    # 기상청 — 단기예보 조회서비스 2.0
    "kma_vilage_fcst": "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst",
    # 통계청 KOSIS — 통계자료 (GRDP / 주민등록인구)
    "kosis": "https://kosis.kr/openapi/Param/statisticsParameterData.do",
}


# ---------------------------------------------------------------------------
# 행정구역 → 기상청 격자좌표(nx, ny) + 대표 인구/GRDP 베이스라인(mock fallback용)
# 실데이터 연동 시 baseline 값은 KOSIS collector 가 덮어쓴다.
# ---------------------------------------------------------------------------
REGIONS: dict[str, dict] = {
    "서울특별시": {"nx": 60, "ny": 127, "pop_k": 9400, "grdp_trillion": 472, "base_demand_mwh": 9800},
    "부산광역시": {"nx": 98, "ny": 76, "pop_k": 3300, "grdp_trillion": 99, "base_demand_mwh": 3600},
    "인천광역시": {"nx": 55, "ny": 124, "pop_k": 3000, "grdp_trillion": 101, "base_demand_mwh": 5200},
    "대구광역시": {"nx": 89, "ny": 90, "pop_k": 2350, "grdp_trillion": 60, "base_demand_mwh": 2600},
    "대전광역시": {"nx": 67, "ny": 100, "pop_k": 1440, "grdp_trillion": 47, "base_demand_mwh": 1900},
    "광주광역시": {"nx": 58, "ny": 74, "pop_k": 1420, "grdp_trillion": 43, "base_demand_mwh": 1700},
    "울산광역시": {"nx": 102, "ny": 84, "pop_k": 1100, "grdp_trillion": 83, "base_demand_mwh": 4800},
    "경기도": {"nx": 60, "ny": 120, "pop_k": 13600, "grdp_trillion": 540, "base_demand_mwh": 18500},
    "강원특별자치도": {"nx": 92, "ny": 131, "pop_k": 1530, "grdp_trillion": 50, "base_demand_mwh": 2300},
    "충청북도": {"nx": 69, "ny": 107, "pop_k": 1590, "grdp_trillion": 77, "base_demand_mwh": 3100},
    "충청남도": {"nx": 68, "ny": 100, "pop_k": 2120, "grdp_trillion": 130, "base_demand_mwh": 6900},
    "전북특별자치도": {"nx": 63, "ny": 89, "pop_k": 1760, "grdp_trillion": 55, "base_demand_mwh": 2700},
    "전라남도": {"nx": 51, "ny": 67, "pop_k": 1820, "grdp_trillion": 90, "base_demand_mwh": 5400},
    "경상북도": {"nx": 89, "ny": 91, "pop_k": 2600, "grdp_trillion": 115, "base_demand_mwh": 6200},
    "경상남도": {"nx": 91, "ny": 77, "pop_k": 3270, "grdp_trillion": 122, "base_demand_mwh": 5800},
    "제주특별자치도": {"nx": 52, "ny": 38, "pop_k": 670, "grdp_trillion": 21, "base_demand_mwh": 1000},
    "세종특별자치시": {"nx": 66, "ny": 103, "pop_k": 390, "grdp_trillion": 14, "base_demand_mwh": 600},
}


def region_names() -> list[str]:
    return list(REGIONS.keys())
