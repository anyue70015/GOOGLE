import streamlit as st
import requests
import numpy as np
import pandas as pd
import time

# --- 1. 核心计算函数 (严格保持科学一致性) ---
def compute_science_metrics(close, high, low, volume):
    # EMA 计算
    def get_ema(x, span):
        alpha = 2 / (span + 1)
        res = np.empty_like(x); res[0] = x[0]
        for i in range(1, len(x)): res[i] = alpha * x[i] + (1 - alpha) * res[i-1]
        return res

    # 指标计算
    e12 = get_ema(close, 12)
    e26 = get_ema(close, 26)
    macd_hist = (e12 - e26) - get_ema(e12 - e26, 9)
    
    # RSI
    delta = np.diff(close, prepend=close[0])
    g = np.where(delta > 0, delta, 0.0)
    l = np.where(delta < 0, -delta, 0.0)
    ge = np.empty_like(g); le = np.empty_like(l)
    ge[0], le[0] = g[0], l[0]
    for i in range(1, len(g)):
        ge[i] = 0.0714 * g[i] + 0.9286 * ge[i-1]
        le[i] = 0.0714 * l[i] + 0.9286 * le[i-1]
    rsi = 100 - (100 / (1 + (ge / (le + 1e-9))))

    # ATR
    pc = np.roll(close, 1); pc[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - pc), np.abs(low - pc)))
    atr = np.empty_like(tr); atr[0] = tr[0]
    for i in range(1, len(tr)): atr[i] = 0.0714 * tr[i] + 0.9286 * atr[i-1]
    
    # OBV
    obv = np.cumsum(np.sign(np.diff(close, prepend=close[0])) * volume)

    # MA 过滤
    def get_ma(x, w=20):
        if len(x) < w: return x
        cs = np.cumsum(np.insert(x, 0, 0.0))
        ma = (cs[w:] - cs[:-w]) / w
        return np.concatenate([np.full(w-1, ma[0]), ma])

    vma, ama, oma = get_ma(volume), get_ma(atr), get_ma(obv)
    
    # 5维评分
    score_arr = (macd_hist > 0).astype(int) + (volume > vma*1.1).astype(int) + \
                (rsi >= 60).astype(int) + (atr > ama*1.1).astype(int) + (obv > oma*1.05).astype(int)
    
    # 回测逻辑 [:-1] 剔除当天干扰
    c_bt, s_bt = close[:-1], score_arr[:-1]
    idx = np.where(s_bt[:-7] >= 3)[0]
    if len(idx) > 0:
        rets = c_bt[idx + 7] / c_bt[idx] - 1
        prob7 = (rets > 0).mean()
        pf7 = rets[rets > 0].sum() / (abs(rets[rets <= 0].sum()) + 1e-9)
    else:
        prob7, pf7 = 0.5, 0.0
        
    return score_arr[-1], prob7, pf7

# --- 2. 界面布局 ---
st.set_page_config(page_title="科学流水线扫描仪", layout="wide")

# 侧边栏交互区
st.sidebar.title("🔍 扫描控制中心")
ticker_input = st.sidebar.text_area("1. 粘贴股票代码 (逗号或回车分隔)", 
                                   "NVDA,AAPL,MSFT,AMZN,GOOGL,META,TSLA,AVGO,WDC,SNDK,SPY,QQQ,SOXL,TQQQ", 
                                   height=300)
min_pf = st.sidebar.slider("2. 最低 PF7 阈值", 0.0, 10.0, 3.6)
min_win = st.sidebar.slider("3. 最低胜率阈值 (%)", 0, 100, 68) / 100.0

col_a, col_b = st.sidebar.columns(2)
run_btn = col_a.button("▶️ 开始全自动扫描")
stop_btn = col_b.button("⏹️ 停止")

# --- 3. 状态管理 ---
if 'db' not in st.session_state: st.session_state.db = []
if 'curr_idx' not in st.session_state: st.session_state.curr_idx = 0
if 'is_running' not in st.session_state: st.session_state.is_running = False

tickers = [s.strip().upper() for s in ticker_input.replace('\n', ',').split(',') if s.strip()]

if run_btn:
    st.session_state.db = []
    st.session_state.curr_idx = 0
    st.session_state.is_running = True
    st.rerun()

if stop_btn:
    st.session_state.is_running = False

# --- 4. 自动扫描执行体 ---
st.title("🛡️ 科学实战：流水线自动化扫描")
p_bar = st.progress(0.0)
p_text = st.empty()

if st.session_state.is_running and st.session_state.curr_idx < len(tickers):
    sym = tickers[st.session_state.curr_idx]
    p_text.warning(f"正在分析第 {st.session_state.curr_idx + 1} 只: {sym}")
    p_bar.progress((st.session_state.curr_idx + 1) / len(tickers))
    
    # 获取数据
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1y&interval=1d"
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10).json()
        q = r["chart"]["result"][0]["indicators"]["quote"][0]
        c, h, l, v = np.array(q["close"]), np.array(q["high"]), np.array(q["low"]), np.array(q["volume"])
        mask = ~np.isnan(c)
        c, h, l, v = c[mask], h[mask], l[mask], v[mask]
        
        if len(c) >= 100:
            score, prob, pf = compute_science_metrics(c, h, l, v)
            st.session_state.db.append({
                "代码": sym, "价格": round(c[-1], 2), "得分": score, "胜率": prob, "PF7": pf
            })
    except:
        pass
    
    # 自动推进到下一个
    st.session_state.curr_idx += 1
    st.rerun() # 核心：强制触发下一次运行

# --- 5. 结果实时展示 ---
if st.session_state.db:
    df = pd.DataFrame(st.session_state.db)
    # 科学筛选
    res = df[(df['PF7'] >= min_pf) | (df['胜率'] >= min_win)].copy()
    
    st.subheader(f"✅ 符合条件的优质标的 (已发现 {len(res)} 只)")
    if not res.empty:
        res['胜率'] = res['胜率'].apply(lambda x: f"{x*100:.1f}%")
        res['PF7'] = res['PF7'].round(2)
        st.table(res.sort_values("PF7", ascending=False))
    else:
        st.info("扫描中，暂未发现符合阈值的股票...")

if st.session_state.curr_idx >= len(tickers) and len(tickers) > 0:
    st.success("🎉 全量扫描已结束！")
    st.session_state.is_running = False
