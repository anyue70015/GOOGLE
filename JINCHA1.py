import streamlit as st
import yfinance as yf
import numpy as np
import pandas as pd
import time
import random

# ==================== 页面配置 ====================
st.set_page_config(page_title="短线扫描器-终极科学版", layout="wide")
st.title("📈 股票短线扫描 (Grok 核心算法整合版)")

# ==================== 核心算法 (完全迁移 Grok 计算逻辑) ====================
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
    rs = g_ema / (l_ema + 1e-9)
    return 100 - (100 / (1 + rs))

def atr_np(high, low, close, period=14):
    prev_close = np.roll(close, 1); prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = np.empty_like(tr); atr[0] = tr[0]
    alpha = 1 / period
    for i in range(1, len(tr)):
        atr[i] = alpha * tr[i] + (1 - alpha) * atr[i-1]
    return atr

def rolling_mean_np(x, window):
    # 使用 NumPy 逻辑加速
    if len(x) < window: return np.full_like(x, np.nan)
    return pd.Series(x).rolling(window=window, min_periods=1).mean().values

def backtest_with_stats(close, score, steps=7):
    """Grok 核心回测逻辑"""
    if len(close) <= steps + 1: return 0.5, 0.0
    idx = np.where(score[:-steps] >= 3)[0]
    if len(idx) == 0: return 0.5, 0.0
    rets = close[idx + steps] / close[idx] - 1
    win_rate = (rets > 0).mean()
    # PF 计算: 盈利总和 / 亏损总和
    pos_sum = rets[rets > 0].sum()
    neg_sum = abs(rets[rets <= 0].sum())
    pf = pos_sum / neg_sum if neg_sum > 0 else 999.0
    return win_rate, pf

@st.cache_data(ttl=1800, show_spinner=False)
def compute_stock_metrics(symbol, range_str="1y"):
    try:
        # 使用 Grok 的动态 period 模式
        time.sleep(random.uniform(1.5, 3))
        df = yf.Ticker(symbol).history(period=range_str, interval="1d", auto_adjust=True)
        if df.empty or len(df) < 50: return None
        
        close = df['Close'].values.astype(float)
        high = df['High'].values.astype(float)
        low = df['Low'].values.astype(float)
        volume = df['Volume'].values.astype(float)
        dates = df.index.strftime("%Y-%m-%d").values

        # 信号计算 (Grok 逻辑)
        ema12, ema26 = ema_np(close, 12), ema_np(close, 26)
        macd_line = ema12 - ema26
        signal_line = ema_np(macd_line, 9)
        macd_hist = macd_line - signal_line
        
        rsi = rsi_np(close)
        atr = atr_np(high, low, close)
        vol_ma20 = rolling_mean_np(volume, 20)
        atr_ma20 = rolling_mean_np(atr, 20)
        
        # 实时打分
        s_macd = (macd_hist > 0).astype(int)
        s_vol = (volume > vol_ma20 * 1.1).astype(int)
        s_rsi = (rsi >= 60).astype(int)
        s_atr = (atr > atr_ma20 * 1.1).astype(int)
        
        # Grok 的 OBV 逻辑
        direction = np.sign(np.diff(close, prepend=close[0]))
        obv = np.cumsum(direction * volume)
        obv_ma20 = rolling_mean_np(obv, 20)
        s_obv = (obv > obv_ma20 * 1.05).astype(int)
        
        score_arr = s_macd + s_vol + s_rsi + s_atr + s_obv
        
        # 计算 PF7 和 胜率
        prob7, pf7 = backtest_with_stats(close[:-1], score_arr[:-1], 7)
        
        # 构建 40 日明细
        details = []
        detail_len = min(40, len(close))
        for i in range(len(close) - detail_len, len(close)):
            d_prob, d_pf = backtest_with_stats(close[:i], score_arr[:i], 7)
            details.append({
                "日期": dates[i], "价格": round(close[i], 2),
                "得分": int(score_arr[i]), "胜率": f"{d_prob*100:.1f}%", "PF7": round(d_pf, 2)
            })

        return {
            "symbol": symbol.upper(), "price": close[-1], 
            "change": f"{(close[-1]/close[-2]-1)*100:+.2f}%",
            "score": int(score_arr[-1]), "prob7": prob7, "pf7": pf7,
            "details": details[::-1]
        }
    except: return None

# ==================== UI 展示 (原汁原味上传 TXT) ====================
if 'results' not in st.session_state: st.session_state.results = []

with st.sidebar:
    st.header("操作面板")
    file = st.file_uploader("上传 TXT 代码文件", type=["txt"])
    if st.button("清空所有数据"): 
        st.session_state.results = []
        st.rerun()

if file:
    tickers = list(dict.fromkeys([t.strip().upper() for t in file.read().decode().split() if t.strip()]))
    if st.button(f"开始扫描 {len(tickers)} 只股票"):
        progress_bar = st.progress(0)
        for i, s in enumerate(tickers):
            res = compute_stock_metrics(s)
            if res: st.session_state.results.append(res)
            progress_bar.progress((i + 1) / len(tickers))

if st.session_state.results:
    df_main = pd.DataFrame(st.session_state.results).drop_duplicates('symbol').sort_values("pf7", ascending=False)
    
    st.subheader("📊 扫描结果汇总 (按盈利因子 PF7 排序)")
    st.dataframe(df_main[["symbol", "pf7", "prob7", "score", "price", "change"]], use_container_width=True)

    st.divider()
    selected = st.selectbox("选择股票查看 40 日动态回测明细", options=df_main["symbol"].tolist())
    if selected:
        res_data = next(r for r in st.session_state.results if r['symbol'] == selected)
        st.table(pd.DataFrame(res_data['details']).style.background_gradient(subset=["得分"], cmap="YlGn"))
