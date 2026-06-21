"""기상청 단기예보(VilageFcstInfoService_2.0) collector.

행정구역 → (nx, ny) 격자좌표로 일자별 기온/강수/습도를 집계한다.
전기수요의 1차 변수(냉난방 부하)를 만든다.
"""
from __future__ import annotations

import datetime as dt
import math

from ..config import settings
from .base import BaseCollector, cached_get


def _base_datetime(now: dt.datetime) -> tuple[str, str]:
    """단기예보 발표 시각(02,05,08,11,14,17,20,23)에 맞춰 base_date/base_time 산출."""
    slots = [2, 5, 8, 11, 14, 17, 20, 23]
    hour = now.hour
    chosen = max([s for s in slots if s <= hour], default=23)
    base_date = now.strftime("%Y%m%d")
    if hour < 2:  # 자정~02시는 전날 23시 발표 사용
        base_date = (now - dt.timedelta(days=1)).strftime("%Y%m%d")
        chosen = 23
    return base_date, f"{chosen:02d}00"


class WeatherCollector(BaseCollector):
    name = "weather"

    def fetch(self, region: str, days: int = 3, **_) -> dict:
        meta = settings.REGIONS[region]
        now = dt.datetime.now()
        base_date, base_time = _base_datetime(now)
        params = {
            "serviceKey": settings.KMA_KEY,
            "pageNo": 1,
            "numOfRows": 1000,
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": meta["nx"],
            "ny": meta["ny"],
        }
        raw = cached_get(settings.API["kma_vilage_fcst"], params)
        items = raw["response"]["body"]["items"]["item"]

        # 일자별 TMP(기온) / POP(강수확률) / REH(습도) 집계
        by_day: dict[str, dict[str, list[float]]] = {}
        for it in items:
            d = it["fcstDate"]
            cat = it["category"]
            if cat not in {"TMP", "POP", "REH"}:
                continue
            try:
                v = float(it["fcstValue"])
            except ValueError:
                continue
            by_day.setdefault(d, {}).setdefault(cat, []).append(v)

        records = []
        for d in sorted(by_day)[:days]:
            agg = by_day[d]
            records.append(
                {
                    "date": d,
                    "temp_avg": round(sum(agg.get("TMP", [0])) / max(len(agg.get("TMP", [1])), 1), 1),
                    "temp_max": max(agg.get("TMP", [0])),
                    "temp_min": min(agg.get("TMP", [0])),
                    "precip_prob": round(sum(agg.get("POP", [0])) / max(len(agg.get("POP", [1])), 1), 1),
                    "humidity": round(sum(agg.get("REH", [0])) / max(len(agg.get("REH", [1])), 1), 1),
                }
            )
        return {"region": region, "records": records}

    def mock(self, region: str, days: int = 3, **_) -> dict:
        # 위도 프록시(ny)로 기온 베이스 조정 — 결정론적
        meta = settings.REGIONS[region]
        seed = meta["ny"]
        today = dt.date.today()
        records = []
        for i in range(days):
            d = today + dt.timedelta(days=i)
            # 계절성: 연중일(day-of-year) 사인파 + 지역 보정
            doy = d.timetuple().tm_yday
            seasonal = 13 + 13 * math.sin(2 * math.pi * (doy - 110) / 365)
            temp = round(seasonal + (seed % 7) - 3 + i * 0.4, 1)
            records.append(
                {
                    "date": d.strftime("%Y%m%d"),
                    "temp_avg": temp,
                    "temp_max": round(temp + 4.5, 1),
                    "temp_min": round(temp - 4.0, 1),
                    "precip_prob": float((seed * (i + 3)) % 80),
                    "humidity": float(45 + (seed * (i + 1)) % 45),
                }
            )
        return {"region": region, "records": records}
