import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO

# ==================== 1. 核心算法逻辑 (严格对齐你的基准版) ====================
def ema_np(x, span):
    alpha = 2 / (span + 1)
    ema = np.empty_like(x)
    ema[0] = x[0]
    for i in range(1, len(x)):
        ema[i] = alpha * x[i] + (1 - alpha) * ema[i-1]
    return ema

def macd_hist_np(close):
    e12, e26 = ema_np(close, 12), ema_np(close, 26)
    macd_line = e12 - e26
    return macd_line - ema_np(macd_line, 9)

def rsi_np(close, period=14):
    delta = np.diff(close, prepend=close[0])
    gain, loss = np.where(delta > 0, delta, 0.0), np.where(delta < 0, -delta, 0.0)
    alpha = 1 / period
    ge, le = np.empty_like(gain), np.empty_like(loss)
    ge[0], le[0] = gain[0], loss[0]
    for i in range(1, len(gain)):
        ge[i] = alpha * gain[i] + (1 - alpha) * ge[i-1]
        le[i] = alpha * loss[i] + (1 - alpha) * le[i-1]
    return 100 - (100 / (1 + (ge / (le + 1e-9))))

def atr_np(high, low, close, period=14):
    pc = np.roll(close, 1); pc[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - pc), np.abs(low - pc)))
    atr, alpha = np.empty_like(tr), 1 / period
    atr[0] = tr[0]
    for i in range(1, len(tr)): atr[i] = alpha * tr[i] + (1 - alpha) * atr[i-1]
    return atr

def rolling_mean_np(x, window):
    if len(x) < window: return np.full_like(x, np.nanmean(x) if not np.isnan(x).all() else 0)
    cs = np.cumsum(np.insert(x, 0, 0.0))
    ma = (cs[window:] - cs[:-window]) / window
    return np.concatenate([np.full(window-1, ma[0]), ma])

def obv_np(close, volume):
    direction = np.sign(np.diff(close, prepend=close[0]))
    return np.cumsum(direction * volume)

def backtest_with_stats(close, score, steps):
    if len(close) <= steps + 1: return 0.5, 0.0
    idx = np.where(score[:-steps] >= 3)[0] # 科学入场阈值：3分
    if len(idx) == 0: return 0.5, 0.0
    rets = close[idx + steps] / close[idx] - 1
    win_rate = (rets > 0).mean()
    pf = rets[rets > 0].sum() / abs(rets[rets <= 0].sum()) if (rets <= 0).any() else 9.99
    return win_rate, pf

# ==================== 2. 界面与执行逻辑 ====================
st.set_page_config(page_title="极品短线-科学终极版", layout="wide")
st.title("🎯 极品短线：科学筛选 (PF7≥3.6 & 胜率≥70% & 得分≥3)")

# 侧边栏：参数与筛选
st.sidebar.header("配置中心")
mode = st.sidebar.selectbox("回测周期", ["3mo", "6mo", "1y", "2y"], index=2)
strict_mode = st.sidebar.checkbox("🚀 仅看超级精选 (PF≥3.6 & Score≥3)", value=True)

# 容器准备
status_box = st.empty()
progress_bar = st.progress(0)

@st.cache_data(ttl=3600)
def fetch_data(symbol, range_str):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range_str}&interval=1d"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15).json()
        d = r["chart"]["result"][0]
        q = d["indicators"]["quote"][0]
        c, h, l, v = np.array(q["close"]), np.array(q["high"]), np.array(q["low"]), np.array(q["volume"])
        m = ~np.isnan(c); return c[m], h[m], l[m], v[m]
    except: return None

def compute_all(sym, rng):
    data = fetch_data(sym, rng)
    if data is None or len(data[0]) < 100: return None
    c, h, l, v = data
    
    mh, rsi, atr, obv = macd_hist_np(c), rsi_np(c), atr_np(h, l, c), obv_np(c, v)
    vma, ama, oma = rolling_mean_np(v, 20), rolling_mean_np(atr, 20), rolling_mean_np(obv, 20)
    
    # 当前得分 (5维动力模型)
    sigs = [(mh[-1]>0), (v[-1]>vma[-1]*1.1), (rsi[-1]>=60), (atr[-1]>ama[-1]*1.1), (obv[-1]>oma[-1]*1.05)]
    score = sum(sigs)
    
    # 历史序列回测 (严格切片保持一致性)
    s_hist = (mh>0).astype(int)+(v>vma*1.1).astype(int)+(rsi>=60).astype(int)+(atr>ama*1.1).astype(int)+(obv>oma*1.05).astype(int)
    prob7, pf7 = backtest_with_stats(c[:-1], s_hist[:-1], 7)
    
    # 近3日波动雷达
    chg3 = [(c[-1]/c[-2]-1)*100, (c[-2]/c[-3]-1)*100, (c[-3]/c[-4]-1)*100] if len(c)>4 else [0,0,0]
    
    return {"symbol": sym, "price": c[-1], "score": score, "prob7": prob7, "pf7": pf7, "chg3": chg3}

# ==================== 3. 扫描执行 ====================
if 'results' not in st.session_state: st.session_state.results = []
if 'done' not in st.session_state: st.session_state.done = set()

tickers = ["SNDK", "WDC", "NVDA", "AAPL", "SLV", "GLD", "QQQ", "SPY", "AMD", "MSFT", "TSLA", "PLTR", "SOXL"] # 更多可按需添加

if len(st.session_state.done) < len(tickers):
    rem = [s for s in tickers if s not in st.session_state.done]
    s = rem[0]
    status_box.info(f"正在科学计算: {s} ({len(st.session_state.done)+1}/{len(tickers)})")
    progress_bar.progress((len(st.session_state.done)+1)/len(tickers))
    
    res = compute_all(s, mode)
    if res: st.session_state.results.append(res)
    st.session_state.done.add(s)
    st.rerun()
else:
    status_box.success("✅ 全市场科学扫描完成")
    progress_bar.empty()

# ==================== 4. 科学展示层 ====================
if st.session_state.results:
    df = pd.DataFrame(st.session_state.results)
    df = df.sort_values(['score', 'pf7'], ascending=False)
    
    # 科学筛选
    if strict_mode:
        show_df = df[(df['pf7'] >= 3.6) & (df['prob7'] >= 0.70) & (df['score'] >= 3)].copy()
        st.subheader(f"💎 超级精选 (共 {len(show_df)} 只)")
    else:
        show_df = df[(df['pf7'] >= 3.6) | (df['prob7'] >= 0.68)].copy()
        st.subheader(f"🔥 全量精选 (共 {len(show_df)} 只)")

    for _, row in show_df.iterrows():
        c3 = row['chg3']
        # 三日雷达：判断是起涨还是超买
        radar = f"<span style='color:{'#ff4b4b' if c3[0]>0 else '#00ff41'}'>{c3[0]:+.2f}%</span>, " \
                f"{c3[1]:+.2f}%, {c3[2]:+.2f}%"
        
        st.markdown(f"""
        <div style="border-left: 8px solid #FF4B4B; padding: 15px; margin: 10px 0; background-color: #1E1E1E; border-radius: 5px;">
            <span style="font-size:22px; font-weight:bold; color:white;">{row['symbol']}</span> 
            <span style="margin-left:20px; color:#AAA;">价格: ${row['price']:.2f}</span>
            <hr style="margin: 10px 0; border: 0.5px solid #333;">
            <div style="display: flex; justify-content: space-between;">
                <div><b>得分: {row['score']}/5</b> (MACD/VOL/RSI/ATR/OBV)</div>
                <div><b>7日胜率: <span style="color:#FFD700;">{row['prob7']*100:.1f}%</span></b></div>
                <div><b>PF7盈利比: <span style="color:#FFD700;">{row['pf7']:.2f}</span></b></div>
            </div>
            <div style="margin-top:10px; font-size:13px; color:#888;">
                📊 动力雷达 (T-0, T-1, T-2): {radar}
            </div>
        </div>
        """, unsafe_allow_html=True)

if st.button("🔄 重置计算"):
    st.session_state.results, st.session_state.done = [], set(); st.rerun()
