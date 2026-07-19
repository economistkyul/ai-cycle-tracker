"""시그널 상태 영속화 — hysteresis가 실행 간에도 유지되게 한다.

기록: state, entered_at(상태 진입일), last_changed, reason(변경 원인)
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = ROOT / "data" / "state" / "signal_state.yaml"


def load_states(path: Path = STATE_FILE) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_states(states: dict, path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(states, f, allow_unicode=True, sort_keys=True)


def update_state(store: dict, key: str, new_state: str, reason: str,
                 today: date) -> dict:
    prev = store.get(key, {})
    if prev.get("state") != new_state:
        store[key] = {"state": new_state, "entered_at": str(today),
                      "last_changed": str(today), "reason": reason,
                      "prev_state": prev.get("state", "NONE")}
    else:
        prev["last_changed"] = str(today)
        store[key] = prev
    return store
