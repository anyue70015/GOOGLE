import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO

st.set_page_config(page_title="极品短线-实战精选版", layout="wide")
st.title("🎯 极品短线扫描 (得分 > 胜率 > PF7)")

# ==================== 核心常量 ====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

BACKTEST_CONFIG = {
    "3个月": {"range": "3mo", "interval": "1d"},
    "6个月": {"range": "6mo", "interval": "1d"},
    "1年":  {"range": "1y",  "interval": "1d"},
    "3年":  {"range": "3y",  "interval": "1d"},
}

CORE_ETFS = ["SPY", "QQQ", "IWM", "DIA", "SLV", "GLD", "GDX", "TLT", "SOXX", "SMH", "KWEB", "BITO", "WDC", "SNDK", "NVDA", "AAPL"]

# ==================== 核心算法 ====================
def ema_np(x, span):
    alpha = 2 / (span + 1)
    ema = np.empty_like(x)
    ema[0] = x[0]
    for i in range(1, len(x)):
        ema[i] = alpha * x[i] + (1 - alpha) * ema[i-1]
    return ema

def macd_hist_np(close):
    ema12, ema26 = ema_np(close, 12), ema_np(close, 26)
    macd_line = ema12 - ema26
    return macd_line - ema_np(macd_line, 9)

def rsi_np(close, period=14):
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    alpha = 1 / period
    g_ema, l_ema = np.empty_like(gain), np.empty_like(loss)
    g_ema[0], l_ema[0] = gain[0], loss[0]
    for i in range(1, len(gain)):
        g_ema[i] = alpha * gain[i] + (1 - alpha) * g_ema[i-1]
        l_ema[i] = alpha * loss[i] + (1 - alpha) * l_ema[i-1]
    return 100 - (100 / (1 + (g_ema / (l_ema + 1e-9))))

def rolling_mean_np(x, window):
    if len(x) < window: return np.full_like(x, np.nanmean(x))
    return pd.Series(x).rolling(window).mean().values

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yahoo_ohlcv(symbol, range_str):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range_str}&interval=1d"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        d = resp.json()["chart"]["result"][0]
        q = d["indicators"]["quote"][0]
        df = pd.DataFrame({"c": q["close"], "h": q["high"], "l": q["low"], "v": q["volume"]}).dropna()
        return df[df['v'] > 0]
    except: return None

def compute_metrics(symbol, cfg_key):
    df = fetch_yahoo_ohlcv(symbol, BACKTEST_CONFIG[cfg_key]["range"])
    if df is None or len(df) < 50: return None
    c, h, l, v = df["c"].values, df["h"].values, df["l"].values, df["v"].values
    
    macd_h, rsi = macd_hist_np(c), rsi_np(c)
    vol_ma20 = rolling_mean_np(v, 20)
    
    sig_list = [
        macd_h[-1] > 0,
        v[-1] > vol_ma20[-1] * 1.1,
        rsi[-1] >= 60,
        c[-1] > rolling_mean_np(c, 20)[-1],
        (c[-1] - l[-1]) / (h[-1] - l[-1] + 1e-9) > 0.5
    ]
    score = sum(sig_list)
    
    score_hist = (macd_h > 0).astype(int) + (v > vol_ma20 * 1.1).astype(int) + (rsi >= 60).astype(int)
    idx = np.where(score_hist[:-7] >= 2)[0]
    if len(idx) > 0:
        rets = c[idx + 7] / c[idx] - 1
        prob7, pf7 = (rets > 0).mean(), rets[rets > 0].sum() / (abs(rets[rets <= 0].sum()) + 1e-9)
    else: prob7, pf7 = 0.5, 1.0
    
    return {"symbol": symbol, "price": c[-1], "score": score, "prob7": prob7, "pf7": pf7, "signals": sig_list}

# ==================== 侧边栏：单股深度穿透 ====================
st.sidebar.header("🔍 单股深度穿透")
single_sym = st.sidebar.text_input("输入代码 (如 SNDK/WDC)", "").upper()
if single_sym:
    st.sidebar.markdown(f"### {single_sym} 多周期对比")
    for p in ["3个月", "1年", "3年"]:
        m = compute_metrics(single_sym, p)
        if m:
            st.sidebar.write(f"**{p}**: 得分:{m['score']} | 胜率:{m['prob7']*100:.1f}% | PF:{m['pf7']:.2f}")
    
    st.subheader(f"🔎 {single_sym} 当前指标状态 (1年周期)")
    m_main = compute_metrics(single_sym, "1年")
    if m_main:
        cols = st.columns(5)
        labels = ["趋势(MACD)", "动力(VOL)", "强弱(RSI)", "均线(MA20)", "收盘强弱"]
        for i, col in enumerate(cols):
            if m_main['signals'][i]: col.success(f"{labels[i]} ✅")
            else: col.error(f"{labels[i]} ❌")
st.sidebar.markdown("---")

# ==================== 主逻辑：自动扫描 ====================
mode = st.selectbox("全量扫描周期", list(BACKTEST_CONFIG.keys()), index=2)

if 'high_prob' not in st.session_state: st.session_state.high_prob = []
if 'scanned' not in st.session_state: st.session_state.scanned = set()

@st.cache_data(ttl=86400)
def get_all_tickers():
    try:
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
        df = pd.read_csv(StringIO(requests.get(url).text))
        return list(set(df['Symbol'].tolist() + CORE_ETFS))
    except: return CORE_ETFS

all_tickers = get_all_tickers()
all_tickers.sort()

if len(st.session_state.scanned) < len(all_tickers):
    with st.spinner("扫描中..."):
        remaining = [s for s in all_tickers if s not in st.session_state.scanned]
        for sym in remaining:
            res = compute_metrics(sym, mode)
            if res: st.session_state.high_prob.append(res)
            st.session_state.scanned.add(sym)
            st.rerun()

# ==================== 排序与展示 (得分 > 胜率 > PF7) ====================
if st.session_state.high_prob:
    df = pd.DataFrame(st.session_state.high_prob)
    
    # 强制排序：得分优先，其次胜率，最后PF
    df_sorted = df.sort_values(
        by=['score', 'prob7', 'pf7'], 
        ascending=[False, False, False]
    )
    
    # 筛选
    df_prime = df_sorted[(df_sorted['score'] >= 3) | (df_sorted['prob7'] >= 0.68)].copy()

    st.subheader(f"🔥 精选结果 (共 {len(df_prime)} 只) - 排序：得分 > 胜率 > PF7")
    
    for _, row in df_prime.iterrows():
        border = "6px solid #00FF00" if row['score'] >= 3 else "2px solid #31333F"
        st.markdown(
            f"""<div style="border-left: {border}; padding: 10px; margin: 10px 0; background-color: #f0f2f622;">
                <span style="font-size:18px; font-weight:bold;">{row['symbol']}</span> | 
                价格: ${row['price']:.2f} | 
                <b>得分: {row['score']}/5</b> | 
                7日胜率: {row['prob7']*100:.1f}% | 
                PF7效率: {row['pf7']:.2f}
            </div>""", unsafe_allow_html=True
        )

    # 修复后的导出逻辑
    report_lines = ["--- 极品精选报告 ---"]
    for _, row in df_prime.iterrows():
        line = f"{row['symbol']}: 得分{row['score']} | 胜率{row['prob7']*100:.1f}% | PF7:{row['pf7']:.2f}"
        report_lines.append(line)
    
    final_report = "\n".join(report_lines)
    st.download_button("📥 导出精选报告", final_report.encode('utf-8'), "Report.txt")

if st.button("🔄 重置"):
    st.session_state.high_prob, st.session_state.scanned = [], set()
    st.rerun()
