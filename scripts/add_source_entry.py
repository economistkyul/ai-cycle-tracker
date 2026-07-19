#!/usr/bin/env python3
"""source_registry entries 수기 입력 워크플로.

사용: python scripts/add_source_entry.py
Narrative(저자 해석) / Observable Evidence(검증가능 데이터) / Actionable Signal(사전정의 조건)
3층을 분리 입력. 원문 미확보 시 confidence=low + basis='summary_only'.
"""
import sys
from datetime import date
from pathlib import Path
import yaml

REG = Path(__file__).resolve().parents[1] / "data" / "sources" / "source_registry.yaml"

FIELDS = [("source", "출처 (egzion/yardeni/기타)"), ("title", "제목"),
          ("source_date", "게시일 YYYY-MM-DD"), ("url", "URL"),
          ("layer", "층 (narrative/evidence/signal)"),
          ("key_claims", "핵심 주장 (;로 구분)"),
          ("confidence", "확신도 (high/normal/low)"),
          ("basis", "근거 (original/summary_only)")]


def main():
    entry = {}
    for k, prompt in FIELDS:
        v = input(f"{prompt}: ").strip()
        entry[k] = v.split(";") if k == "key_claims" else v
    entry["fetched_at"] = str(date.today())
    if entry.get("basis") == "summary_only" and entry.get("confidence") != "low":
        print("⚠️ 원문 미확보(summary_only)는 confidence=low 강제")
        entry["confidence"] = "low"
    reg = yaml.safe_load(open(REG, encoding="utf-8"))
    reg.setdefault("entries", []).append(entry)
    yaml.safe_dump(reg, open(REG, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
    print(f"✅ 등록 완료 ({len(reg['entries'])}건)")


if __name__ == "__main__":
    main()
