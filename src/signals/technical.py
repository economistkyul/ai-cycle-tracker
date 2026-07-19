"""기술적 분석 모듈 v3.

v3 수정:
- 다자산 평가 (지수 + 레버리지 ETF 개별)
- CSV 검증: 정렬/중복/신선도/수정주가 컬럼
- 200MA·기울기·이격도·최근 고점 대비 낙폭 실사용
- 레버리지 ETF 상태 → reduction/exit/reentry 룰 연결
- 재진입 일수 단일 출처: portfolio.yaml leveraged_etf_rules
  (moving_average.yaml의 asset_class_overrides 제거됨)
"""
from __future__ import annotations
import csv
from datetime import datetime, date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRICE_DIR = ROOT / "data" / "private" / "prices"


def load_prices(asset: str, price_dir: Path = PRICE_DIR,
                today: date | None = None) -> tuple[list[float], list[str]]:
    """가격 로드 + 검증. 반환: (closes, issues). 치명 결함 시 ([], issues)."""
    f = price_dir / f"{asset}.csv"
    issues = []
    if not f.exists():
        return [], [f"{asset}: 가격 파일 없음"]
    with open(f, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return [], [f"{asset}: 빈 파일"]
    if "adjusted" not in rows[0]:
        issues.append(f"{asset}: 수정주가 여부(adjusted) 컬럼 없음 — 미수정 가정")
    dates = [r["date"] for r in rows]
    if len(set(dates)) != len(dates):
        return [], [f"{asset}: 중복 날짜 존재 — 데이터 정제 필요"]
    if dates != sorted(dates):
        rows = sorted(rows, key=lambda r: r["date"])
        issues.append(f"{asset}: 날짜 역순 → 자동 정렬")
    if today:
        last = datetime.strptime(rows[-1]["date"], "%Y-%m-%d").date()
        if last > today:
            return [], [f"{asset}: 미래 가격 데이터 ({last}) — 사용 불가"]
        if (today - last).days > 7:
            issues.append(f"{asset}: 최종 가격 {last} — 노후 (7일 초과)")
            return [], issues
    return [float(r["close"]) for r in rows], issues


def sma(vals: list[float], n: int) -> float | None:
    return sum(vals[-n:]) / n if len(vals) >= n else None


def eval_technical(closes: list[float], cfg: dict, regime: str = "bull_regime",
                   break_confirm: int | None = None,
                   reentry_confirm: int | None = None) -> dict:
    w = cfg["windows"]
    if len(closes) < w["mid"] + 1:
        return {"state": "UNKNOWN", "reasons": ["가격 데이터 부족/부재"]}

    bc = break_confirm or int(cfg["confirm_days"][regime]["break_confirm"])
    rc = reentry_confirm or int(cfg["confirm_days"][regime]["reentry_confirm"])
    band = float(cfg.get("hysteresis_pct", 1.0))

    close = closes[-1]
    ma20, ma50 = sma(closes, w["short"]), sma(closes, w["mid"])
    ma200 = sma(closes, w["long"])
    disparity50 = (close / ma50 - 1) * 100
    high = max(closes[-252:]) if len(closes) >= 2 else close
    drawdown = (close / high - 1) * 100
    slope50 = ma50 - sma(closes[:-1], w["mid"])
    below200 = ma200 is not None and close < ma200

    below50 = [c < sma(closes[:i + 1], w["mid"]) * (1 - band / 100)
               for i, c in enumerate(closes) if i + 1 >= w["mid"]]
    consec_below = next((i for i, b in enumerate(reversed(below50)) if not b), len(below50))
    consec_above = next((i for i, b in enumerate(reversed(below50)) if b), len(below50))

    reasons = [f"종가 {close:.2f} | 50MA {ma50:.2f} (기울기 {slope50:+.2f}) | "
               f"이격 {disparity50:+.1f}% | 고점대비 {drawdown:+.1f}% | "
               f"50선 하회 {consec_below}일/기준 {bc}일"
               + (f" | 200MA 하회" if below200 else "")]

    if consec_below >= bc:
        state = "TREND_BREAK"
    elif consec_below >= 1:
        state = "TREND_WARNING"
    elif 0 < consec_above < rc and any(below50[-(rc + 2):]):
        state = "RECOVERY"
        reasons.append(f"회복 확인 {consec_above}/{rc}일 — 재진입 대기")
    elif disparity50 >= float(cfg.get("extended_disparity_pct", 10)):
        state = "EXTENDED"
    elif float(cfg.get("pullback_floor_pct", -3)) <= disparity50 < 0 and ma20 and close < ma20:
        state = "PULLBACK"
    else:
        state = "TREND_STRONG" if slope50 > 0 else "PULLBACK"
    return {"state": state, "disparity50_pct": round(disparity50, 2),
            "drawdown_from_high_pct": round(drawdown, 2),
            "below_200ma": bool(below200), "reasons": reasons}


def leveraged_action(ticker: str, tech_state: str, rules: dict) -> dict:
    """레버리지 ETF 상태 → 룰 연결. recommendation_only."""
    r = rules.get(ticker, {})
    if tech_state == "TREND_BREAK":
        action = f"EXIT: {r.get('exit_rule', '전량 정리')}"
    elif tech_state == "TREND_WARNING":
        action = f"REDUCE: {r.get('reduction_rule', '50% 축소')}"
    elif tech_state == "RECOVERY":
        action = f"REENTRY 대기: {r.get('reentry_rule', '')} " \
                 f"(cooldown {r.get('cooldown_period_days', '?')}일)"
    elif tech_state == "UNKNOWN":
        action = "판정 불가 — 가격 데이터 공급 필요"
    else:
        action = "유지"
    return {"ticker": ticker, "tech_state": tech_state, "action": action,
            "recommendation_only": True}


INDEX_ASSETS = ["KOSPI", "NDX", "SOX"]


def eval_all_assets(cfg: dict, leveraged_rules: dict, today: date) -> dict:
    """지수 + 레버리지 ETF 전 자산 평가."""
    out = {"indices": {}, "leveraged": {}, "issues": []}
    for a in INDEX_ASSETS:
        closes, iss = load_prices(a, today=today)
        out["issues"] += iss
        out["indices"][a] = eval_technical(closes, cfg) if closes else \
            {"state": "UNKNOWN", "reasons": iss or ["데이터 없음"]}
    for t, r in leveraged_rules.items():
        closes, iss = load_prices(t, today=today)
        out["issues"] += iss
        tech = eval_technical(closes, cfg,
                              break_confirm=r.get("break_confirm_days"),
                              reentry_confirm=r.get("reentry_confirm_days")) \
            if closes else {"state": "UNKNOWN", "reasons": ["데이터 없음"]}
        out["leveraged"][t] = {**leveraged_action(t, tech["state"], leveraged_rules),
                               "detail": tech}
    return out
