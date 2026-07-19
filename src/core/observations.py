"""날짜별 관측 이력 로딩 + 검증 + 확인단위 분리.

원칙 F: 누락/노후/무효 데이터 → UNKNOWN (CLEAR 금지)
v3: 미래 날짜 무효, 미발표(release_date>today) 제외,
    확인 카운트는 스냅샷 수가 아닌 고유 observation/release 수.
"""
from __future__ import annotations
from datetime import date, datetime
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
OBS_DIR = ROOT / "data" / "observations"


def _d(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return datetime.strptime(str(v), "%Y-%m-%d").date()
    except ValueError:
        return None


def load_history(obs_dir: Path = OBS_DIR) -> list[dict]:
    snaps = []
    for d in sorted(p for p in obs_dir.iterdir() if p.is_dir()):
        f = d / "observations.yaml"
        if f.exists():
            with open(f, encoding="utf-8") as fh:
                snaps.append(yaml.safe_load(fh))
    return snaps


def validate_entry(entry: dict, today: date) -> tuple[bool, str]:
    """메타데이터 누락·미래 날짜 검증."""
    obs = _d(entry.get("observation_date"))
    if obs is None:
        return False, "observation_date 누락/형식오류"
    if entry.get("stale_after_days") is None:
        return False, "stale_after_days 누락"
    if obs > today:
        return False, f"미래 관측일 {obs}"
    rel = _d(entry.get("release_date"))
    if rel and rel > today:
        return False, f"미발표 데이터 (release {rel})"
    fetched = _d(entry.get("fetched_at"))
    if fetched and fetched > today:
        return False, f"미래 수집일 {fetched}"
    return True, ""


def is_fresh(entry: dict, today: date) -> bool:
    ok, _ = validate_entry(entry, today)
    if not ok:
        return False
    return (today - _d(entry["observation_date"])).days <= int(entry["stale_after_days"])


def series(history: list[dict], metric: str) -> list[dict]:
    out = []
    for snap in history:
        m = snap.get("metrics", {}).get(metric)
        if m is not None:
            out.append({"as_of": snap.get("as_of"), **m})
    return out


def confirm_series(history: list[dict], metric: str, confirm_unit: str,
                   today: date) -> list[dict]:
    """확인 카운트용 시계열: 유효 항목만, 확인단위 키로 중복 제거.

    confirm_unit='trading_day' → 고유 observation_date 1건씩
    confirm_unit='release'     → 고유 release_date 1건씩 (월간 CPI가 주간 스냅샷에
                                 복사돼도 발표 1회로만 계산)
    스냅샷 주기 ≠ 관측 주기 혼동 방지의 핵심.
    """
    key = "release_date" if confirm_unit == "release" else "observation_date"
    seen, out = {}, []
    for e in series(history, metric):
        ok, _ = validate_entry(e, today)
        if not ok:
            continue
        k = str(e.get(key) or e.get("observation_date"))
        seen[k] = e                      # 같은 키는 최신 스냅샷으로 갱신 (수정치 반영)
    for k in sorted(seen):               # 시간 오름차순 (역순 데이터 정렬)
        out.append(seen[k])
    return out


def latest_fresh(history: list[dict], metric: str, today: date):
    s = series(history, metric)
    if not s:
        return None
    last = s[-1]
    return last if is_fresh(last, today) else None
