# aielectricity — 행정구역별 일자별 전기수요 예측 에이전트

공공데이터를 실시간으로 수집하여 행정구역별·일자별 전기수요를 예측하고,
불확실성 하에서 최적 운영 전략을 제안하는 하이브리드 AI 에이전트입니다.

LangGraph + AutoGluon + Bayesian Expected Loss + Gemini 아키텍처를
전기수요 예측 도메인에 적용했습니다.

---

## 프로젝트 구조

```
aielectricity/                        ← 저장소 루트 (이 README 위치)
├── README.md
├── .env                              ← API 키 설정
├── .gitignore
├── decision_process.txt              ← 의사결정 프로세스 상세 문서
│
└── model/                            ← ★ 실행 기준 디렉터리 (cd 후 실행)
    ├── requirements.txt
    │
    ├── ai_elec/                      ← 메인 패키지
    │   ├── config/
    │   │   └── settings.py           # API URL, REGIONS, 환경변수
    │   ├── collectors/
    │   │   ├── base.py               # HTTP 클라이언트 + TTL 캐시 + fallback
    │   │   ├── power.py              # 전력거래소 collector
    │   │   ├── weather.py            # 기상청 collector
    │   │   └── industry.py           # 통계청 KOSIS collector
    │   ├── ml/
    │   │   └── predictor.py          # AutoGluon / 선형추세 예측
    │   ├── decision/
    │   │   └── bayesian.py           # Bayesian Expected Loss
    │   ├── agent/
    │   │   ├── graph.py              # LangGraph 파이프라인
    │   │   ├── nodes.py              # collect / predict / decision / strategy / report
    │   │   └── state.py              # ElecState TypedDict
    │   ├── cli/
    │   │   ├── main.py               # CLI 진입점
    │   │   ├── query_parser.py       # 자연어 쿼리 파서
    │   │   └── trend_analyzer.py     # 월별 추세 분석 + ASCII 차트
    │   ├── services/
    │   │   └── agent_service.py      # ElecAgentService
    │   ├── ui/
    │   │   └── dashboard.py          # Streamlit 대시보드 (3탭)
    │   ├── tests/                    # 개별 검증 모듈
    │   │   ├── test_e2e.py           # E2E 파이프라인 검증
    │   │   ├── test_api_verify.py    # 공공데이터 API 연동 검증
    │   │   └── test_predict_verify.py# 예측(predict) 파이프라인 검증
    │   └── api_info/
    │       └── .env.example
    │
    ├── test/                         ← ★ 검증 러너
    │   ├── run_all.py                # API + 예측 한 번에 실행
    │   ├── run_api_test.py           # API 연동 검증만 실행
    │   └── run_predict_test.py       # 예측 파이프라인 검증만 실행
    │
    └── predict_rnd/                  ← 예측 정확도 실험
        ├── data_generator.py         # 합성 시계열 데이터 생성
        ├── models.py                 # 단순선형추세 / 피처OLS / AutoGluon
        ├── backtest.py               # Rolling-origin 백테스트 엔진
        ├── run_experiment.py         # 실험 실행 스크립트
        └── results/                  # 백테스트 CSV 출력
```

> **실행 기준 디렉터리**: `model/`  
> 아래 모든 `pip`, `streamlit`, `python3 -m` 명령어는 이 디렉터리에서 실행합니다.

```bash
cd model
```

---

## 빠른 시작

```bash
# 1. 패키지 설치
cd model
pip install -r requirements.txt

# 2. API 키 설정 (없어도 mock 모드로 전체 동작)
# 저장소 루트 .env 또는 model/.env 에 키 입력
# (ai_elec/api_info/.env.example 참고)

# 3. 대시보드 실행
streamlit run ai_elec/ui/dashboard.py

# 4. CLI (자연어 쿼리)
python3 -m ai_elec.cli.main "대구지역 3개월간 수요추세 및 7월 수요예측을 조사해줘"
```

### 환경 변수

| 변수 | 설명 |
|---|---|
| `DATA_GO_KR_KEY` | 공공데이터포털 인증키 (전력거래소·기상청) |
| `KMA_KEY` | 기상청 인증키 (미입력 시 `DATA_GO_KR_KEY` 재사용) |
| `KOSIS_KEY` | 통계청 KOSIS 인증키 |
| `GEMINI_API_KEY` | Gemini API 키 (미입력 시 규칙기반 전략 fallback) |

---

## 실행 방법

### 대시보드 (Streamlit)

```bash
streamlit run ai_elec/ui/dashboard.py
```

탭 구성:
- **📊 지역 예측** — 지역·기간 선택 → 수요 예측 + 의사결정 + 전략
- **💬 자연어 조회** — 쿼리 입력 → 추세 + 예측 + Bayesian 결정
- **🔬 정확도 실험** — Rolling-origin 백테스트 → 모델별 정확도 비교

### CLI (자연어 쿼리)

```bash
# 자연어 쿼리
python3 -m ai_elec.cli.main "대구지역 3개월간 수요추세 및 7월 수요예측을 조사해줘"

# 옵션 직접 지정
python3 -m ai_elec.cli.main --region 대구광역시 --trend-months 3 --forecast-month 7

# 단기 예측
python3 -m ai_elec.cli.main --region 서울특별시 --forecast-days 14

# 지원 지역 목록
python3 -m ai_elec.cli.main --list-regions
```

---

## 검증 실행 가이드

### ⭐ 통합 검증 — API + 예측 한 번에 실행 (권장)

| 파일 | 실행 명령 | 범위 |
|---|---|---|
| `test/run_all.py` | `python3 -m test.run_all` | API + 예측 한 번에 |
| `test/run_api_test.py` | `python3 -m test.run_api_test` | API 연동 검증만 |
| `test/run_predict_test.py` | `python3 -m test.run_predict_test` | 예측 파이프라인 검증만 |

```bash
cd model

# API + 예측 한 번에 (API 검증 + 예측 검증 + 백테스트)
python3 -m test.run_all
python3 -m test.run_all --region 경기도 --horizon 5
python3 -m test.run_all --real           # 실제 API 수집 후 예측까지 검증
python3 -m test.run_all --skip-backtest  # 백테스트 섹션 생략(빠른 실행)

# API 연동 검증만
python3 -m test.run_api_test
python3 -m test.run_api_test --region 경기도 --days 5

# 예측 파이프라인 검증만
python3 -m test.run_predict_test
python3 -m test.run_predict_test --region 경기도 --horizon 5
python3 -m test.run_predict_test --real --skip-backtest
```

`run_all` 출력은 **PART A. API 연동 검증** → **PART B. 예측 파이프라인 검증** →
**종합 결과** 순으로 구성되며, `N/N 섹션 통과` 형태로 결과를 확인합니다.

분리 실행한 `run_api_test` / `run_predict_test` 도 각각 동일한 종합 요약을 출력합니다.
세부 검증 항목은 아래 ①②③ 을 참고하세요.

---

### ① 공공데이터 API 연동 검증

| 항목 | 내용 |
|---|---|
| **파일** | `ai_elec/tests/test_api_verify.py` |
| **목적** | 기상청·전력거래소·KOSIS API 응답 및 데이터 구조 정합성 확인 |

```bash
# 기본 실행 (서울특별시, 3일)
python3 -m ai_elec.tests.test_api_verify

# 지역·일수 지정
python3 -m ai_elec.tests.test_api_verify --region 대구광역시 --days 5
```

| # | 검증 항목 | 통과 기준 |
|---|---|---|
| 1 | 설정 점검 | API 키 존재 확인, `REGIONS` 17개 등록 |
| 2 | 전력거래소 API | HTTP 200, `history` 레코드 ≥ 1, `0 < region_share ≤ 1` |
| 3 | 기상청 API | HTTP 200, `records` 날짜 수 = 요청 일수, `-40 ≤ temp_avg ≤ 45℃` |
| 4 | 통계청 KOSIS | HTTP 200, `population_k > 0`, `grdp_trillion > 0` |
| 5 | 통합 검증 | 3개 collector 출력 → `predict_node` 입력 포맷 충족, 날짜 `YYYYMMDD` |

**결과 표시**: `[PASS]` 통과 · `[FAIL]` 실패 · `[SKIP]` API 키 미설정 (mock 구조 검증만)

---

### ② 예측 파이프라인 검증

| 항목 | 내용 |
|---|---|
| **파일** | `ai_elec/tests/test_predict_verify.py` |
| **목적** | `predictor` 모듈·`predict_node`·`predict_rnd` 백테스트 검증 |

```bash
# 기본 (mock 데이터)
python3 -m ai_elec.tests.test_predict_verify

# 지역·예측일수 지정
python3 -m ai_elec.tests.test_predict_verify --region 경기도 --horizon 5

# 실제 API 수집 후 예측 + 백테스트
python3 -m ai_elec.tests.test_predict_verify --real --backtest

# 전 지역 mock 스모크 테스트
python3 -m ai_elec.tests.test_predict_verify --all-regions
```

| # | 검증 항목 | 내용 |
|---|---|---|
| 1 | module | `Forecast` 구조, AutoGluon 설치 여부 |
| 2 | build_frame | 피처 테이블 생성 (dow, temp, grdp 등) |
| 3 | predict_mock | mock 수집 데이터로 `predict()` 실행 |
| 4 | predict_real | 실제 API 수집 후 예측 (`--real`) |
| 5 | predict_node | LangGraph `predict_node` 통합 |
| 6 | backtest | `predict_rnd` 합성 데이터 백테스트 (`--backtest`) |

---

### ③ 예측 정확도 실험 (predict_rnd)

| 항목 | 내용 |
|---|---|
| **파일** | `predict_rnd/run_experiment.py` |
| **목적** | 2025년 데이터로 학습 → 2026년 1~5월 월별 총수요 예측 정확도 측정 |
| **방법** | Rolling-origin 백테스트 (매 목표월 직전까지 학습, 해당 월 전체 예측) |

```bash
# 기본 실행 (대구광역시)
python3 -m predict_rnd.run_experiment

# 지역 변경
python3 -m predict_rnd.run_experiment --region 경기도

# 결과 CSV 저장 (predict_rnd/results/ 에 저장)
python3 -m predict_rnd.run_experiment --region 대구광역시 --save-csv
```

**실험 설계**

| 항목 | 내용 |
|---|---|
| 학습 기간 | 2025-01-01 ~ 목표월 직전 (rolling) |
| 검증 기간 | 2026년 1월 ~ 5월 (5개월) |
| 예측 단위 | 일별 수요 예측 후 월별 합산 |
| 기준일 | 2026-06-21 고정 (재현성 보장) |

**비교 모델**

| 모델 | 설명 | 필요 라이브러리 |
|---|---|---|
| 단순선형추세 | 시계열 인덱스 OLS + 기온·요일 보정 | 없음 (표준 라이브러리) |
| 피처OLS회귀 | 요일·계절·냉난방부하 등 10개 피처 기반 OLS | numpy |
| AutoGluon | TabularPredictor (medium_quality, 60초 제한) | autogluon.tabular |

**정확도 측정 기준** (월별 총수요 MWh 합계 단위)

| 지표 | 산출식 | 목표 |
|---|---|---|
| **정확도(%)** | `100 - MAPE` | **≥ 90%** |
| **MAPE(%)** | `\|예측합계 - 실제합계\| / 실제합계 × 100` | ≤ 10% |
| **일별 MAPE(%)** | 각 일자 오차율 평균 | 참고 지표 |
| **RMSE (MWh)** | 일별 잔차 제곱평균 제곱근 | 작을수록 좋음 |
| **R²** | 일별 결정계수 | 1에 가까울수록 좋음 |

**실측 결과 (대구광역시, 2026-06-21)**

| 모델 | 평균 정확도 | 평균 MAPE | 1월 | 2월 | 3월 | 4월 | 5월 |
|---|---|---|---|---|---|---|---|
| AutoGluon | **99.64%** | 0.36% | 99.58% | 99.81% | 99.82% | 99.52% | 99.46% |
| 피처OLS회귀 | **99.61%** | 0.39% | 99.76% | 99.65% | 99.41% | 99.91% | 99.32% |
| 단순선형추세 | 92.20% | 7.80% | 86.11% | 91.80% | 96.22% | 92.70% | 94.14% |

> 세 모델 모두 목표 정확도(90%) 달성.  
> AutoGluon과 피처OLS는 월 합계 오차 1% 미만으로 사실상 동등.

---

### ④ E2E 파이프라인 검증

```bash
python3 -m ai_elec.tests.test_e2e
```

서울·울산·제주 3개 시나리오로 `collect → predict → decision → strategy → report` 전체 파이프라인을 검증합니다.

---

## 공공데이터 API

| 변수 | API 서비스명 | 기관 |
|---|---|---|
| 전력수요(타깃) | 시간별 전국 전력수요량 (15065266) | 전력거래소 |
| 오늘수급 | 오늘전력수급현황조회 (15056879) | 전력거래소 |
| 날씨 | 단기예보 조회서비스 (VilageFcstInfoService_2.0) | 기상청 |
| 인구 | 주민등록인구 (KOSIS DT_1B04005N) | 통계청 |
| GRDP | 지역내총생산 (KOSIS) | 통계청 |

> API 키가 없거나 호출이 실패하면 각 collector가 결정론적 mock 데이터로 자동 전환합니다.  
> 오프라인 환경에서도 전체 파이프라인이 재현됩니다.

---

## 설계 원칙

1. **관심사 분리** — 수집 / 예측 / 결정 / 전략 / 리포트를 각각 독립 LangGraph 노드로 분리
2. **Graceful Degradation** — API·모델·LLM 중 하나가 실패해도 파이프라인 유지
3. **실시간 공공데이터 우선** — 별도 DW 없이 직접 호출 + TTL 300초 캐시
4. **불확실성 보존** — 예측 신뢰구간(95% CI)과 Bayesian 사후확률을 최종 결정까지 유지
