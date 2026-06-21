# 공공데이터 API 승인/연동 정보

| # | 데이터셋 | 제공기관 | 공공데이터포털 ID | 용도 | 비고 |
|---|---|---|---|---|---|
| 1 | 시간별 전국 전력수요량 | 한국전력거래소 | 15065266 | 타깃(수요) 과거 시계열 | 파일→OpenAPI 자동변환, MWh |
| 2 | 오늘전력수급현황조회 | 한국전력거래소 | 15056879 | 실시간 현재/최대예측수요 | MW, 가이드 v1.6 |
| 3 | 지역별 용도별 전력사용량 | 한국전력공사 | 15031941 | 행정구역×산업분류 소비 | 2006.1~ , 파일형 |
| 4 | 단기예보 조회서비스 2.0 | 기상청 | VilageFcstInfoService_2.0 | 날씨(기온/강수/습도) | 격자 nx,ny, 일8회 |
| 5 | 지역소득(GRDP)/주민등록인구 | 통계청 KOSIS | (표ID별) | 산업규모·인구 slow feature | KOSIS Open API |

## 승인 절차 요약
1. 공공데이터포털(data.go.kr) 로그인 → 각 API "활용신청".
   - 기상청 단기예보: 자동승인(즉시), 운영계정 일 10만 콜.
   - 한전/전력거래소: 승인까지 최대 1일 소요 가능.
2. 발급된 **일반 인증키(decoding)** 를 `.env` 의 `DATA_GO_KR_KEY` 에 입력.
3. KOSIS 는 별도 [kosis.kr](https://kosis.kr) Open API 키 발급 → `KOSIS_KEY`.
4. Gemini 는 Google AI Studio 키 → `GEMINI_API_KEY` (선택).

## 좌표 변환
기상청 격자(nx, ny)는 위경도→격자 변환식(LCC)으로 산출. 본 프로젝트는
`config/settings.py:REGIONS` 에 시·도 대표 격자를 사전 매핑해 두었다.
시·군·구 단위 확장 시 KMA 격자 변환표를 추가하면 된다.

## Fallback 정책
키 미입력 또는 호출 실패 시 각 collector 는 결정론적 mock 으로 자동 전환되어
데모/오프라인에서도 동일 결과가 재현된다 (`base.BaseCollector.collect`).
