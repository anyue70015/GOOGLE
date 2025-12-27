import streamlit as st
import requests
import numpy as np
import pandas as pd
import time

# ==================== 1. 绝对锁定的底层引擎 (1:1 搬运你的基准版) ====================
class ScienceEngine:
    @staticmethod
    def ema(x, span):
        alpha = 2 / (span + 1)
        ema = np.empty_like(x)
        ema[0] = x[0]
        for i in range(1, len(x)):
            ema[i] = alpha * x[i] + (1 - alpha) * ema[i-1]
        return ema

    @staticmethod
    def rolling_mean(x, window):
        if len(x) < window: return np.full_like(x, np.nanmean(x) if not np.isnan(x).all() else 0)
        cumsum = np.cumsum(np.insert(x, 0, 0.0))
        ma = (cumsum[window:] - cumsum[:-window]) / window
        return np.concatenate([np.full(window-1, ma[0]), ma])

    @staticmethod
    def compute_metrics(close, high, low, volume):
        # 严格对齐你的 5 维模型
        e12, e26 = ScienceEngine.ema(close, 12), ScienceEngine.ema(close, 26)
        macd_hist = (e12 - e26) - ScienceEngine.ema(e12 - e26, 9)
        
        # RSI
        delta = np.diff(close, prepend=close[0])
        g, l = np.where(delta > 0, delta, 0.0), np.where(delta < 0, -delta, 0.0)
        ge, le = np.empty_like(g), np.empty_like(l)
        ge[0], le[0] = g[0], l[0]
        for i in range(1, len(g)):
            ge[i] = 0.0714 * g[i] + 0.9286 * ge[i-1] # 1/14 alpha
            le[i] = 0.0714 * l[i] + 0.9286 * le[i-1]
        rsi = 100 - (100 / (1 + (ge / (le + 1e-9))))

        # ATR & OBV
        pc = np.roll(close, 1); pc[0] = close[0]
        tr = np.maximum(high - low, np.maximum(np.abs(high - pc), np.abs(low - pc)))
        atr = np.empty_like(tr); atr[0] = tr[0]
        for i in range(1, len(tr)): atr[i] = 0.0714 * tr[i] + 0.9286 * atr[i-1]
        obv = np.cumsum(np.sign(np.diff(close, prepend=close[0])) * volume)

        # MA 对齐
        vma, ama, oma = ScienceEngine.rolling_mean(volume, 20), ScienceEngine.rolling_mean(atr, 20), ScienceEngine.rolling_mean(obv, 20)
        
        # 信号矩阵
        s1 = (macd_hist > 0).astype(int)
        s2 = (volume > vma * 1.1).astype(int)
        s3 = (rsi >= 60).astype(int)
        s4 = (atr > ama * 1.1).astype(int)
        s5 = (obv > oma * 1.05).astype(int)
        score_arr = s1 + s2 + s3 + s4 + s5
        
        # 严格执行回测切片 [:-1]
        c_bt, s_bt = close[:-1], score_arr[:-1]
        idx = np.where(s_bt[:-7] >= 3)[0]
        if len(idx) > 0:
            rets = c_bt[idx + 7] / c_bt[idx] - 1
            prob7, pf7 = (rets > 0).mean(), rets[rets > 0].sum() / abs(rets[rets <= 0].sum() + 1e-9)
        else: prob7, pf7 = 0.5, 0.0
        
        return score_arr[-1], prob7, pf7

# ==================== 2. 执行与展示逻辑 ====================
st.title("🛡️ 绝对数据同步 - 科学实战版")

# 强制锁定 1y 范围，确保与你的基准工具在同一个时间平面
RANGE = "1y"

@st.cache_data(ttl=3600)
def get_clean_data(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={RANGE}&interval=1d"
    try:
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=15).json()
        q = r["chart"]["result"][0]["indicators"]["quote"][0]
        c, h, l, v = np.array(q["close"]), np.array(q["high"]), np.array(q["low"]), np.array(q["volume"])
        m = ~np.isnan(c)
        return c[m], h[m], l[m], v[m]
    except: return None

# 核心计算流程
def run_scan(sym):
    data = get_clean_data(sym)
    if data is None or len(data[0]) < 100: return None
    c, h, l, v = data
    score, prob7, pf7 = ScienceEngine.compute_metrics(c, h, l, v)
    chg3 = [(c[-1]/c[-2]-1)*100, (c[-2]/c[-3]-1)*100, (c[-3]/c[-4]-1)*100]
    return {"symbol": sym, "price": c[-1], "score": score, "prob7": prob7, "pf7": pf7, "chg3": chg3}

# --- 界面 ---
tickers = ["SNDK", "WDC", "NVDA", "AAPL", "SLV", "GLD", "QQQ"] # 仅作示例
if 'db' not in st.session_state: st.session_state.db = []
if 'scanned' not in st.session_state: st.session_state.scanned = set()

# 筛选条件设置 (根据你的需求)
st.sidebar.subheader("筛选设置")
min_score = st.sidebar.slider("最低得分", 0, 5, 3)
min_prob = st.sidebar.slider("最低胜率", 0.0, 1.0, 0.70)
min_pf = st.sidebar.slider("最低PF7", 0.0, 10.0, 3.6)

progress = st.empty()
if len(st.session_state.scanned) < len(tickers):
    target = [t for t in tickers if t not in st.session_state.scanned][0]
    progress.info(f"正在同步计算: {target}")
    res = run_scan(target)
    if res: st.session_state.db.append(res)
    st.session_state.scanned.add(target)
    st.rerun()

# 结果展示
if st.session_state.db:
    df = pd.DataFrame(st.session_state.db)
    # 同时满足三个严苛条件
    refined = df[(df['score'] >= min_score) & (df['prob7'] >= min_prob) & (df['pf7'] >= min_pf)]
    
    st.subheader(f"符合科学条件的极品 (共 {len(refined)} 只)")
    st.dataframe(refined.sort_values('pf7', ascending=False))
