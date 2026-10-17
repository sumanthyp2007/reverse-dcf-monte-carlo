import os
import tempfile
import streamlit as st
import pandas as pd
import numpy as np

from reverse_dcf import (
    fetch_company,
    dcf_diagnostics,
    implied_growth,
    implied_margin,
    scenario_analysis,
    monte_carlo,
    tornado_chart,
    peer_data,
    write_memo,
    data_quality_checks,
)

st.set_page_config(page_title="Reverse DCF & Monte Carlo", layout="wide")
st.title("Reverse DCF & Monte Carlo Valuation Model")
st.caption("Live FCFF Reverse DCF, Scenario Analysis, and 10,000-Trial Monte Carlo Simulation")

with st.sidebar:
    st.header("1. Choose Company")
    ticker = st.text_input("Stock Ticker", value="AAPL").upper().strip()
    peers_input = st.text_input("Peer Tickers (comma-separated)", value="MSFT,GOOGL,AMZN")
    
    st.header("2. Simulation Settings")
    simulations = st.slider("Monte Carlo Runs", min_value=1000, max_value=20000, value=10000, step=1000)
    seed = st.number_input("Random Seed", value=2026, step=1)
    
    st.header("3. Custom Overrides")
    use_overrides = st.checkbox("Override WACC & Terminal Growth")
    custom_wacc = st.slider("WACC (%)", 4.0, 20.0, 9.0, 0.1) / 100.0
    custom_tg = st.slider("Terminal Growth (%)", 0.5, 5.0, 2.5, 0.1) / 100.0
    
    run_btn = st.button("Run Valuation Model", type="primary", use_container_width=True)

@st.cache_data(ttl=3600, show_spinner="Fetching live financial statements...")
def get_data(tk):
    return fetch_company(tk)

if run_btn or ticker:
    try:
        d = get_data(ticker).copy()
        if use_overrides:
            d["wacc"] = custom_wacc
        tg_val = custom_tg if use_overrides else 0.025

        with tempfile.TemporaryDirectory() as tmpdir:
            ig = implied_growth(d)
            im = implied_margin(d)
            vals, _ = monte_carlo(d, n=simulations, seed=int(seed))
            base_val, _ = tornado_chart(d, tmpdir)
            scenarios = scenario_analysis(d)
            
            # Save distribution chart
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(8.5, 4.8))
            ax.hist(vals, bins=60)
            ax.axvline(d["price"], color="red", linestyle="--", label="Market Price")
            ax.axvline(np.median(vals), color="green", linestyle="-", label="Median Simulated Value")
            ax.set_title(f"{ticker} Fair-Value Distribution")
            ax.set_xlabel(f"Value per share ({d['currency']})")
            ax.legend()
            fig.tight_layout()
            dist_path = os.path.join(tmpdir, f"{d['ticker']}_distribution.png")
            fig.savefig(dist_path, dpi=160)
            plt.close(fig)

            peer_list = [x.strip() for x in peers_input.split(",") if x.strip()]
            peers_df = peer_data(d, peer_list, tmpdir)
            memo_stats = write_memo(d, base_val, vals, ig, im, scenarios, peers_df, tmpdir)
            
            memo_path = os.path.join(tmpdir, f"{d['ticker']}_investment_memo.md")
            with open(memo_path, "r", encoding="utf-8") as f:
                memo_md = f.read()

            # Display Top Summary Cards
            st.subheader(f"{d['name']} ({d['ticker']}) — {d['sector']}")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Market Price", f"{d['currency']} {d['price']:,.2f}")
            c2.metric("Base DCF Value", f"{d['currency']} {base_val:,.2f}", f"{(base_val/d['price']-1)*100:+.1f}%")
            c3.metric("Implied Growth", f"{ig*100:.1f}%" if np.isfinite(ig) else "N/A")
            c4.metric("Implied Margin", f"{im*100:.1f}%" if np.isfinite(im) else "N/A")
            c5.metric("Upside Probability", f"{memo_stats['probability_upside']*100:.1f}%")

            t1, t2, t3, t4 = st.tabs(["Charts & Monte Carlo", "Scenarios & Peers", "Investment Memo", "Data Checks"])
            
            with t1:
                col1, col2 = st.columns(2)
                col1.image(dist_path, caption="Monte Carlo Fair-Value Distribution")
                col2.image(os.path.join(tmpdir, f"{d['ticker']}_tornado.png"), caption="Tornado Sensitivity Chart")
                
            with t2:
                st.write("### Bear / Base / Bull Scenarios")
                st.dataframe(pd.DataFrame(scenarios), use_container_width=True)
                st.write("### Peer Comparables")
                st.dataframe(peers_df, use_container_width=True)
                
            with t3:
                st.download_button("Download Memo (.md)", memo_md, file_name=f"{ticker}_memo.md")
                st.markdown(memo_md)
                
            with t4:
                st.dataframe(pd.DataFrame(data_quality_checks(d)), use_container_width=True)

    except Exception as e:
        st.error(f"Error loading {ticker}: {e}")