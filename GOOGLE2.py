import streamlit as st
import yfinance as yf
import numpy as np
import pandas as pd
import time
import random
from datetime import datetime, timedelta

# ==================== 页面配置 ====================
st.set_page_config(page_title="短线扫描器-纯文本修正版", layout="wide")
st.title("📊 股票短线扫描 (TXT 绝对一行一个)")

# --- 周期设定 ---
END_DATE_STR = "2026-01-24"
end_dt = datetime.strptime(END_DATE_STR, "%Y-%m-%d")
start_dt = end_dt - timedelta(days=385) 
START_DATE = start_dt.strftime("%Y-%m-%d")

# ==================== 核心算法 ====================
def ema_np(x, span):
    alpha = 2 / (span + 1)
    ema = np.empty_like(x)
    ema[0] = x[0]
    for i in range(1, len(x)):
        ema[i] = alpha * x[i] + (1 - alpha) * ema[i-1]
    return ema

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

def atr_np(high, low, close, period=14):
    prev_c = np.roll(close, 1); prev_c[0] = close[0]
    tr = np.maximum(high-low, np.maximum(np.abs(high-prev_c), np.abs(low-prev_c)))
    atr = np.empty_like(tr); atr[0] = tr[0]
    alpha = 1 / period
    for i in range(1, len(tr)):
        atr[i] = alpha * tr[i] + (1 - alpha) * atr[i-1]
    return atr

def rolling_mean_np(x, window):
    return pd.Series(x).rolling(window=window, min_periods=1).mean().values

def obv_np(close, volume):
    return np.cumsum(np.sign(np.diff(close, prepend=close[0])) * volume)

def backtest_with_stats(close, score, steps=7):
    idx = np.where(score[:-steps] >= 3)[0]
    if len(idx) == 0: return 0.0, 0.0
    rets = close[idx + steps] / close[idx] - 1
    win_rate = (rets > 0).mean()
    pos_ret = rets[rets > 0].sum()
    neg_ret = abs(rets[rets <= 0].sum())
    pf = pos_ret / neg_ret if neg_ret > 0 else (9.9 if pos_ret > 0 else 0.0)
    return win_rate, pf

@st.cache_data(ttl=3600, show_spinner=False)
def compute_stock_comprehensive(symbol):
    try:
        df = yf.Ticker(symbol).history(start=START_DATE, end=END_DATE_STR, interval="1d")
        if df.empty or len(df) < 50: return None
        close, high, low, volume = df['Close'].values, df['High'].values, df['Low'].values, df['Volume'].values
        dates = df.index.strftime("%Y-%m-%d").values

        macd_hist = (ema_np(close, 12) - ema_np(close, 26)) - ema_np((ema_np(close, 12) - ema_np(close, 26)), 9)
        score_arr = (macd_hist > 0).astype(int) + \
                    (volume > rolling_mean_np(volume, 20) * 1.1).astype(int) + \
                    (rsi_np(close) >= 60).astype(int) + \
                    (atr_np(high, low, close) > rolling_mean_np(atr_np(high, low, close), 20) * 1.1).astype(int) + \
                    (obv_np(close, volume) > rolling_mean_np(obv_np(close, volume), 20) * 1.05).astype(int)

        detail_len = min(40, len(close))
        details = []
        for i in range(len(close) - detail_len, len(close)):
            sub_prob, sub_pf = backtest_with_stats(close[:i], score_arr[:i], 7)
            details.append({
                "日期": dates[i], "价格": round(close[i], 2), "得分": int(score_arr[i]),
                "胜率": f"{sub_prob*100:.1f}%", "PF7": round(sub_pf, 2), "指标": f"M{score_arr[i]}"
            })
        f_prob, f_pf = backtest_with_stats(close[:-1], score_arr[:-1], 7)
        return {"symbol": symbol.upper(), "prob7": f_prob, "pf7": f_pf, "price": close[-1], "score": int(score_arr[-1]), "details": details[::-1]}
    except: return None

# ==================== UI 展示 ====================
if 'results' not in st.session_state: st.session_state.results = []
with st.sidebar:
    file = st.file_uploader("上传代码 TXT", type=["txt"])
    if st.button("清空"): st.session_state.results = []

if file:
    tickers = list(dict.fromkeys([t.strip().upper() for t in file.read().decode().split() if t.strip()]))
    if st.button("开始分析"):
        for s in tickers:
            res = compute_stock_comprehensive(s)
            if res: st.session_state.results.append(res)

if st.session_state.results:
    df_main = pd.DataFrame(st.session_state.results).sort_values("pf7", ascending=False)
    st.dataframe(df_main[["symbol", "pf7", "prob7", "score", "price"]], use_container_width=True)

    # --- 汇总下载 (纯 TXT 格式，强制换行) ---
    summary_txt = "代码       PF7       胜率       得分       现价\n"
    summary_txt += "-------------------------------------------\n"
    for _, r in df_main.iterrows():
        # 使用固定的列宽，并在末尾加 \r\n 确保 Windows 记事本强制换行
        line = f"{r['symbol']:<10} {r['pf7']:<10.2f} {r['prob7']*100:<10.1f}% {r['score']:<10} {r['price']:<10.2f}\r\n"
        summary_txt += line
    
    st.download_button("📥 下载汇总排行榜 (纯 TXT)", summary_txt, file_name="Summary.txt")

    st.divider()
    selected = st.selectbox("选择股票查看 40 日明细", options=df_main["symbol"].tolist())
    if selected:
        res_data = next(r for r in st.session_state.results if r['symbol'] == selected)
        df_detail = pd.DataFrame(res_data['details'])
        
        # --- 逐日明细下载 (纯 TXT 格式，强制换行) ---
        detail_txt = f"股票: {selected} 最近 40 日明细\n"
        detail_txt += "日期         价格     得分     胜率     PF7\n"
        detail_txt += "-------------------------------------------\n"
        for _, d in df_detail.iterrows():
            d_line = f"{d['日期']:<12} {d['价格']:<8.2f} {d['得分']:<8} {d['胜率']:<8} {d['PF7']:<8.2f}\r\n"
            detail_txt += d_line
        
        st.download_button(f"📥 下载 {selected} 逐日明细 (纯 TXT)", detail_txt, file_name=f"{selected}_Detail.txt")
        st.table(df_detail)
