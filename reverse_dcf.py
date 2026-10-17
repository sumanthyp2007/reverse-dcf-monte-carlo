#!/usr/bin/env python3
"""Reverse DCF Research Grade
FCFF DCF, CAPM/WACC, reverse solvers, bear/base/bull, Monte Carlo, peer metrics,
tornado/distribution charts, memo, data lineage, unit checks and run manifest.

This is a learning model. Provider fields and assumptions require independent validation.
"""
from __future__ import annotations
import argparse, json, os, warnings, hashlib
from datetime import datetime, timezone
import numpy as np
import pandas as pd
try:
    import yfinance as yf
except ImportError:  # Keep valuation math and unit tests usable without the optional data provider.
    yf = None
import matplotlib.pyplot as plt
from scipy.optimize import brentq

YEARS = 5
DEFAULT_RF = 0.042
DEFAULT_ERP = 0.050

def fnum(x, default=np.nan):
    try:
        v=float(x)
        return v if np.isfinite(v) else default
    except Exception:
        return default

def get_row(df, labels, col=0):
    if df is None or df.empty: return np.nan
    for label in labels:
        if label in df.index:
            v=df.loc[label].dropna()
            if len(v)>col: return fnum(v.iloc[col])
    return np.nan

def fetch_company(ticker):
    """Fetch best-effort data via yfinance. Market and accounting inputs remain unverified until reviewed."""
    if yf is None:
        raise RuntimeError("yfinance is not installed. Run: pip install -r requirements.txt")
    obj=yf.Ticker(ticker)
    info=obj.get_info()
    income=obj.financials
    cashflow=obj.cashflow
    balance=obj.balance_sheet
    hist=obj.history(period="5y",auto_adjust=True)
    # Save provider statement snapshots separately so analysts can inspect labels and period order.
    # These are raw provider outputs, not filing-verified numbers.
    price=fnum(hist["Close"].dropna().iloc[-1] if not hist.empty else np.nan)
    shares=fnum(info.get("sharesOutstanding"))
    revenue=get_row(income,["Total Revenue","Operating Revenue"])
    ebit=get_row(income,["Operating Income","EBIT"])
    pretax=get_row(income,["Pretax Income"])
    taxprov=get_row(income,["Tax Provision"])
    taxrate=float(np.clip(taxprov/pretax,0,0.35)) if np.isfinite(taxprov) and np.isfinite(pretax) and pretax>0 else 0.21
    da=get_row(cashflow,["Depreciation And Amortization","Depreciation Amortization Depletion"])
    capex=get_row(cashflow,["Capital Expenditure","Capital Expenditures"])
    cash=get_row(balance,["Cash Cash Equivalents And Short Term Investments","Cash And Cash Equivalents","Cash And Short Term Investments"])
    curr_debt=get_row(balance,["Current Debt And Capital Lease Obligation","Current Debt"])
    long_debt=get_row(balance,["Long Term Debt And Capital Lease Obligation","Long Term Debt"])
    debt=(max(0,curr_debt) if np.isfinite(curr_debt) else 0)+(max(0,long_debt) if np.isfinite(long_debt) else 0)
    revenue_series=pd.Series(dtype=float)
    if income is not None and not income.empty and "Total Revenue" in income.index:
        revenue_series=income.loc["Total Revenue"].dropna().copy()
        revenue_series.index=pd.to_datetime(revenue_series.index)
        revenue_series=revenue_series.sort_index().astype(float)
    growth_series=revenue_series.pct_change().replace([np.inf,-np.inf],np.nan).dropna()
    hist_growth=float(growth_series.median()) if len(growth_series) else 0.08
    hist_cagr=float((revenue_series.iloc[-1]/revenue_series.iloc[0])**(1/(len(revenue_series)-1))-1) if len(revenue_series)>1 and revenue_series.iloc[0]>0 else hist_growth
    ebitda=get_row(income,["EBITDA","Normalized EBITDA"])
    if not np.isfinite(ebitda) and np.isfinite(ebit) and np.isfinite(da):
        ebitda=ebit+abs(da)
    margin=ebit/revenue if np.isfinite(ebit) and np.isfinite(revenue) and revenue else np.nan
    da_pct=abs(da)/revenue if np.isfinite(da) and np.isfinite(revenue) and revenue else np.nan
    capex_pct=abs(capex)/revenue if np.isfinite(capex) and np.isfinite(revenue) and revenue else np.nan
    beta=fnum(info.get("beta"),1.0)
    mcap=fnum(info.get("marketCap"),price*shares if np.isfinite(price) and np.isfinite(shares) else np.nan)
    debt_weight=debt/(debt+mcap) if np.isfinite(mcap) and mcap>0 else 0.10
    debt_weight=float(np.clip(debt_weight,0,0.80))
    # Defaults are clearly labelled analyst assumptions, not live sourced market observations.
    rf=DEFAULT_RF; erp=DEFAULT_ERP
    pretax_debt_cost=0.05
    coe=rf+beta*erp
    after_tax_debt=pretax_debt_cost*(1-taxrate)
    wacc=coe*(1-debt_weight)+after_tax_debt*debt_weight
    rev_hist={str(k.date()):float(v) for k,v in revenue_series.items()}
    return {
      "ticker":ticker.upper(),"name":info.get("shortName",ticker.upper()),"price":price,"shares":shares,
      "revenue":revenue,"ebit":ebit,"ebitda":ebitda,"ebit_margin":margin,"tax_rate":taxrate,"da_pct":da_pct,
      "capex_pct":capex_pct,"cash":cash if np.isfinite(cash) else 0.0,"debt":debt,
      "hist_growth":hist_growth,"hist_cagr":hist_cagr,"beta":beta,"risk_free":rf,"erp":erp,
      "pre_tax_cost_debt":pretax_debt_cost,"debt_weight":debt_weight,"cost_equity":coe,"wacc":wacc,
      "market_cap":mcap,"currency":info.get("currency","USD"),"sector":info.get("sector","Unknown"),
      "industry":info.get("industry","Unknown"),"revenue_history":rev_hist,
      "source_provider":"yfinance","retrieved_at_utc":datetime.now(timezone.utc).isoformat(),
      "risk_free_source_status":"illustrative default; replace with dated market source",
      "erp_source_status":"illustrative default; replace with dated market source",
      "cost_of_debt_source_status":"illustrative default; replace with company-specific borrowing yield",
      "shares_basis":"provider sharesOutstanding; verify diluted share count and convertibles/options",
      "sbc_status":"not separately forecast; review SBC expense and dilution in filings"
    }

def fcff_dcf(revenue,growth,margins,tax,da_pct,capex_pct,nwc_pct,wacc,tg,cash,debt,shares,years=YEARS):
    """FCFF = EBIT*(1-tax) + D&A - capex - change in NWC; inputs must use consistent units."""
    required=[revenue,tax,da_pct,capex_pct,nwc_pct,wacc,tg,cash,debt,shares]
    if not all(np.isfinite(v) for v in required) or shares<=0 or revenue<=0 or wacc<=tg+0.002 or wacc<=0:
        return np.nan
    gs=[float(growth)]*years if np.isscalar(growth) else list(growth)
    ms=[float(margins)]*years if np.isscalar(margins) else list(margins)
    if len(gs)<years or len(ms)<years: return np.nan
    prior=float(revenue); pv_explicit=0.0; final_fcf=0.0
    for yr in range(1,years+1):
        rev=prior*(1+gs[yr-1])
        ebit=rev*ms[yr-1]
        nopat=ebit*(1-tax)
        da=rev*da_pct
        capex=rev*capex_pct
        change_nwc=(rev-prior)*nwc_pct
        fcff=nopat+da-capex-change_nwc
        pv_explicit += fcff/((1+wacc)**yr)
        prior=rev; final_fcf=fcff
    terminal_value=final_fcf*(1+tg)/(wacc-tg)
    enterprise_value=pv_explicit+terminal_value/((1+wacc)**years)
    return (enterprise_value+cash-debt)/shares

def dcf_diagnostics(revenue,growth,margin,tax,da_pct,capex_pct,nwc_pct,wacc,tg,cash,debt,shares,years=YEARS):
    """Return valuation bridge and terminal-value concentration for auditability."""
    if not np.isfinite(fcff_dcf(revenue,growth,margin,tax,da_pct,capex_pct,nwc_pct,wacc,tg,cash,debt,shares,years)):
        return {"enterprise_value":np.nan,"pv_explicit_fcff":np.nan,"terminal_value":np.nan,
                "pv_terminal_value":np.nan,"terminal_value_pct_enterprise_value":np.nan,
                "equity_value":np.nan,"value_per_share":np.nan}
    prior=float(revenue); pv_explicit=0.0; final_fcf=0.0
    gs=[float(growth)]*years if np.isscalar(growth) else list(growth)
    ms=[float(margin)]*years if np.isscalar(margin) else list(margin)
    for yr in range(1,years+1):
        rev=prior*(1+gs[yr-1]); ebit=rev*ms[yr-1]
        fcff=ebit*(1-tax)+rev*da_pct-rev*capex_pct-(rev-prior)*nwc_pct
        pv_explicit += fcff/((1+wacc)**yr); prior=rev; final_fcf=fcff
    tv=final_fcf*(1+tg)/(wacc-tg); pvtv=tv/((1+wacc)**years)
    ev=pv_explicit+pvtv; equity=ev+cash-debt
    return {"enterprise_value":ev,"pv_explicit_fcff":pv_explicit,"terminal_value":tv,
            "pv_terminal_value":pvtv,"terminal_value_pct_enterprise_value":pvtv/ev if ev else np.nan,
            "equity_value":equity,"value_per_share":equity/shares}

def root_solver(fun, low, high, steps=300):
    grid=np.linspace(low,high,steps+1)
    x0=grid[0]; y0=fun(x0)
    for x1 in grid[1:]:
        y1=fun(x1)
        if np.isfinite(y0) and np.isfinite(y1) and y0*y1<=0:
            try: return float(brentq(fun,x0,x1))
            except ValueError: pass
        x0,y0=x1,y1
    return np.nan

def implied_growth(d):
    def f(g):
        return fcff_dcf(d["revenue"],g,d["ebit_margin"],d["tax_rate"],d["da_pct"],d["capex_pct"],0.01,
                        d["wacc"],0.025,d["cash"],d["debt"],d["shares"])-d["price"]
    return root_solver(f,-0.50,0.80)

def implied_margin(d):
    def f(m):
        return fcff_dcf(d["revenue"],d["hist_growth"],m,d["tax_rate"],d["da_pct"],d["capex_pct"],0.01,
                        d["wacc"],0.025,d["cash"],d["debt"],d["shares"])-d["price"]
    return root_solver(f,-0.30,0.90)

def scenario_analysis(d):
    g=float(np.clip(d["hist_growth"],-0.20,0.50))
    m=float(np.clip(d["ebit_margin"],-0.20,0.70))
    w=float(np.clip(d["wacc"],0.045,0.20))
    rows=[]
    for label,dg,dm,dw,dtg in [("Bear",-0.05,-0.03,0.015,-0.005),("Base",0,0,0,0),("Bull",0.05,0.03,-0.01,0.005)]:
        gi=g+dg; mi=m+dm; wi=max(0.04,w+dw); tg=min(0.06,max(0,0.025+dtg),wi-0.005)
        value=fcff_dcf(d["revenue"],gi,mi,d["tax_rate"],d["da_pct"],d["capex_pct"],0.01,wi,tg,d["cash"],d["debt"],d["shares"])
        rows.append({"ticker":d["ticker"],"scenario":label,"growth":gi,"ebit_margin":mi,"wacc":wi,"terminal_growth":tg,
                     "value_per_share":value,"upside_downside":value/d["price"]-1 if d["price"] else np.nan})
    return rows

def monte_carlo(d,n=10000,seed=2026):
    rng=np.random.default_rng(seed)
    gm=float(np.clip(d["hist_growth"],-0.15,0.35)); gs=float(np.clip(abs(gm)*0.35,0.04,0.15))
    mm=float(np.clip(d["ebit_margin"],-0.10,0.65)); ms=float(np.clip(abs(mm)*0.12,0.015,0.08))
    wm=float(np.clip(d["wacc"],0.045,0.20)); ws=0.015; tm=0.025; ts=0.006
    # Correlated growth and margin draws: moderate positive correlation; WACC independent.
    z1=rng.normal(size=n); z2=rng.normal(size=n); rho=0.25
    z_margin=rho*z1+np.sqrt(1-rho*rho)*z2
    growth=np.clip(gm+gs*z1,-0.40,0.80)
    margin=np.clip(mm+ms*z_margin,-0.25,0.85)
    wacc=np.clip(rng.normal(wm,ws,n),0.04,0.25)
    tg=np.clip(rng.normal(tm,ts,n),0,0.06)
    tg=np.minimum(tg,wacc-0.005)
    vals=np.array([fcff_dcf(d["revenue"],g,m,d["tax_rate"],d["da_pct"],d["capex_pct"],0.01,w,t,
                            d["cash"],d["debt"],d["shares"]) for g,m,w,t in zip(growth,margin,wacc,tg)])
    return vals[np.isfinite(vals)],{"growth_mean":gm,"growth_sd":gs,"margin_mean":mm,"margin_sd":ms,
        "growth_margin_correlation":rho,"wacc_mean":wm,"wacc_sd":ws,"terminal_growth_mean":tm,
        "terminal_growth_sd":ts,"requested_simulations":n}

def tornado_chart(d,outdir):
    base=fcff_dcf(d["revenue"],d["hist_growth"],d["ebit_margin"],d["tax_rate"],d["da_pct"],d["capex_pct"],0.01,
                  d["wacc"],0.025,d["cash"],d["debt"],d["shares"])
    cases=[("Revenue growth","g",-0.05,0.05),("EBIT margin","m",-0.03,0.03),
           ("WACC","w",-0.01,0.01),("Terminal growth","tg",-0.01,0.01)]
    rows=[]
    for label,key,lo,hi in cases:
        vals=[]
        for delta in [lo,hi]:
            g=d["hist_growth"]; m=d["ebit_margin"]; w=d["wacc"]; tg=0.025
            if key=="g": g+=delta
            elif key=="m": m+=delta
            elif key=="w": w+=delta
            else: tg+=delta
            tg=min(tg,w-0.005)
            vals.append(fcff_dcf(d["revenue"],g,m,d["tax_rate"],d["da_pct"],d["capex_pct"],0.01,w,tg,d["cash"],d["debt"],d["shares"]))
        rows.append({"driver":label,"low_value":vals[0],"high_value":vals[1],
                     "low_change":vals[0]-base,"high_change":vals[1]-base})
    frame=pd.DataFrame(rows); frame.to_csv(os.path.join(outdir,f"{d['ticker']}_tornado_data.csv"),index=False)
    fig,ax=plt.subplots(figsize=(8.5,5))
    for i,r in frame.iterrows():
        ax.barh(i,r["high_change"],left=0,label="High assumption" if i==0 else None)
        ax.barh(i,r["low_change"],left=0,label="Low assumption" if i==0 else None)
    ax.axvline(0,linewidth=1); ax.set_yticks(range(len(frame)),frame["driver"])
    ax.set_xlabel("Change in value per share"); ax.set_title(f"{d['ticker']} sensitivity")
    ax.legend(); fig.tight_layout()
    path=os.path.join(outdir,f"{d['ticker']}_tornado.png"); fig.savefig(path,dpi=160); plt.close(fig)
    return base,frame

def peer_data(d,tickers,outdir):
    rows=[]
    for ticker in tickers:
        if ticker.upper()==d["ticker"]: continue
        try:
            p=fetch_company(ticker)
            ev=p["market_cap"]+p["debt"]-p["cash"] if np.isfinite(p["market_cap"]) else np.nan
            rows.append({"target_ticker":d["ticker"],"peer_ticker":p["ticker"],"peer_name":p["name"],
                "sector":p["sector"],"industry":p["industry"],"historical_growth_median":p["hist_growth"],
                "revenue_cagr_proxy":p["hist_cagr"],"revenue":p["revenue"],"ebit":p["ebit"],"ebitda":p["ebitda"],
                "ebit_margin":p["ebit_margin"],"market_cap":p["market_cap"],"enterprise_value_proxy":ev,
                "price_to_sales_proxy":p["market_cap"]/p["revenue"] if np.isfinite(p["market_cap"]) and p["revenue"]>0 else np.nan,
                "ev_to_sales_proxy":ev/p["revenue"] if np.isfinite(ev) and p["revenue"]>0 else np.nan,
                "ev_to_ebitda_proxy":ev/p["ebitda"] if np.isfinite(ev) and np.isfinite(p["ebitda"]) and p["ebitda"]>0 else np.nan,
                "retrieved_at_utc":p["retrieved_at_utc"],"provider":"yfinance","multiples_status":"proxy; reconcile market cap, debt, cash and EBITDA"})
        except Exception as e: warnings.warn(f"Peer {ticker} failed: {e}")
    frame=pd.DataFrame(rows)
    if not frame.empty: frame.to_csv(os.path.join(outdir,f"{d['ticker']}_peer_comparison.csv"),index=False)
    return frame

def write_memo(d,base,vals,ig,im,scenarios,peers,outdir):
    p10,p50,p90=np.percentile(vals,[10,50,90]) if len(vals) else (np.nan,np.nan,np.nan)
    prob=float(np.mean(vals>d["price"])) if len(vals) else np.nan
    pg=float(peers["historical_growth_median"].median()) if peers is not None and not peers.empty else np.nan
    pm=float(peers["ebit_margin"].median()) if peers is not None and not peers.empty else np.nan
    money=lambda x: "N/A" if not np.isfinite(x) else f"{d['currency']} {x:,.2f}"
    pct=lambda x: "N/A" if not np.isfinite(x) else f"{x:.1%}"
    lines=[f"# {d['name']} ({d['ticker']}) | Reverse DCF investment memo",
        f"**As of UTC:** {d['retrieved_at_utc']} | **Price:** {money(d['price'])} | **Sector:** {d['sector']} / {d['industry']}",
        "","## Investment question","What operating performance is implied by the current market price?","",
        "## Reverse DCF",
        f"- Implied constant revenue growth, holding EBIT margin fixed: {pct(ig)}.",
        f"- Implied constant EBIT margin, holding historical growth proxy fixed: {pct(im)}.",
        f"- Historical revenue CAGR proxy: {pct(d['hist_cagr'])}; median annual growth proxy: {pct(d['hist_growth'])}.",
        f"- Base DCF value per share: {money(base)}.",
        f"- Monte Carlo P10 / median / P90: {money(p10)} / {money(p50)} / {money(p90)}.",
        f"- Modelled probability fair value exceeds price: {pct(prob)}.","","## Scenario values"]
    for s in scenarios: lines.append(f"- {s['scenario']}: {money(s['value_per_share'])} per share; upside/downside {pct(s['upside_downside'])}.")
    diag=dcf_diagnostics(d["revenue"],d["hist_growth"],d["ebit_margin"],d["tax_rate"],d["da_pct"],d["capex_pct"],0.01,d["wacc"],0.025,d["cash"],d["debt"],d["shares"])
    lines += [f"- Present value of explicit forecast FCFF: {money(diag['pv_explicit_fcff'])} (enterprise-value units).",
        f"- Present value of terminal value: {money(diag['pv_terminal_value'])}; terminal value share of EV: {pct(diag['terminal_value_pct_enterprise_value'])}.",
        "","## Peer context",f"- Peer median historical growth proxy: {pct(pg)}.",f"- Peer median EBIT margin: {pct(pm)}.",
        "Peer lists must be reviewed for business-model fit. Consolidated margins can mislead when segment mixes differ.",
        "","## Risks and limitations",
        "- Verify data, currency, units, fiscal period, cash, debt and diluted shares against company filings.",
        "- WACC defaults are estimates; replace them with sourced market inputs and document dates.",
        "- This simplified model uses a flat working-capital ratio and does not separately normalize one-offs or segment economics.",
        "- Terminal value can dominate valuation; inspect terminal value / enterprise value and run sensitivities.",
        "- Monte Carlo results are conditional on analyst-selected distributions, not objective probabilities of investment success.",
        "- This is an educational research model, not investment advice."]
    path=os.path.join(outdir,f"{d['ticker']}_investment_memo.md")
    open(path,"w",encoding="utf-8").write("\n".join(lines))
    return {"p10":p10,"median":p50,"p90":p90,"probability_upside":prob,"implied_growth":ig,"implied_margin":im}

def data_quality_checks(d):
    """Separate machine-checkable failures from manual analyst-review requirements."""
    checks=[]
    def add(name, passed, note=""):
        checks.append({"ticker":d["ticker"],"check":name,"status":"PASS" if passed else "FAIL",
                       "pass":bool(passed),"note":note})
    add("price_present",np.isfinite(d["price"]) and d["price"]>0)
    add("revenue_positive",np.isfinite(d["revenue"]) and d["revenue"]>0)
    add("shares_positive",np.isfinite(d["shares"]) and d["shares"]>0)
    add("cash_nonnegative",np.isfinite(d["cash"]) and d["cash"]>=0,"Confirm cash is cash plus eligible short-term investments.")
    add("debt_nonnegative",np.isfinite(d["debt"]) and d["debt"]>=0,"Confirm debt labels and lease treatment.")
    add("wacc_in_reasonable_range",np.isfinite(d["wacc"]) and 0.03<d["wacc"]<0.30)
    add("wacc_exceeds_terminal_growth",np.isfinite(d["wacc"]) and d["wacc"]>0.027)
    add("margin_plausibility",np.isfinite(d["ebit_margin"]) and -.5<d["ebit_margin"]<.9)
    for name,note in [
        ("market_price_source","Confirm price timestamp, exchange, and currency."),
        ("revenue_ebit_and_cashflow","Tie latest annual financials to the 10-K/20-F and confirm period alignment."),
        ("diluted_share_count","Review diluted weighted-average shares, options, convertibles and subsequent issuances."),
        ("stock_based_compensation","Assess SBC as an economic expense and reconcile to share dilution."),
        ("risk_free_rate_and_erp","Replace illustrative defaults with dated, documented market sources."),
        ("cost_of_debt","Replace illustrative debt-cost default with a defensible company-specific estimate."),
        ("peer_selection","Review peer business mix, growth, margins, geography and fiscal-year comparability."),
        ("terminal_value_concentration","Review terminal value as a share of enterprise value and test sensitivities.")]:
        checks.append({"ticker":d["ticker"],"check":name,"status":"REVIEW_REQUIRED","pass":None,"note":note})
    return checks

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--tickers",nargs="+",default=["AAPL","MSFT","NVDA"])
    parser.add_argument("--peers",default="MSFT,GOOGL,AMZN",help="Example only; customize peers for each target")
    parser.add_argument("--simulations",type=int,default=10000)
    parser.add_argument("--outdir",default="outputs")
    parser.add_argument("--seed",type=int,default=2026,help="Deterministic Monte Carlo seed")
    args=parser.parse_args()
    if args.simulations < 100:
        parser.error("--simulations must be at least 100")
    os.makedirs(args.outdir,exist_ok=True)
    summary=[]; metadata={}; all_checks=[]; failures=[]
    peer_list=[x.strip() for x in args.peers.split(",") if x.strip()]
    for ticker in args.tickers:
        try:
            d=fetch_company(ticker)
            # Preserve raw provider tables for manual mapping/reconciliation.
            if yf is not None:
                raw_obj=yf.Ticker(ticker)
                for label, table in [("income_statement",raw_obj.financials),("cash_flow",raw_obj.cashflow),("balance_sheet",raw_obj.balance_sheet)]:
                    if table is not None and not table.empty:
                        table.to_csv(os.path.join(args.outdir,f"{ticker}_{label}_raw.csv"))
            required_fields=["price","revenue","ebit","shares","da_pct","capex_pct","wacc"]
            missing=[field for field in required_fields if not np.isfinite(d.get(field,np.nan))]
            if missing or d["price"]<=0 or d["revenue"]<=0 or d["shares"]<=0:
                raise ValueError(f"Missing/invalid required inputs: {missing or 'non-positive price/revenue/shares'}. Inspect provider fields and filing data.")
            checks=data_quality_checks(d); all_checks.extend(checks)
            pd.DataFrame(checks).to_csv(os.path.join(args.outdir,f"{ticker}_data_quality_checks.csv"),index=False)
            ig=implied_growth(d); im=implied_margin(d)
            vals,dist=monte_carlo(d,args.simulations,seed=args.seed)
            base,tornado=tornado_chart(d,args.outdir)
            scenarios=scenario_analysis(d)
            peers=peer_data(d,peer_list,args.outdir)
            pd.DataFrame(scenarios).to_csv(os.path.join(args.outdir,f"{ticker}_scenarios.csv"),index=False)
            pd.DataFrame({"fair_value_per_share":vals}).to_csv(os.path.join(args.outdir,f"{ticker}_monte_carlo.csv"),index=False)
            fig,ax=plt.subplots(figsize=(8.5,4.8)); ax.hist(vals,bins=60)
            ax.axvline(d["price"],label="Market price"); ax.axvline(np.median(vals),label="Median simulated value")
            ax.set_title(f"{ticker} fair-value distribution"); ax.set_xlabel(f"Value per share ({d['currency']})"); ax.legend()
            fig.tight_layout(); fig.savefig(os.path.join(args.outdir,f"{ticker}_distribution.png"),dpi=160); plt.close(fig)
            result=write_memo(d,base,vals,ig,im,scenarios,peers,args.outdir)
            summary.append({"ticker":ticker,"price":d["price"],"base_value":base,**result})
            metadata[ticker]={"company_inputs":{k:v for k,v in d.items() if k!="revenue_history"},
                              "revenue_history":d["revenue_history"],"monte_carlo_assumptions":dist,
                              "valuation_diagnostics":dcf_diagnostics(d["revenue"],d["hist_growth"],d["ebit_margin"],d["tax_rate"],d["da_pct"],d["capex_pct"],0.01,d["wacc"],0.025,d["cash"],d["debt"],d["shares"])}
            print(f"{ticker}: base={base:.2f}; implied growth={ig}; upside probability={result['probability_upside']}")
        except Exception as e:
            failures.append({"ticker":ticker,"error":str(e)})
            warnings.warn(f"{ticker} failed: {e}")
    if summary:
        pd.DataFrame(summary).to_csv(os.path.join(args.outdir,"summary.csv"),index=False)
        pd.DataFrame(all_checks).to_csv(os.path.join(args.outdir,"data_quality_checks_all.csv"),index=False)
        manifest={"run_time_utc":datetime.now(timezone.utc).isoformat(),"provider":"yfinance",
                  "tickers_requested":args.tickers,"tickers_succeeded":list(metadata.keys()),"failures":failures,
                  "peers_requested":peer_list,"simulations":args.simulations,"seed":args.seed,
                  "assumptions":{"risk_free_rate":DEFAULT_RF,"equity_risk_premium":DEFAULT_ERP,
                                 "pretax_cost_of_debt":0.05,"working_capital_pct_incremental_revenue":0.01,
                                 "terminal_growth_rate":0.025},
                  "disclaimer":"Provider data and model assumptions require independent verification.",
                  "companies":metadata}
        with open(os.path.join(args.outdir,"source_metadata.json"),"w",encoding="utf-8") as f:
            json.dump(manifest,f,indent=2,default=str)
        print("Completed. Outputs saved to",args.outdir)
    if failures:
        pd.DataFrame(failures).to_csv(os.path.join(args.outdir,"run_failures.csv"),index=False)
    if not summary:
        pd.DataFrame(failures,columns=["ticker","error"]).to_csv(os.path.join(args.outdir,"run_failures.csv"),index=False)
        raise SystemExit("No tickers completed successfully. See run_failures.csv and install/check dependencies.")

if __name__=="__main__":
    main()
