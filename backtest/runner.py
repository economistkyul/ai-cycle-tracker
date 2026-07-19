"""백테스트 러너 스캐폴드 — look-ahead bias 방지 구조.

핵심 원칙: 전략 함수에는 as_of 시점에 '이용 가능했던' 데이터만 전달한다.
(release_date <= as_of 필터. CPI 등 수정 지표는 초기 발표값 사용)
실데이터 미확보 상태 — 실행 시 명시적으로 실패한다. 가짜 결과 생성 금지.
"""
from __future__ import annotations
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

STRATEGIES = ["buy_and_hold", "rebalance", "ma50", "dual_trigger_v1",
              "egzion", "yardeni", "integrated_with_override"]


def available_asof(records: list[dict], as_of: str) -> list[dict]:
    """release_date 기준 시점 필터 — look-ahead 방지의 핵심."""
    return [r for r in records if r.get("release_date", r["observation_date"]) <= as_of]


def run():
    if not RAW.exists() or not any(RAW.iterdir()):
        raise SystemExit(
            "백테스트 불가: data/raw/ 에 이력 데이터가 없다.\n"
            "backtest/README.md의 데이터 확보 절차를 먼저 수행할 것. (합성 데이터 생성 금지)")


if __name__ == "__main__":
    run()
