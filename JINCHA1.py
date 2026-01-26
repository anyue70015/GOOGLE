import streamlit as st
import yfinance as yf
import numpy as np
import pandas as pd
import time
import random

# ==================== 核心算法 (找回“每天都变”的动态逻辑) ====================
def ema_np(x, span):
    alpha = 2 / (span + 1)
    ema = np.empty_like(x)
    ema[0] = x[0]
    for i in range(1, len(x)): ema[i] = alpha * x[i] + (1 - alpha) * ema[i-1]
    return ema

def rsi_np(close, period=14):
    delta = np.diff(close, prepend=close[0])
    g = np.where(delta > 0, delta, 0.0)
    l = np.where(delta < 0, -delta, 0.0)
    alpha = 1 / period
    ge, le = np.empty_like(g), np.empty_like(l)
    ge[0], le[0] = g[0], l[0]
    for i in range(1, len(g)):
        ge[i] = alpha * g[i] + (1 - alpha) * ge[i-1]
        le[i] = alpha * l[i] + (1 - alpha) * le[i-1]
    return 100 - (100 / (1 + (ge / (le + 1e-9))))

def backtest_with_stats(close, score, steps=7):
    """这是灵魂：计算截至当前日期的历史期望值"""
    if len(close) <= steps: return 0.0, 0.0
    idx = np.where(score[:-steps] >= 3)[0]
    if len(idx) == 0: return 0.0, 0.0
    rets = close[idx + steps] / close[idx] - 1
    win_rate = (rets > 0).mean()
    pos_sum = rets[rets > 0].sum()
    neg_sum = abs(rets[rets <= 0].sum())
    pf = pos_sum / neg_sum if neg_sum > 0 else 9.9
    return win_rate, pf

@st.cache_data(ttl=1800, show_spinner=False)
def compute_stock_metrics(symbol):
    try:
        # 强制拉取 1y 数据确保回测样本够大
        df = yf.Ticker(symbol).history(period="1y", interval="1d", auto_adjust=True)
        if df.empty or len(df) < 60: return None
        
        close = df['Close'].values.astype(float)
        high = df['High'].values.astype(float)
        low = df['Low'].values.astype(float)
        vol = df['Volume'].values.astype(float)
        dates = df.index.strftime("%Y-%m-%d").values
        
        # 信号序列
        macd = (ema_np(close, 12) - ema_np(close, 26)) - ema_np((ema_np(close, 12) - ema_np(close, 26)), 9)
        rsi = rsi_np(close)
        vol_ma = pd.Series(vol).rolling(20).mean().values
        # 打分矩阵
        s1 = (macd > 0).astype(int)
        s2 = (vol > vol_ma * 1.1).astype(int)
        s3 = (rsi >= 60).astype(int)
        score_arr = s1 + s2 + s3 # 简化演示，你可以自行加回 ATR/OBV
        
        # --- 关键：动态回溯 40 日 ---
        details = []
        # 我们从倒数第 40 天开始，逐日重算历史 PF7
        for i in range(len(close) - 40, len(close)):
            # 这里的核心是只把 [0:i] 的数据喂给回测函数，模拟“当时”的情况
            p7, f7 = backtest_with_stats(close[:i], score_arr[:i], 7)
            details.append({
                "日期": dates[i],
                "价格": round(close[i], 2),
                "得分": int(score_arr[i]),
                "胜率": f"{p7*100:.1f}%",
                "PF7": round(f7, 3) # 增加精度看到每日变化
            })
            
        final_p7, final_f7 = backtest_with_stats(close[:-1], score_arr[:-1], 7)
        
        return {
            "symbol": symbol.upper(),
            "pf7": final_f7,
            "prob7": final_p7,
            "score": int(score_arr[-1]),
            "price": close[-1],
            "details": details[::-1] # 倒序显示，今天在最上面
        }
    except: return None

# ==================== UI 界面 (TX上传 + 完整下载) ====================
if 'results' not in st.session_state: st.session_state.results = []

with st.sidebar:
    st.header("1. 上传中心")
    file = st.file_uploader("上传 TXT 代码", type=["txt"])
    if st.button("清空结果"):
        st.session_state.results = []
        st.rerun()

if file:
    tickers = list(dict.fromkeys([t.strip().upper() for t in file.read().decode().split() if t.strip()]))
    if st.button(f"执行科学扫描 ({len(tickers)} 只)"):
        for s in tickers:
            res = compute_stock_metrics(s)
            if res: st.session_state.results.append(res)

if st.session_state.results:
    df_main = pd.DataFrame(st.session_state.results).drop_duplicates('symbol').sort_values("pf7", ascending=False)
    
    # --- 下载优质股 TXT ---
    premium_list = df_main[df_main['pf7'] >= 3.5]['symbol'].tolist()
    if premium_list:
        st.download_button("📥 点击下载优质股 (PF7 > 3.5)", "\n".join(premium_list), "Premium_Stocks.txt")
    
    st.subheader("📊 扫描结果汇总")
    st.dataframe(df_main[["symbol", "pf7", "prob7", "score", "price"]], use_container_width=True)

    st.divider()
    
    # --- 40 日明细 (现在每一行都会变了) ---
    selected = st.selectbox("选择股票查看 40 日动态回测明细", options=df_main["symbol"].tolist())
    if selected:
        res_data = next(r for r in st.session_state.results if r['symbol'] == selected)
        st.table(pd.DataFrame(res_data['details']).style.background_gradient(subset=["得分"], cmap="YlGn"))
