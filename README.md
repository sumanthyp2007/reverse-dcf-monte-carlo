# Reverse DCF Research Grade | Version 2

An educational equity-research project for reverse DCF, scenario analysis, sensitivity testing, peer valuation context, and investment-memo generation. It is designed to demonstrate an analyst workflow, not to produce unattended investment recommendations.

## Deliverables

- `reverse_dcf_research_grade_model.xlsx`: editable workbook with Inputs, WACC, DCF, Scenarios, Checks, Source Log, Peer Sets, Historical Data, Scenario Analysis and Model Governance tabs.
- `reverse_dcf.py`: Python pipeline for best-effort market/accounting data retrieval, FCFF DCF, reverse growth and margin solvers, scenario analysis, Monte Carlo, tornado sensitivity, peer valuation proxies, investment memo generation and source metadata.
- `test_reverse_dcf.py`: automated unit tests for core valuation properties and valuation-bridge reconciliation.
- `investment_memo_template.md`: reusable investment memo template.
- `requirements.txt`: Python dependencies.

## Setup

Windows PowerShell:
```powershell
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python reverse_dcf.py --tickers AAPL MSFT NVDA --peers MSFT,GOOGL,AMZN --simulations 10000 --seed 2026 --outdir outputs
python -m unittest -v
```

macOS/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python reverse_dcf.py --tickers AAPL MSFT NVDA --peers MSFT,GOOGL,AMZN --simulations 10000 --seed 2026 --outdir outputs
python -m unittest -v
```

The data pipeline requires internet access and the `yfinance` package. The valuation functions and unit tests can run without `yfinance`; the live-data pipeline cannot. The program writes `run_failures.csv` when a ticker cannot be processed and fails loudly if no ticker completes.

## Outputs

For each ticker that processes successfully, the script writes:
- `*_investment_memo.md`
- `*_tornado.png` and `*_tornado_data.csv`
- `*_distribution.png`
- `*_monte_carlo.csv`
- `*_scenarios.csv`
- `*_peer_comparison.csv`, including P/S, EV/Sales and EV/EBITDA proxies where the underlying data is available
- `*_data_quality_checks.csv`
- raw provider statement snapshots: `*_income_statement_raw.csv`, `*_cash_flow_raw.csv`, `*_balance_sheet_raw.csv`

Global outputs include `summary.csv`, `data_quality_checks_all.csv`, `source_metadata.json`, and `run_failures.csv` when applicable.

## Core methodology

- FCFF = EBIT × (1 − tax rate) + D&A − capex − change in net working capital.
- Enterprise value = present value of explicit forecast FCFF + present value of terminal value.
- Equity value = enterprise value + cash − debt; per-share value divides equity value by the share count input.
- Cost of equity = risk-free rate + beta × equity risk premium.
- WACC combines cost of equity and after-tax cost of debt using market-value weights.
- Reverse DCF numerically solves for constant revenue growth or EBIT margin that equates estimated value with current price while holding other assumptions fixed.
- Monte Carlo results depend on analyst-selected distributions and correlations. They are conditional model outputs, not objective probabilities of investment success.
- The memo includes an enterprise-value bridge and terminal-value concentration diagnostic.

## Important data and model limitations

1. **No live output is bundled as verified research.** This package has not been validated against current company filings or market quotes. Run it with internet access, inspect the raw CSVs and source metadata, and independently reconcile the numbers before using results.
2. `yfinance` is a convenience data source, not the primary evidence for an investment memo. Provider labels, period order, and definitions can vary. Verify revenue, EBIT, D&A, capex, cash, debt, price, currency and diluted shares against annual/quarterly filings and a dated market-data source.
3. Risk-free rate (4.2%), equity risk premium (5.0%), pretax cost of debt (5.0%), working-capital ratio (1.0% of incremental revenue), and terminal growth (2.5%) are illustrative defaults. They are deliberately exposed in source metadata and must be replaced or justified for a real analysis.
4. Share count is based on provider shares outstanding, not a fully modelled diluted share schedule. Review options, convertibles, restricted stock, subsequent issuances and SBC. SBC is not separately forecast as a dilution schedule in this version.
5. The model does not fully normalize one-offs, pensions, leases, non-operating assets/liabilities, segment economics or working-capital seasonality. The simple enterprise-value and trading-multiple bridges are proxies that require analyst reconciliation.
6. Peer groups are user-selected candidates. They are not automatically appropriate comparables. Check business mix, geography, growth, margin profile, accounting, fiscal year and capital structure.
7. The Excel workbook is an editable manual model; it does not pull live data or run the Python numerical solvers. Reconcile Excel assumptions and outputs with Python before publishing.
8. Terminal value may account for a large portion of enterprise value. Review the terminal-value percentage, WACC/terminal-growth spread, and sensitivities. If WACC is close to terminal growth, the valuation becomes unstable.

## Institutional-style workflow

1. Pull and timestamp price and financial inputs.
2. Tie financials to annual/quarterly filings; retain raw provider data and source links.
3. Confirm units, currency, fiscal period, cash, debt and diluted shares.
4. Document and date every WACC assumption.
5. Review forecast mechanics and terminal-value concentration.
6. Solve implied growth/margins and compare with historical and relevant peer ranges.
7. Run bear/base/bull, Monte Carlo and sensitivity cases; state that distributions are assumptions-driven.
8. Write a memo with thesis, expectations implied by price, contrary evidence, catalysts, risks and valuation drivers.
9. Keep all validation flags and do not publish outputs with unresolved critical data issues.

**Educational research project, not investment advice.**
