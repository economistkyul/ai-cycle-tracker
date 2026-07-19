# 감사 기록 (v1 → v2 → v3)

## 1. v1 감사에서 발견된 결함 (스펙 §6 전수 검사)

| # | v1 결함 | v2 조치 | 검증 |
|---|---|---|---|
| 1 | `trend_entry`가 단순 `>=` 비교로 축약 | `confirm_obs` 연속 관측 확인 구현 | test_fire_needs_consecutive |
| 2 | trigger_zone 상단(5.3) 미사용 | `severity_threshold`로 사용 (심화 판정) | SignalEval.severity |
| 3 | hysteresis 부재 — 하루 등락에 상태 반전 | `clear_threshold` + `clear_confirm_obs` | test_hysteresis_keeps_fired |
| 4 | 보조지표(secondary) 설정이 코드 미사용 | rate_velocity 구현, 나머지는 입력 슬롯 명시 | rate_velocity_flag |
| 5 | sell_sequence가 실행계획 미연결 | 목표 축소율·기한·확인조건·현금목표 추가 | test_all_sell_buckets_mapped |
| 6 | portfolio.yaml이 위험 계산 미사용 | src/portfolio/risk.py가 소비 | test_risk.py |
| 7 | latest.yaml 덮어쓰기 → 이력 소실 | 날짜별 디렉토리 + pointer | data/observations/YYYY-MM-DD/ |
| 8 | 신선도/관측일 검사 부재 | stale_after_days → UNKNOWN | test_stale_returns_unknown |
| 9 | 계좌 A 비중 합 95% (5% 미분류) — 검증 없어 미발견 | unallocated 5% 명시 + 합계 검증 | test_weight_sums_100 |
| 10 | A·B 중복 노출 미합산 | combined_exposure + overlap 검출 | test_overlap_detected (7종목 중복 확인) |
| 11 | 3x ETF 명목 비중만 표시 | 레버리지/베타 조정 노출 (명목 100% → 실효 139%) | test_effective_exceeds_nominal |
| 12 | 버킷↔매도버킷 매핑 불완전 | 전 버킷 매핑 + 테스트 강제 | test_all_sell_buckets_mapped |
| 13 | KRW stage 수기 입력, 검증 없음 | 구성 지표 유도 규칙 정의, 수기는 override + 모순 경고 | triggers.yaml:krw_signal.derivation |
| 14 | 최종 판단이 사실상 단일 상태 | 6축 독립 평가 + 원인 설명 출력 | test_engine.py |

## 2. 이그전/야데니 프레임 대비 현재 구현 수준

구현 수준 표기 기준(v3에서 정정): **실행경로 연결** > **판정 함수 구현** > **스키마 정의** > **미구현**.
v2 감사 문서는 '판정 함수 구현'을 '완전 구현'으로 과장 표기했음 — 아래는 정정본.

| 프레임 요소 | 구현 상태 (v3 기준) |
|---|---|
| 듀얼 매크로 트리거 | ✅ 실행경로 연결 — 확인단위(trading_day/release) 분리, hysteresis 영속화, 날짜 검증 |
| 6축 엔진 + 원칙 A~F | ✅ 실행경로 연결 — 단 3축은 입력이 schema_only |
| 50일선 다자산 모듈 | 🟡 판정 함수 구현 + CSV 검증 — 가격 데이터 미연결 (공급 시 즉시 작동) |
| emergency override | ✅ 실행경로 연결 — 관측→입력 자동 연결, 삼중상태 (현재 UNKNOWN: fEPS/HY 미관측) |
| structural_regime | ✅ 값 기반 판정 + min_inputs 실사용 — 현재 입력 2/3로 UNKNOWN (정직한 판정) |
| KRW stage | ✅ 자동 유도 + 수기 모순 경고 |
| 매도 계획 (planner) | ✅ 실행경로 연결 — 상태→감축률/기한/현금목표, recommendation_only |
| earnings/valuation/semi_cycle | 🔴 스키마 정의 (schema_only) — 데이터 미연결 |
| NERI/NRRI | 🔴 미구현 (proxy 공식 확보 전 구현 금지) |
| 야데니 시나리오 확률 | 🔴 스키마 정의 |
| 백테스트 | 🔴 데이터 미확보로 실행 불가 — look-ahead 방지 러너만 준비 |

## v2 → v3 수정 기록 (외부 감사 지적 10건)

| # | 지적 | 조치 | 검증 테스트 |
|---|---|---|---|
| 1 | confirm_obs가 스냅샷 수 카운트 | confirm_series: 고유 observation/release 카운트, 단위 분리 | T1_CpiDedup |
| 2 | 상태 비영속 — hysteresis가 실행 간 소실 | data/state/signal_state.yaml (진입일·변경일·원인) | T2 + state_store |
| 3 | 미래/미발표/누락 메타데이터 미검증 | validate_entry + release_date 필터 | T4_FutureDates |
| 4 | structural이 값이 아닌 존재 평가 | 방향 채점 + 하드 베어 룰 + min_inputs 실사용 | T3_StructuralNotBull |
| 5 | override 입력 하드코딩 {} | 관측·기술평가 자동 연결, FIRED/NOT_FIRED/UNKNOWN | T5_EmergencyTriState |
| 6 | KOSPI 단일 + CSV 무검증 | 다자산(지수3+레버리지4), 정렬/중복/신선도/미래 검증, 200MA·기울기·낙폭 | T8, T9 |
| 7 | sell_sequence 미연결 | execution/planner.py — 우선순위 명문화(100% > 50%) | T6_SellPlanner |
| 8 | example 계좌값 무단 사용 | (values, is_demo) + DEMO DATA 표시, 팩터 명목/실효 이중, 국가·통화 | T7 + 대시보드 출력 |
| 9 | 프레임 구현 과장 표기 | 본 문서 표기 정정 + schema_only 태그를 코드 출력에 반영 | dashboard 출력 |
| 10 | 재진입 일수 이중 정의 충돌 | moving_average.yaml overrides 삭제 — leveraged_etf_rules 단일 출처 | test_config |

## v3에서 잡힌 오판 재현 3건
1. 동일 CPI 발표(3.1%)가 주간 스냅샷 2개에 복사 → v2 FIRED / v3 ARMED (발표 1회 카운트)
2. 원화 약세+외인 순매도 → v2 BULL_WITH_LATE_CYCLE_RISK / v3 STRUCTURAL_BEAR + KRW stage 3
3. release_date가 미래인 CPI 3.5% → v2 FIRED 가능 / v3 유효 0건 제외

## 3. Provisional 임계값 및 민감도 (백테스트로 확정 필요)

| 파라미터 | 현재값 | 민감도 방향 |
|---|---|---|
| us10y.confirm_obs | 3 | ↓1이면 조기 매도 증가 / ↑5면 신호 지연 위험 |
| us10y.clear_threshold | 4.70 | 좁으면(4.9) 재진입 잦음, 넓으면(4.5) 현금 체류 길어짐 |
| core_cpi.confirm_obs | 2 | 월간 지표 — 1이면 단월 노이즈에 발화 |
| fast_rise_bp | 40bp/4관측 | 낮추면 2022형 속도 충격 조기 포착, 오탐 증가 |
| emergency: fEPS -5% / HY +150bp | 잠정 | 2008·2020 구간 백테스트로 조정 필수 |
| 스트레스 쇼크 -5/-12/-25% | 잠정 | 실측 분포로 대체 예정 |

## 4. 남은 데이터 제약
1. fwd EPS·수정률·마진 — 유료/수기 소싱 필요 (proxy 사용 시 공식 명시, "공식 NERI" 표기 금지)
2. 가격 이력 — data/private/prices/*.csv 로컬 공급 (레포에 커밋하지 않음)
3. 이그전 원문 — 접근 불가 시 텔레그램 미러/KB 리서치로 대체, confidence 하향 표기
