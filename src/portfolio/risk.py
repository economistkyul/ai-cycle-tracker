"""계좌 A+B 합산 포트폴리오 위험 v3.

v3 수정:
- example 파일 무단 사용 금지 → (values, is_demo) 반환, DEMO DATA 명시
- 팩터 노출: 명목/레버리지조정 이중 출력
- 국가·통화 노출 포함
- top5: 보유종목별 비중(data/private/holdings.yaml) 있으면 holding 기준,
  없으면 버킷 기준 + 사유 명시
- 레버리지 버킷 상품별 비중 미공급 → equal-weight assumption 명시
"""
from __future__ import annotations
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
_last_source = None


def load_portfolio(path: Path | None = None) -> dict:
    with open(path or ROOT / "config" / "portfolio.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_weights(pf: dict, tol: float = 0.5) -> dict[str, float]:
    sums = {}
    for acc, spec in pf["accounts"].items():
        s = sum(b["weight_pct"] for b in spec["buckets"].values())
        sums[acc] = s
        if abs(s - 100) > tol:
            raise ValueError(f"{acc} 비중 합 {s} ≠ 100")
    return sums


def load_account_values() -> tuple[dict | None, bool]:
    """반환: (values, is_demo). 실파일 없으면 example을 쓰되 is_demo=True."""
    global _last_source
    real = ROOT / "data" / "private" / "account_values.yaml"
    demo = ROOT / "data" / "private" / "account_values.example.yaml"
    if real.exists():
        _last_source = real
        with open(real, encoding="utf-8") as f:
            return yaml.safe_load(f), False
    if demo.exists():
        _last_source = demo
        with open(demo, encoding="utf-8") as f:
            return yaml.safe_load(f), True
    _last_source = None
    return None, False


def account_values_source():
    return _last_source


def _bucket_leverage(pf: dict, bucket: dict) -> float:
    rules = pf.get("leveraged_etf_rules", {})
    levs = [rules[h]["leverage_multiple"] for h in bucket.get("holdings", []) if h in rules]
    return sum(levs) / len(levs) if levs else 1.0   # equal-weight assumption


def combined_exposure(pf: dict, values: dict, is_demo: bool = False) -> dict:
    fmap = pf["factor_map"]
    accounts = {a: float(values[a]) for a in pf["accounts"]}
    total = sum(accounts.values())
    nominal, effective, beta_adj = {}, 0.0, 0.0
    fac_nom = {"semiconductor": 0.0, "nasdaq_megacap": 0.0, "ai_capex": 0.0}
    fac_eff = dict(fac_nom)
    country, currency = {}, {}
    holdings_by_account = {}

    for acc, spec in pf["accounts"].items():
        share = accounts[acc] / total
        holdings_by_account[acc] = set()
        for c, w in spec.get("country_mix", {}).items():
            country[c] = country.get(c, 0.0) + w * share * 100
        for c, w in spec.get("currency_mix", {}).items():
            currency[c] = currency.get(c, 0.0) + w * share * 100
        for bname, b in spec["buckets"].items():
            w = b["weight_pct"] * share
            nominal[bname] = nominal.get(bname, 0.0) + w
            f = fmap.get(bname, {"beta": 1.0})
            lev = _bucket_leverage(pf, b)
            effective += w * lev
            beta_adj += w * float(f.get("beta", 1.0))
            for fac in fac_nom:
                fac_nom[fac] += w * float(f.get(fac, 0.0))
                fac_eff[fac] += w * lev * float(f.get(fac, 0.0))
            holdings_by_account[acc].update(b.get("holdings", []))

    overlap = set.intersection(*holdings_by_account.values()) if len(holdings_by_account) > 1 else set()

    hfile = ROOT / "data" / "private" / "holdings.yaml"
    if hfile.exists():
        with open(hfile, encoding="utf-8") as fh:
            hw = yaml.safe_load(fh)
        top5 = sorted(hw.items(), key=lambda kv: -kv[1])[:5]
        top5_out = {"basis": "holding", "value_pct": round(sum(v for _, v in top5), 1),
                    "names": [k for k, _ in top5]}
    else:
        t5 = sorted(nominal.items(), key=lambda kv: -kv[1])[:5]
        top5_out = {"basis": "bucket", "value_pct": round(sum(v for _, v in t5), 1),
                    "note": "보유종목별 비중 미공급 — 버킷 기준 대체"}

    return {
        "is_demo_data": is_demo,
        "nominal_by_bucket_pct": {k: round(v, 2) for k, v in nominal.items()},
        "effective_exposure_pct": round(effective, 1),
        "beta_adjusted_exposure_pct": round(beta_adj, 1),
        "factor_exposure_nominal_pct": {k: round(v, 1) for k, v in fac_nom.items()},
        "factor_exposure_effective_pct": {k: round(v, 1) for k, v in fac_eff.items()},
        "country_exposure_pct": {k: round(v, 1) for k, v in country.items()},
        "currency_exposure_pct": {k: round(v, 1) for k, v in currency.items()},
        "top5_concentration": top5_out,
        "overlap_holdings": sorted(overlap),
        "cash_pct": round(nominal.get("unallocated", 0.0), 2),
        "leveraged_weighting": pf.get("leveraged_bucket_weighting", "unspecified"),
    }


def stress_loss(exposure: dict, shocks: dict | None = None) -> dict:
    shocks = shocks or {"1d": -5.0, "5d": -12.0, "20d": -25.0}
    b = exposure["beta_adjusted_exposure_pct"] / 100
    return {k: round(v * b, 1) for k, v in shocks.items()}
