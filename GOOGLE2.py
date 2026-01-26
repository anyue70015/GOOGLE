import streamlit as st
import yfinance as yf
import numpy as np
import pandas as pd
import time
import random
from datetime import datetime, timedelta

# ==================== 页面配置 ====================
st.set_page_config(page_title="短线扫描器-增强版", layout="wide")
st.title("📊 股票短线深度扫描 (支持双向下载)")

# --- 周期设定 ---
END_DATE_STR = "2026-01-24"
end_dt = datetime.strptime(END_DATE_STR, "%Y-%m-%d")
start_dt = end_dt - timedelta(days=385) 
START_DATE = start_dt.strftime("%Y-%m-%d")

st.info(f"📅 测算周期：{START_DATE} 至 {END_DATE_STR}")

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

# ==================== 抓取与分析 ====================
@st.cache_data(ttl=3600, show_spinner=False)
def compute_stock_comprehensive(symbol):
    try:
        df = yf.Ticker(symbol).history(start=START_DATE, end=END_DATE_STR, interval="1d")
        if df.empty or len(df) < 50: return None
        
        close = df['Close'].values.astype(float)
        high = df['High'].values.astype(float)
        low = df['Low'].values.astype(float)
        volume = df['Volume'].values.astype(float)
        dates = df.index.strftime("%Y-%m-%d").values

        macd_line = ema_np(close, 12) - ema_np(close, 26)
        macd_hist = macd_line - ema_np(macd_line, 9)
        rsi = rsi_np(close)
        atr = atr_np(high, low, close)
        obv = obv_np(close, volume)
        vol_ma20 = rolling_mean_np(volume, 20)
        atr_ma20 = rolling_mean_np(atr, 20)
        obv_ma20 = rolling_mean_np(obv, 20)

        sig_macd = (macd_hist > 0).astype(int)
        sig_vol = (volume > vol_ma20 * 1.1).astype(int)
        sig_rsi = (rsi >= 60).astype(int)
        sig_atr = (atr > atr_ma20 * 1.1).astype(int)
        sig_obv = (obv > obv_ma20 * 1.05).astype(int)
        score_arr = sig_macd + sig_vol + sig_rsi + sig_atr + sig_obv

        detail_len = min(40, len(close))
        details = []
        for i in range(len(close) - detail_len, len(close)):
            sub_prob, sub_pf = backtest_with_stats(close[:i], score_arr[:i], 7)
            chg = (close[i]/close[i-1]-1)*100 if i > 0 else 0
            details.append({
                "日期": dates[i],
                "价格": round(close[i], 2),
                "涨跌": f"{chg:+.2f}%",
                "得分": int(score_arr[i]),
                "当日胜率": f"{sub_prob*100:.1f}%",
                "当日PF7": round(sub_pf, 2),
                "指标": f"M:{sig_macd[i]}|V:{sig_vol[i]}|R:{sig_rsi[i]}|A:{sig_atr[i]}|O:{sig_obv[i]}"
            })

        final_prob, final_pf = backtest_with_stats(close[:-1], score_arr[:-1], 7)
        return {
            "symbol": symbol.upper(),
            "prob7": final_prob,
            "pf7": final_pf,
            "current_price": close[-1],
            "last_score": int(score_arr[-1]),
            "details": details[::-1]
        }
    except: return None

# ==================== UI 展示 ====================
if 'results' not in st.session_state: st.session_state.results = []

with st.sidebar:
    file = st.file_uploader("上传代码 TXT", type=["txt"])
    if st.button("🗑️ 清空"):
        st.session_state.results = []
        st.rerun()

if not file: st.stop()

tickers = list(dict.fromkeys([t.strip().upper() for t in file.read().decode().replace(","," ").split() if t.strip()]))

if st.button("🚀 开始分析"):
    for s in tickers:
        res = compute_stock_comprehensive(s)
        if res: st.session_state.results.append(res)

if st.session_state.results:
    # 1. 年度排行榜
    df_main = pd.DataFrame([
        {
            "代码": r['symbol'], 
            "PF7(年)": r['pf7'], 
            "7日胜率(年)": f"{r['prob7']*100:.1f}%", 
            "最新5指得分": r['last_score'],
            "现价": r['current_price']
        } for r in st.session_state.results
    ]).sort_values("PF7(年)", ascending=False)

    st.subheader("🏆 年度排行榜 (按 PF7 排序)")
    st.dataframe(df_main, use_container_width=True)

    # 2. 下载汇总报告
    txt_summary = f"{'代码':<10} | {'胜率':<10} | {'PF7':<10} | {'得分':<10} | {'现价':<10}\n" + "-"*55 + "\n"
    for _, row in df_main.iterrows():
        txt_summary += f"{row['代码']:<10} | {row['7日胜率(年)']:<10} | {row['PF7(年)']:<10.2f} | {row['最新5指得分']:<10} | {row['现价']:<10.2f}\n"
    
    st.download_button("📥 下载汇总排行榜 (TXT)", txt_summary, file_name="Summary_Report.txt")

    st.divider()

    # 3. 逐日明细及详情下载
    st.subheader("🔍 40日逐日明细统计")
    sorted_tickers = df_main["代码"].tolist()
    selected = st.selectbox("选择要分析的股票 (已按 PF7 排序)", options=sorted_tickers)
    
    if selected:
        res_data = next(r for r in st.session_state.results if r['symbol'] == selected)
        df_detail = pd.DataFrame(res_data['details'])
        
        # --- 详情下载逻辑 ---
        detail_txt = f"股票代码: {selected} | 最近40个交易日逐日统计\n"
        detail_txt += f"{'日期':<12} | {'价格':<8} | {'涨跌':<8} | {'得分':<5} | {'胜率':<8} | {'PF7':<8} | {'指标细节'}\n"
        detail_txt += "-"*80 + "\n"
        for _, d in df_detail.iterrows():
            detail_txt += f"{d['日期']:<12} | {d['价格']:<8.2f} | {d['涨跌']:<8} | {d['得分']:<5} | {d['当日胜率']:<8} | {d['当日PF7']:<8.2f} | {d['指标']}\n"
        
        col1, col2 = st.columns([3, 1])
        with col2:
            st.download_button(f"📥 下载 {selected} 逐日明细", detail_txt, file_name=f"{selected}_daily_details.txt")
        
        with col1:
            st.write(f"当前查看：**{selected}**")

        st.table(df_detail.style.background_gradient(subset=["得分"], cmap="YlGn"))

st.caption("提示：汇总报告与逐日明细均已优化为一行一个记录，方便记事本直接查看。")
