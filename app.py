# app.py — CASE LTS Mini UI (Streamlit)
# Run: streamlit run app.py

import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import date
from dateutil.relativedelta import relativedelta
import plotly.graph_objects as go

# ========================
# Config
# ========================
API_DEFAULT = "http://127.0.0.1:8000"  # adjust here if needed
st.set_page_config(page_title="CASE LTS — Quick Viz", layout="wide")

# ========================
# Utils
# ========================
def _ensure_list(data):
    """Accept DRF with/without pagination: dict {'results': [...]} or list[...]"""
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "results" in data and isinstance(data["results"], list):
        return data["results"]
    return []

def _detect_external_link(row: dict, api_base: str) -> str | None:
    """Find an EXTERNAL news link and ignore internal API links."""
    candidates = ["external_url", "article_url", "news_url", "link", "source_url", "url"]
    for key in candidates:
        v = row.get(key)
        if isinstance(v, str) and v.startswith(("http://", "https://")):
            if "/api/" in v and api_base in v:
                continue
            return v
    for _, v in row.items():
        if isinstance(v, str) and v.startswith(("http://", "https://")):
            if "/api/" in v and api_base in v:
                continue
            return v
    return None

def _fmt_date(d: date) -> str:
    return d.isoformat()

# ---------- Cleaning / Resampling ----------
def _to_numeric(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

def _drop_bad_ohlc(df):
    """Drop rows with impossible OHLC or NaNs."""
    req = {"open", "high", "low", "close"}
    if not req.issubset(df.columns):
        return df
    mask = (
        df["high"].ge(df[["open", "close"]].max(axis=1)) &
        df["low"].le(df[["open", "close"]].min(axis=1))
    )
    return df[mask].dropna(subset=["open", "high", "low", "close"])

def _resample_ohlc(df, rule: str):
    """Resample to a neat rule keeping OHLC semantics."""
    if not rule:
        return df
    rule_map = {"4H": "4H", "1D": "1D"}
    r = rule_map.get(rule, rule)
    out = (
        df.set_index("ts")
          .resample(r)
          .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
          .dropna(subset=["open", "high", "low", "close"])
          .reset_index()
    )
    return out

def prepare_for_plot(df: pd.DataFrame, rule: str):
    """Clean, de-duplicate, sort, and resample to the chosen resolution."""
    if df.empty or "ts" not in df.columns:
        return df
    df = df.copy()
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    df = df.dropna(subset=["ts"]).sort_values("ts").drop_duplicates(subset=["ts"])
    df = _to_numeric(df, ["open", "high", "low", "close", "volume"])
    df = _drop_bad_ohlc(df)
    if df.empty:
        return df
    df = _resample_ohlc(df, rule)
    return df

# ========================
# Fetchers
# ========================
@st.cache_data(ttl=60)
def fetch_companies(api_base: str):
    url = f"{api_base}/api/companies/"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = _ensure_list(r.json())
    rows = []
    for item in data:
        ticker = item.get("ticker") or item.get("symbol") or item.get("slug") or ""
        name = item.get("name") or item.get("title") or ticker
        if ticker:
            rows.append({"ticker": ticker, "name": name})
    return rows

@st.cache_data(ttl=60)
def fetch_candles(api_base: str, ticker: str, start: str, end: str):
    def _get(u):
        r = requests.get(u, timeout=30)
        r.raise_for_status()
        data = _ensure_list(r.json())
        df = pd.DataFrame(data)
        if not df.empty and "ts" in df.columns:
            df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
        return df

    url = f"{api_base}/api/marketcandles/?company={ticker}&start={start}&end={end}"
    df = _get(url)
    if df.empty:
        df_all = _get(f"{api_base}/api/marketcandles/?company={ticker}")
        if not df_all.empty and "ts" in df_all.columns:
            s = pd.to_datetime(start)
            e = pd.to_datetime(end) + pd.Timedelta(days=1)
            df = df_all[(df_all["ts"] >= s) & (df_all["ts"] < e)]
    if not df.empty and "ts" in df.columns:
        df = df.sort_values("ts")
    return df

@st.cache_data(ttl=60)
def fetch_articles(api_base: str, ticker: str, start: str, end: str, limit: int = 100):
    url = f"{api_base}/api/articles/?company={ticker}&start={start}&end={end}&limit={limit}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = _ensure_list(r.json())
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    pub_col = None
    for c in ["published", "published_at", "datetime"]:
        if c in df.columns:
            pub_col = c
            df[c] = pd.to_datetime(df[c], errors="coerce")
            break
    if pub_col and pub_col != "published":
        df["published"] = df[pub_col]
    api_host = api_base.rstrip("/")
    df["ext_link"] = [_detect_external_link(row, api_host) for row in data]
    if "sentiment_label" not in df.columns:
        if "sentiment" in df.columns:
            df["sentiment_label"] = df["sentiment"].astype(str).str.capitalize()
        else:
            df["sentiment_label"] = "Neutral"
    if "published" in df.columns:
        df = df.sort_values("published", ascending=False)
    for c in ["title", "source", "published", "sentiment_label", "ext_link"]:
        if c not in df.columns:
            df[c] = None
    return df

# ========================
# UI
# ========================
st.title("CASE LTS — Quick Viz")

api_base = st.sidebar.text_input("API Base", value=API_DEFAULT)

companies = fetch_companies(api_base)
ticker_options = [f"{c['ticker']} — {c['name']}" for c in companies] if companies else []
ticker_map = {opt: opt.split(" — ")[0] for opt in ticker_options}

col1, col2, col3, col4 = st.columns([2, 1, 1, 2], gap="medium")

with col1:
    if ticker_options:
        sel = st.selectbox("Company", options=ticker_options, index=0)
        ticker = ticker_map.get(sel, "MSFT")
    else:
        st.warning("No companies returned by the API. Check /api/companies/")
        ticker = "MSFT"

with col2:
    end_d = st.date_input("End", value=date.today())
with col3:
    start_d = st.date_input("Start", value=date.today() - relativedelta(days=30))

# Resolution selector — only 4H and 1D
resolution = st.radio("Resolution", ["4H", "1D"], horizontal=True, index=0)

start_s, end_s = _fmt_date(start_d), _fmt_date(end_d)

with st.spinner("Loading data..."):
    raw = fetch_candles(api_base, ticker, start_s, end_s)
    candles = prepare_for_plot(raw, rule=resolution)
    articles = fetch_articles(api_base, ticker, start_s, end_s)

left, right = st.columns([2, 1], gap="large")

# ---- Price (dark candlesticks) ----
with left:
    st.subheader("Price")
    if candles.empty or not {"ts","open","high","low","close"}.issubset(candles.columns):
        st.info("No OHLC candles in the selected range.")
    else:
        prev_close = float(candles["close"].iloc[0])

        fig = go.Figure()
        fig.add_trace(
            go.Candlestick(
                x=candles["ts"],
                open=candles["open"],
                high=candles["high"],
                low=candles["low"],
                close=candles["close"],
                increasing_line_color="#26a69a",   # teal
                increasing_fillcolor="#26a69a",
                decreasing_line_color="#e74c3c",   # red
                decreasing_fillcolor="#e74c3c",
                increasing_line_width=1,
                decreasing_line_width=1,
                whiskerwidth=0.35,
                name="OHLC",
            )
        )

        # Prev close dashed line + label
        fig.add_hline(y=prev_close, line_width=1, line_dash="dash", line_color="rgba(255,255,255,0.45)")
        fig.add_annotation(
            x=1.0, y=prev_close, xref="paper", yref="y", xanchor="left",
            showarrow=False, text="Prev close",
            font=dict(size=12, color="rgba(255,255,255,0.75)"),
            bgcolor="rgba(17,24,39,0.8)",
            bordercolor="rgba(255,255,255,0.2)", borderwidth=1, borderpad=3,
        )

        # Dark TradingView-like layout
        fig.update_layout(
            dragmode="pan",
            hovermode="x unified",
            margin=dict(l=8, r=8, t=8, b=0),
            plot_bgcolor="#0f111a",
            paper_bgcolor="#0f111a",
            font=dict(color="#e5e7eb"),
            showlegend=False,
            xaxis=dict(
                rangeslider=dict(visible=False),
                showgrid=True, gridcolor="#2b2f3a", gridwidth=1,
                zeroline=False, showspikes=True, spikemode="across",
                spikecolor="rgba(255,255,255,0.25)", spikethickness=1,
            ),
            yaxis=dict(
                showgrid=True, gridcolor="#2b2f3a", gridwidth=1,
                zeroline=False, showspikes=True,
            ),
        )

        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    st.subheader("Volume")
    if candles.empty or "volume" not in candles.columns:
        st.info("No volume in the selected range.")
    else:
        vol = go.Figure()
        vol.add_trace(go.Bar(x=candles["ts"], y=candles["volume"], marker=dict(color="#3b82f6"), name="Volume"))
        vol.update_layout(
            margin=dict(l=8, r=8, t=8, b=0),
            plot_bgcolor="#0f111a",
            paper_bgcolor="#0f111a",
            font=dict(color="#e5e7eb"),
            showlegend=False,
            xaxis=dict(showgrid=False, rangeslider=dict(visible=False)),
            yaxis=dict(showgrid=False, zeroline=False),
            bargap=0.1,
        )
        st.plotly_chart(vol, use_container_width=True, config={"displayModeBar": False})

# ---- News ----
with right:
    st.subheader("News & Sentiment")
    if articles.empty:
        st.info("No news in the selected range.")
    else:
        counts = (
            articles["sentiment_label"]
            .astype(str)
            .str.capitalize()
            .replace({"Positiva": "Positive", "Negativa": "Negative", "Neutra": "Neutral"})
            .value_counts()
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Positive", int(counts.get("Positive", 0)))
        c2.metric("Neutral",  int(counts.get("Neutral", 0)))
        c3.metric("Negative", int(counts.get("Negative", 0)))

        for _, row in articles.head(12).iterrows():
            title = row.get("title") or "(untitled)"
            source = row.get("source") or ""
            published = row.get("published")
            if pd.notna(published):
                try:
                    pub_str = pd.to_datetime(published).date().isoformat()
                except Exception:
                    pub_str = str(published)
            else:
                pub_str = ""

            badge = {
                "Positive": "✅ Positive",
                "Neutral":  "• Neutral",
                "Negative": "⛔ Negative",
            }.get(str(row.get("sentiment_label")).capitalize(), "• Neutral")

            link = row.get("ext_link")
            link_md = f"[open]({link})" if isinstance(link, str) and len(link) > 0 else "*no link*"

            st.markdown(f"**{title}**  \n{source} · {pub_str} · {badge}  \n{link_md}")
            st.divider()

# Footer
st.caption("If any block is empty, try another ticker or expand the period (e.g., 1y).")
