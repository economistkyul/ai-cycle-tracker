# 백테스트 — 현재 상태: 실행 불가 (데이터 미확보)

## 실행 불가 사유
이 개발 환경은 외부 네트워크가 차단되어 가격/EPS 이력 데이터를 내려받을 수 없다.
가짜 데이터로 백테스트를 돌려 수치를 제시하는 것은 스펙의 날조 금지 원칙 위반이므로 하지 않는다.

## 준비된 것
- `runner.py`: 전략 인터페이스 + look-ahead 방지 구조 (as-of 데이터만 전략에 공급)
- 비교 대상 7전략 슬롯: buy_and_hold / rebalance / ma50 / dual_trigger_v1 / egzion / yardeni / integrated
- 필수 검증 구간: 2000 붕괴, 2008, 2020, 2022, 금리하락형 하락장, 금리상승+이익장세, 반도체 사이클 고저점

## 데이터 확보 후 절차
1. data/raw/ 에 일별 가격, 월별 CPI(초기발표값), 주별 fwd EPS 적재 (release_date 필수)
2. parameter sensitivity: confirm_obs ∈ {1,2,3,5}, clear_threshold ∈ {4.5,4.7,4.9} 그리드
3. walk-forward: 5년 학습 / 1년 검증 롤링
