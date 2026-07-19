# AI Cycle Tracker

AI 인프라 사이클을 끝까지 타고, 시그널 기반으로 내리기 위한 개인 투자전략 트래킹 시스템.

> **Disclaimer**: 이 레포는 개인의 투자 프레임워크를 기록·추적하기 위한 것으로, 투자 권유가 아닙니다.
> 실제 계좌 금액·수량 데이터는 포함하지 않으며, 비중(%)과 룰만 공개합니다.
> 계좌 식별자·실명 등 개인정보는 어떤 파일에도 기록하지 않습니다 — [보안 정책](docs/SECURITY.md)

---

## 핵심 전략

**목표**: AI 버블 사이클의 멜트업 구간을 최대한 포착하되, 사전 정의된 시그널이 발화하면
감정 개입 없이 시퀀싱된 매도를 실행한다. 조기 이탈도, 붕괴 후 이탈도 아닌 **룰 기반 이탈**.

**분석 스캐폴딩**:
- 1999년 닷컴 버블 아날로그 (버블 국면 전환 이론: 실적 장세 → P/E 확장 장세)
- 과잉완화 테제 + Roaring 2020s / BRAIN revolution
- 원화 안정화 → 외국인 리플렉시브 루프 (독자 테제)

## 대시보드 상태: `ARMED, NOT FIRED`

| 시그널 | 트리거 | 현재 | 상태 |
|---|---|---|---|
| 미 10Y 금리 | 5.0~5.3% 추세 진입 | ~4.45% | 🟢 미발화 |
| Core CPI | 3.0% 상회 | ~2.9% | 🟡 임계 근접 |
| 원화 시그널 | 3단계 (하단 참조) | 1단계 (안정화) | 🟢 강세 신호 |
| Fed 정책 편향 | 인상 편향 전환 | Warsh Fed 인상 편향 | 🟡 모니터링 |

**듀얼 컨디션 필터**: 금리 상승 단독으로는 트리거가 아니다.
비가역적·인플레이션 주도형 금리 상승(10Y 5.0%+ **AND** core CPI 3%+)만이 진짜 트리거.

**원화 3단계 시그널**:
1. 원화 안정화 시작 → 버블 진입/지속 신호
2. 원화 강세 + 이익수정비율 둔화 → 후기 경고
3. 원화 반전 + 외국인 순매도 → 이탈 가속 (한국 포지션은 미국 트리거보다 먼저 발화 가능)

## 매도 시퀀싱

| 순서 | 버킷 | 논리 |
|---|---|---|
| 1st | 로봇 / 펀딩 의존 고멀티플 | 유동성 민감도 최고 |
| 2nd | 광통신 | 닷컴 아날로그: 마지막에 정점, 가장 폭력적 하락 (90%+) |
| Last | 메모리 / 반도체 | 실적 장세 주도, 최후 보유 |
| **룰 우선** | 3x 레버리지 ETF | 시그널 확인을 기다리지 않는다. 변동성 잠식 + 폭락 증폭 → 사전 설정 룰로 선제 이탈 |

## 레포 구조

```
ai-cycle-tracker/
├── config/
│   ├── triggers.yaml        # 붕괴 트리거 정의 (선언적)
│   ├── portfolio.yaml       # 포트폴리오 구조 — 비중(%)만, 금액 없음
│   └── sell_sequence.yaml   # 매도 시퀀싱 룰
├── data/
│   ├── observations/        # 주간 시그널 관측값 (수기 → 추후 자동화)
│   ├── templates/           # 프라이빗 데이터 입력 템플릿
│   └── private/             # 실계좌 데이터 (gitignored, 로컬 전용)
├── src/
│   ├── signals/dashboard.py # 시그널 판정 엔진
│   └── report/              # 주간/월말 리포트 생성 (Phase 3)
└── .github/workflows/       # 토요일 09:00 KST 자동 체크 (Phase 2)
```

## v2 아키텍처 (통합 의사결정 엔진)

단일 boolean 판단 금지 — 6축 독립 평가 후 원인과 함께 최종 상태를 출력한다.
**모든 출력은 recommendation_only이며 자동 주문 기능은 존재하지 않는다.**

```
관측 이력 (data/observations/YYYY-MM-DD/)
   ├→ macro_financial_stress   (연속확인·hysteresis·속도·듀얼컨디션)
   ├→ technical_regime         (50일선 모듈 — 확인기간·재진입·이격도)
   ├→ structural_regime        (3저 프레임 — 입력 유도)
   ├→ earnings_regime          (fwd EPS·NERI proxy — 데이터 대기)
   ├→ valuation_regime         (데이터 대기)
   └→ ai_semiconductor_cycle   (마진·재고·수주 — 데이터 대기)
        ↓
   engine.decide() → RISK_ON / RISK_ON_EXTENDED / HOLD_WITH_HEDGE /
                     REDUCE_LEVERAGE / DEFENSIVE / EXITING / UNKNOWN
        + emergency override (금리 하락형 붕괴)
        + 데이터 누락 → UNKNOWN (CLEAR 반환 금지)
```

포트폴리오 위험: 계좌 A+B 합산, 레버리지/베타 조정 실효 노출, 팩터 노출,
계좌 간 중복 종목, 스트레스 손실. → `src/portfolio/risk.py`

감사 결과와 전후 비교: [docs/AUDIT.md](docs/AUDIT.md)

## 로드맵

- [x] **Phase 1** — 룰의 코드화
- [x] **Phase 2a** — 6축 엔진·hysteresis·이력 데이터모델·합산 위험·테스트 22종 (v2)
- [ ] **Phase 2b** — 데이터 파이프라인 (fwd EPS, 가격, NERI proxy) + Actions 자동화
- [ ] **Phase 3** — 주간 보고서 자동 생성 (14섹션 + 출처 태그, src/report/weekly_template.md)
- [ ] **Phase 4** — 백테스트 (현재 불가 — backtest/README.md 사유 참조)

## 사용법 (Phase 1)

```bash
# 최초 1회: 개인정보 커밋 차단 훅 설치
ln -sf ../../scripts/check_secrets.sh .git/hooks/pre-commit

# 시그널 대시보드 판정 (6축 + 합산 위험)
python src/signals/dashboard.py

# 새 관측 추가: 날짜 디렉토리 생성 (기존 이력 보존)
mkdir data/observations/2026-07-25
cp data/observations/2026-07-17/observations.yaml data/observations/2026-07-25/
# 값 수정 후 data/latest/pointer.yaml 갱신

# 테스트
python -m unittest discover tests
```

## 원칙

1. **반대논리 필수**: 모든 리포트에 동등한 깊이의 베어 논거 1~2페이지 포함
2. **트리거 품질 > 트리거 발생**: 양성 금리 상승과 악성 금리 상승을 구분
3. **레버리지는 룰, 현물은 시그널**
4. **시점 프레임**: H1 공격, 가을 방어(sticky inflation), Q4 재진입
5. **계좌 분리 없음**: 모든 계좌가 동일 대시보드를 따른다
