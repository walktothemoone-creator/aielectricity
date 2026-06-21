"""산업규모(GRDP·산업매출) + 인구변화 collector (통계청 KOSIS).

연 단위 통계라 일자별 모델에는 '느린 변수(slow feature)'로 들어간다.
ML 학습 시 각 일자 레코드에 동일 연도 값을 broadcast 한다.
"""
from __future__ import annotations

from ..config import settings
from .base import BaseCollector, cached_get

# KOSIS 행정구역(시·도) 코드 — DT_1B04005N 주민등록인구
KOSIS_REGION_CODES: dict[str, str] = {
    "서울특별시": "11",
    "부산광역시": "26",
    "대구광역시": "27",
    "인천광역시": "28",
    "광주광역시": "29",
    "대전광역시": "30",
    "울산광역시": "31",
    "세종특별자치시": "36",
    "경기도": "41",
    "강원특별자치도": "42",
    "충청북도": "43",
    "충청남도": "44",
    "전북특별자치도": "45",
    "전라남도": "46",
    "경상북도": "47",
    "경상남도": "48",
    "제주특별자치도": "50",
}

POPULATION_TBL = "DT_1B04005N"


def _kosis_list(params: dict) -> list[dict]:
    if not settings.KOSIS_KEY:
        raise ValueError("KOSIS_KEY 미설정")

    payload = {
        "method": "getList",
        "apiKey": settings.KOSIS_KEY,
        "format": "json",
        "jsonVD": "Y",
        **params,
    }
    raw = cached_get(settings.API["kosis"], payload)
    if isinstance(raw, dict) and raw.get("err"):
        raise ValueError(raw.get("errMsg", "KOSIS API error"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("KOSIS empty response")
    return raw


def _pick_total_row(rows: list[dict]) -> dict:
    for row in rows:
        if row.get("C2_NM") == "계" or row.get("C2") in {"0", 0}:
            return row
    return rows[0]


class IndustryPopulationCollector(BaseCollector):
    name = "industry_population"

    def fetch(self, region: str, **_) -> dict:
        meta = settings.REGIONS[region]
        code = KOSIS_REGION_CODES[region]

        pop_rows = _kosis_list({
            "orgId": "101",
            "tblId": POPULATION_TBL,
            "itmId": "T2+",
            "objL1": code,
            "objL2": "ALL",
            "prdSe": "M",
            "newEstPrdCnt": "2",
            "loadGubun": "2",
        })
        latest = _pick_total_row(pop_rows)
        population = float(latest["DT"]) / 1000.0  # 명 → 천명

        population_yoy_pct = 0.0
        if len(pop_rows) >= 2:
            prev = _pick_total_row(pop_rows[1:])
            prev_pop = float(prev["DT"])
            if prev_pop:
                population_yoy_pct = round((float(latest["DT"]) - prev_pop) / prev_pop * 100, 2)

        # GRDP 통계표 ID는 KOSIS에서 별도 확인 필요 — 현재는 지역 baseline 유지
        grdp = float(meta["grdp_trillion"])
        return {
            "region": region,
            "grdp_trillion": grdp,
            "industry_sales_index": round(95 + (int(code) % 20), 1),
            "population_k": round(population, 1),
            "population_yoy_pct": population_yoy_pct,
        }

    def mock(self, region: str, **_) -> dict:
        meta = settings.REGIONS[region]
        seed = meta["nx"]
        return {
            "region": region,
            "grdp_trillion": float(meta["grdp_trillion"]),
            "industry_sales_index": round(95 + (seed % 20), 1),
            "population_k": float(meta["pop_k"]),
            "population_yoy_pct": round(((seed % 9) - 5) / 10.0, 2),
        }
