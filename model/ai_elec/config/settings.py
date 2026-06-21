"""도메인 설정: API URL, 행정구역 격자좌표.

환경변수·API 키는 model/config.py 에서 일괄 관리한다.
collector·agent 코드는 `from ..config import settings` 로 접근한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

# model/config.py import 경로 보장
_MODEL_ROOT = Path(__file__).resolve().parents[2]
if str(_MODEL_ROOT) not in sys.path:
    sys.path.insert(0, str(_MODEL_ROOT))

from config import (  # noqa: E402
    CACHE_TTL_SECONDS,
    DATA_GO_KR_KEY,
    GEMINI_API_KEY,
    GOOGLE_API_KEY,
    GOOGLE_SERVICE_ACCOUNT_KEY,
    HTTP_TIMEOUT,
    KMA_KEY,
    KOSIS_KEY,
    MODEL_ROOT,
    PMGO_VI_AUTH_TOKEN,
    REPO_ROOT,
    USE_MOCK,
)

# 하위 호환: PROJECT_ROOT = model/
PROJECT_ROOT = MODEL_ROOT

# ---------------------------------------------------------------------------
# 공공데이터 API endpoint
# ---------------------------------------------------------------------------
API = {
    # 전력거래소 — 시간별 전국 전력수요량 (odcloud, 15065266)
    "kpx_hourly_demand": "https://api.odcloud.kr/api/15065266/v1/uddi:6ade08d2-0014-4d22-b10c-c811e3273c70",
    # 전력거래소 — 오늘전력수급현황조회
    "kpx_today_supply": "https://apis.data.go.kr/B552115/PowerSupplyStatusInfoService/getPowerSupplyStatusInfo",
    # 한국전력 — 지역별 용도별 전력사용량
    "kepco_region_usage": "https://bigdata.kepco.co.kr/openapi/v1/powerUsage/region.do",
    # 기상청 — 단기예보 조회서비스 2.0
    "kma_vilage_fcst": "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst",
    # 통계청 KOSIS
    "kosis": "https://kosis.kr/openapi/Param/statisticsParameterData.do",
}


# ---------------------------------------------------------------------------
# 행정구역 → 기상청 격자좌표(nx, ny) + baseline(mock fallback용)
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
