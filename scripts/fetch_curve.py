"""
FRED에서 금리 커브를 매일 수집하고 트리거를 평가한다.

출력: data/curve.json
  { "updated": ISO8601, "history": [...], "latest": {...} }

필요 환경변수: FRED_API_KEY  (https://fred.stlouisfed.org/docs/api/api_key.html 에서 무료 발급)

의존성 없음 (표준 라이브러리만 사용).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

FRED = "https://api.stlouisfed.org/fred/series/observations"

# 시리즈: 내부 필드명 -> (FRED series_id, units)
SERIES = {
    "m3": ("DGS3MO", "lin"),      # 3개월물
    "y2": ("DGS2", "lin"),        # 2년물
    "y10": ("DGS10", "lin"),      # 10년물
    "y30": ("DGS30", "lin"),      # 30년물
    "ff_top": ("DFEDTARU", "lin"),  # 정책금리 목표범위 상단
    "core_cpi": ("CPILFESL", "pc1"),  # 코어 CPI 전년동월비 (월간)
    "usdkrw": ("DEXKOUS", "lin"),   # 원달러 (공표 지연 있음)
}

REQUIRED = ["m3", "y2", "y10", "y30", "ff_top"]
LOOKBACK_DAYS = 400

# --- 트리거 임계값 ---------------------------------------------------------
TH = {
    "level_y30_fired": 5.75,
    "level_y30_warn": 5.50,
    "level_y10_fired": 5.30,
    "level_y10_warn": 5.10,
    "front_fired_gap": 0.50,   # 2Y - 정책상단
    "late_stage_gap": 0.25,
    "dual_y10": 5.00,
    "dual_core_cpi": 3.00,
    "delta_window_days": 28,
    "delta_window_min": 21,
    "delta_window_max": 42,
}


# --- FRED ------------------------------------------------------------------
def fetch_series(series_id: str, units: str, api_key: str, start: str) -> dict[str, float]:
    q = urllib.parse.urlencode({
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "units": units,
        "observation_start": start,
    })
    req = urllib.request.Request(f"{FRED}?{q}", headers={"User-Agent": "ai-cycle-tracker"})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    out = {}
    for ob in payload.get("observations", []):
        v = ob.get("value", ".")
        if v not in (".", "", None):
            try:
                out[ob["date"]] = float(v)
            except ValueError:
                continue
    return out


def build_history(api_key: str) -> list[dict]:
    start = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    raw = {}
    for field, (sid, units) in SERIES.items():
        try:
            raw[field] = fetch_series(sid, units, api_key, start)
        except Exception as e:  # 개별 시리즈 실패가 전체를 막지 않도록
            print(f"warn: {sid} 수집 실패 ({e})", file=sys.stderr)
            raw[field] = {}

    # 국채금리 4종이 모두 있는 날짜만 관측일로 인정
    dates = sorted(set.intersection(*(set(raw[f]) for f in ["m3", "y2", "y10", "y30"])))
    if not dates:
        raise RuntimeError("국채금리 시리즈 교집합이 비어 있습니다. FRED 응답을 확인하세요.")

    history = []
    for d in dates:
        row = {"date": d}
        for f in ["m3", "y2", "y10", "y30"]:
            row[f] = raw[f][d]
        # 저빈도/지연 시리즈는 직전 관측치를 이월
        for f in ["ff_top", "core_cpi", "usdkrw"]:
            row[f] = carry_forward(raw[f], d)
        if row["ff_top"] is None:
            continue
        row["s210"] = round(row["y10"] - row["y2"], 4)
        row["s230"] = round(row["y30"] - row["y2"], 4)
        history.append(row)
    return history


def carry_forward(series: dict[str, float], on: str) -> float | None:
    keys = [k for k in series if k <= on]
    return series[max(keys)] if keys else None


# --- 평가 ------------------------------------------------------------------
def delta_4w(history: list[dict], idx: int) -> float | None:
    """idx 시점의 2s10s를 약 4주 전과 비교한 변화폭(%p)."""
    if idx < 1:
        return None
    ref = history[idx]
    ref_d = datetime.fromisoformat(ref["date"]).date()
    # 뒤에서부터 훑어 최소 창을 처음 만족하는 관측치가 가장 가까운 기준점이다.
    for j in range(idx - 1, -1, -1):
        gap = (ref_d - datetime.fromisoformat(history[j]["date"]).date()).days
        if gap >= TH["delta_window_min"]:
            if gap > TH["delta_window_max"]:
                return None  # 데이터 공백 — 비교 불가
            return round(ref["s210"] - history[j]["s210"], 4)
    return None


def evaluate(history: list[dict]) -> dict:
    if not history:
        raise RuntimeError("history가 비어 있습니다.")
    cur = history[-1]
    d_now = delta_4w(history, len(history) - 1)
    d_prev = delta_4w(history, len(history) - 2) if len(history) > 1 else None

    # A. 커브 반전
    if d_now is None:
        a = {"state": "unknown", "detail": "4주 전 데이터 부족"}
    elif d_now < 0 and d_prev is not None and d_prev < 0:
        a = {"state": "fired", "detail": "플래트닝 2회 연속"}
    elif d_now < 0:
        a = {"state": "warn", "detail": "플래트닝 1회"}
    else:
        a = {"state": "clear", "detail": "스티프닝 지속"}
    a["delta_4w_bp"] = None if d_now is None else round(d_now * 100)

    # B. 레벨 (1987년형)
    if cur["y30"] >= TH["level_y30_fired"] or cur["y10"] >= TH["level_y10_fired"]:
        b_state = "fired"
    elif cur["y30"] >= TH["level_y30_warn"] or cur["y10"] >= TH["level_y10_warn"]:
        b_state = "warn"
    else:
        b_state = "clear"
    b = {"state": b_state, "y30": cur["y30"], "y10": cur["y10"]}

    # C. 프론트엔드
    gap = round(cur["y2"] - cur["ff_top"], 4)
    if gap >= TH["front_fired_gap"]:
        c_state = "fired"
    elif gap > 0:
        c_state = "warn"
    else:
        c_state = "clear"
    c = {"state": c_state, "gap_bp": round(gap * 100)}

    # 듀얼 조건 (이은택)
    core = cur.get("core_cpi")
    dual = {
        "yield_ok": cur["y10"] >= TH["dual_y10"],
        "cpi_ok": core is not None and core >= TH["dual_core_cpi"],
        "core_cpi": core,
    }
    dual["fired"] = dual["yield_ok"] and dual["cpi_ok"]

    # 국면
    if a["state"] == "fired" or b["state"] == "fired":
        stage, stage_name = 3, "전환"
    elif gap >= 0:
        stage, stage_name = 2, "확장"
    else:
        stage, stage_name = 1, "점화"
    late = stage == 2 and gap >= TH["late_stage_gap"]

    # 실행 지시
    if stage == 3:
        action = "매도 시퀀스 개시: 로보틱스 전량 → 레버리지 ETF 전량 → 광통신 50% → 메모리 유지"
    elif dual["fired"]:
        action = "듀얼 조건 발화: 로보틱스 50% 축소, 3x 레버리지 전량 언레버리지 전환"
    elif late:
        action = "②후반 구성 교체: SOXL→SMH, TQQQ→QQQ, SGOV/BIL 현금 버퍼 확보"
    elif stage == 2:
        action = "보유. 3x 비중 상한 고정, 신규 증액 없음"
    else:
        action = "보유. 사전 정의 비중 유지"

    alert = stage == 3 or dual["fired"] or b["state"] == "fired" or a["state"] == "fired"

    return {
        "date": cur["date"],
        "stage": stage,
        "stage_name": stage_name,
        "late_stage": late,
        "yields": {k: cur[k] for k in ["m3", "y2", "y10", "y30", "ff_top"]},
        "spreads": {"s210_bp": round(cur["s210"] * 100), "s230_bp": round(cur["s230"] * 100)},
        "triggers": {"A_curve": a, "B_level": b, "C_front": c, "dual": dual},
        "usdkrw": cur.get("usdkrw"),
        "action": action,
        "alert": alert,
    }


def summarize(latest: dict) -> str:
    t = latest["triggers"]
    late = " 후반" if latest["late_stage"] else ""
    return (
        f"{latest['date']} · 국면 {latest['stage']}{late} ({latest['stage_name']})\n"
        f"2s10s {latest['spreads']['s210_bp']}bp (4주 {t['A_curve']['delta_4w_bp']}bp) · "
        f"30Y {latest['yields']['y30']}% · 2Y−정책 {t['C_front']['gap_bp']}bp\n"
        f"A {t['A_curve']['state']} / B {t['B_level']['state']} / C {t['C_front']['state']} / "
        f"듀얼 {'발화' if t['dual']['fired'] else '미발화'}\n"
        f"→ {latest['action']}"
    )


def main() -> int:
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        print("error: FRED_API_KEY가 설정되지 않았습니다.", file=sys.stderr)
        return 1

    history = build_history(api_key)
    latest = evaluate(history)

    out = Path(os.environ.get("CURVE_OUT", "data/curve.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"updated": datetime.utcnow().isoformat() + "Z", "history": history[-260:], "latest": latest},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    summary = summarize(latest)
    print(summary)

    # GitHub Actions로 상태 전달
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as fh:
            fh.write(f"alert={'true' if latest['alert'] else 'false'}\n")
            fh.write(f"stage={latest['stage']}\n")
            fh.write("summary<<EOF\n" + summary + "\nEOF\n")
    gh_sum = os.environ.get("GITHUB_STEP_SUMMARY")
    if gh_sum:
        with open(gh_sum, "a", encoding="utf-8") as fh:
            fh.write("```\n" + summary + "\n```\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
