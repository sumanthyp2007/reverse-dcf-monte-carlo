#!/usr/bin/env python3
"""Fetch latest annual SEC company-facts values for manual reconciliation.

SEC data are official filing-derived facts, but XBRL tag mapping and fiscal-period
selection still require analyst review. This module intentionally does not pretend
that SEC data alone provide a current stock price or a full valuation model.
"""
from __future__ import annotations
import argparse, json, os, time
from datetime import datetime, timezone
import pandas as pd
import requests

CIKS = {"AAPL":"0000320193", "MSFT":"0000789019", "NVDA":"0001045810"}
TAGS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "Revenues"],
    "operating_income": ["OperatingIncomeLoss"],
    "cash_and_equivalents": ["CashAndCashEquivalentsAtCarryingValue"],
    "short_term_investments": ["ShortTermInvestments", "AvailableForSaleSecuritiesCurrent"],
    "current_debt": ["ShortTermBorrowings", "LongTermDebtCurrent", "LongTermDebtAndFinanceLeaseObligationsCurrent"],
    "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebtAndFinanceLeaseObligationsNoncurrent"],
    "diluted_weighted_average_shares": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
}
BASE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{}.json"

def _facts_for_tag(payload, tag):
    facts = payload.get("facts", {}).get("us-gaap", {}).get(tag, {})
    units = facts.get("units", {})
    # Most monetary facts use USD, shares use shares. Preserve the actual unit.
    for unit, entries in units.items():
        annual = [e for e in entries if e.get("form") == "10-K" and e.get("fp") == "FY" and e.get("val") is not None]
        if not annual:
            annual = [e for e in entries if e.get("form") == "10-K" and e.get("val") is not None]
        if annual:
            annual.sort(key=lambda e: (e.get("end", ""), e.get("filed", "")))
            latest_end = annual[-1].get("end")
            same_period = [e for e in annual if e.get("end") == latest_end]
            # Prefer the latest filed value for the selected period.
            chosen = sorted(same_period, key=lambda e: e.get("filed", ""))[-1]
            return {"value": chosen["val"], "unit": unit, "period_end": chosen.get("end"),
                    "filed": chosen.get("filed"), "form": chosen.get("form"), "tag": tag,
                    "accn": chosen.get("accn")}
    return None

def pick_fact(payload, candidates):
    for tag in candidates:
        found = _facts_for_tag(payload, tag)
        if found is not None:
            return found
    return None

def fetch_sec_facts(ticker, user_agent, timeout=25):
    ticker = ticker.upper()
    if ticker not in CIKS:
        raise ValueError(f"No SEC CIK configured for {ticker}. Add a verified CIK before running.")
    if not user_agent or "@" not in user_agent:
        raise ValueError("Provide a descriptive SEC_USER_AGENT containing a contact email, e.g. 'Research Project contact@example.com'.")
    response = requests.get(BASE.format(CIKS[ticker]), headers={"User-Agent": user_agent, "Accept-Encoding":"gzip, deflate"}, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    results = {key: pick_fact(payload, candidates) for key, candidates in TAGS.items()}
    # Use best available current debt tag for each side; tag overlap is surfaced for review.
    return {"ticker":ticker, "cik":CIKS[ticker], "company_name":payload.get("entityName"),
            "retrieved_at_utc":datetime.now(timezone.utc).isoformat(), "source_url":BASE.format(CIKS[ticker]),
            "facts":results, "notes":["Latest annual 10-K facts only; quarterlies and amendments may change the preferred period.",
                "Cash and short-term investments are separate facts and should only be added after checking overlap.",
                "Debt tags may overlap or vary by company; inspect tags and filing context before summing.",
                "Revenue tag selection follows the first available candidate and requires mapping review.",
                "SEC company facts do not provide a current market price or a complete WACC input set."]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tickers", nargs="+", default=["AAPL","MSFT","NVDA"])
    p.add_argument("--outdir", default="outputs")
    p.add_argument("--user-agent", default=os.environ.get("SEC_USER_AGENT", ""))
    p.add_argument("--pause-seconds", type=float, default=0.25)
    args=p.parse_args(); os.makedirs(args.outdir, exist_ok=True)
    outputs=[]; errors=[]
    for ticker in args.tickers:
        try:
            result=fetch_sec_facts(ticker,args.user_agent)
            outputs.append(result)
            with open(os.path.join(args.outdir,f"{ticker.upper()}_sec_facts.json"),"w",encoding="utf-8") as f: json.dump(result,f,indent=2)
            flat={"ticker":ticker.upper(),"cik":result["cik"],"company_name":result["company_name"],"retrieved_at_utc":result["retrieved_at_utc"]}
            for name, fact in result["facts"].items():
                flat[name]=fact.get("value") if fact else None
                flat[name+"_unit"]=fact.get("unit") if fact else None
                flat[name+"_period_end"]=fact.get("period_end") if fact else None
                flat[name+"_tag"]=fact.get("tag") if fact else None
            pd.DataFrame([flat]).to_csv(os.path.join(args.outdir,f"{ticker.upper()}_sec_facts.csv"),index=False)
            print(f"{ticker.upper()}: SEC facts saved; inspect tags and periods before reconciliation.")
        except Exception as e:
            errors.append({"ticker":ticker,"error":str(e)})
            print(f"{ticker.upper()}: FAILED: {e}")
        time.sleep(max(0,args.pause_seconds))
    pd.DataFrame(errors).to_csv(os.path.join(args.outdir,"sec_reconcile_failures.csv"),index=False)
    if not outputs: raise SystemExit("No SEC facts retrieved. Check network access, User-Agent, and failures file.")
    with open(os.path.join(args.outdir,"sec_reconcile_manifest.json"),"w",encoding="utf-8") as f:
        json.dump({"retrieved_at_utc":datetime.now(timezone.utc).isoformat(),"source":"SEC EDGAR Company Facts API",
                   "succeeded":[x["ticker"] for x in outputs],"failures":errors,
                   "important":"Machine-selected facts are a reconciliation aid, not filing-verified valuation inputs."},f,indent=2)

if __name__ == "__main__": main()
