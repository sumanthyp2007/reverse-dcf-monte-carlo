# SEC filing-data reconciliation helper

This helper fetches latest annual 10-K facts from the SEC's public Company Facts API for AAPL, MSFT, and NVDA and writes JSON/CSV audit files. It does **not** claim automatic full reconciliation: XBRL tag choice, amended filings, current-vs-noncurrent debt, investment classification, diluted share basis, and fiscal-period comparability must be reviewed by an analyst.

## Run

Set a descriptive User-Agent with contact email, then run:

```bash
export SEC_USER_AGENT="Reverse DCF Research contact you@example.com"
python sec_reconcile.py --tickers AAPL MSFT NVDA --outdir outputs/sec
```

On Windows PowerShell:

```powershell
$env:SEC_USER_AGENT="Reverse DCF Research contact you@example.com"
python sec_reconcile.py --tickers AAPL MSFT NVDA --outdir outputs/sec
```

The SEC requires an identifying User-Agent. The API supplies filing-derived facts, not stock prices, beta, risk-free rates, equity risk premium, or a complete WACC. See https://www.sec.gov/search-filings/edgar-application-programming-interfaces.

## Important interpretation rules

- Review each fact's XBRL tag, unit, period end, filing date, and accession number.
- Do not sum cash and short-term investments without confirming the tags do not overlap.
- Do not sum debt tags until current/noncurrent and lease treatment are confirmed.
- Revenue candidates can differ across filers and should be checked against the face of the 10-K.
- Weighted-average diluted shares are not the same as period-end shares outstanding.
- Reconcile each SEC fact to the corresponding filing before feeding it into the DCF.
