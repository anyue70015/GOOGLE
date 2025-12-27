import streamlit as st
import requests
import numpy as np
import pandas as pd
import time

# ==================== 1. 核心科学引擎 (严格保持你最信任的算法) ====================
class ScienceEngine:
    @staticmethod
    def ema(x, span):
        alpha = 2 / (span + 1)
        ema = np.empty_like(x); ema[0] = x[0]
        for i in range(1, len(x)): ema[i] = alpha * x[i] + (1 - alpha) * ema[i-1]
        return ema

    @staticmethod
    def rolling_mean(x, window):
        if len(x) < window: return np.full_like(x, np.nanmean(x) if not np.isnan(x).all() else 0)
        cs = np.cumsum(np.insert(x, 0, 0.0))
        ma = (cs[window:] - cs[:-window]) / window
        return np.concatenate([np.full(window-1, ma[0]), ma])

    @staticmethod
    def compute_metrics(close, high, low, volume):
        e12, e26 = ScienceEngine.ema(close, 12), ScienceEngine.ema(close, 26)
        mh = (e12 - e26) - ScienceEngine.ema(e12 - e26, 9)
        delta = np.diff(close, prepend=close[0])
        g, l = np.where(delta > 0, delta, 0.0), np.where(delta < 0, -delta, 0.0)
        ge, le = np.empty_like(g), np.empty_like(l); ge[0], le[0] = g[0], l[0]
        for i in range(1, len(g)):
            ge[i] = 0.0714 * g[i] + 0.9286 * ge[i-1]
            le[i] = 0.0714 * l[i] + 0.9286 * le[i-1]
        rsi = 100 - (100 / (1 + (ge / (le + 1e-9))))
        pc = np.roll(close, 1); pc[0] = close[0]
        tr = np.maximum(high - low, np.maximum(np.abs(high - pc), np.abs(low - pc)))
        atr = np.empty_like(tr); atr[0] = tr[0]
        for i in range(1, len(tr)): atr[i] = 0.0714 * tr[i] + 0.9286 * atr[i-1]
        obv = np.cumsum(np.sign(np.diff(close, prepend=close[0])) * volume)
        vma, ama, oma = ScienceEngine.rolling_mean(volume, 20), ScienceEngine.rolling_mean(atr, 20), ScienceEngine.rolling_mean(obv, 20)
        score_arr = (mh>0).astype(int) + (volume>vma*1.1).astype(int) + (rsi>=60).astype(int) + (atr>ama*1.1).astype(int) + (obv>oma*1.05).astype(int)
        c_bt, s_bt = close[:-1], score_arr[:-1]
        idx = np.where(s_bt[:-7] >= 3)[0]
        if len(idx) > 0:
            rets = c_bt[idx + 7] / c_bt[idx] - 1
            prob7, pf7 = (rets > 0).mean(), rets[rets > 0].sum() / (abs(rets[rets <= 0].sum()) + 1e-9)
        else: prob7, pf7 = 0.5, 0.0
        return score_arr[-1], prob7, pf7

# ==================== 2. 界面与配置 ====================
st.set_page_config(page_title="科学全量扫描仪", layout="wide")
st.title("🛡️ 科学实战：全量自动扫描系统")

# 初始化状态 (State)
if 'results' not in st.session_state: st.session_state.results = []
if 'idx' not in st.session_state: st.session_state.idx = 0
if 'scanning' not in st.session_state: st.session_state.scanning = False

# --- 侧边栏：输入与控制 ---
st.sidebar.header("🔍 扫描配置")

# 1. 股票名侧边栏输入 (默认填入一些，支持手动修改)
default_tickers = "NVDA,AAPL,MSFT,AMZN,GOOGL,META,TSLA,AVGO,WDC,SNDK,SPY,QQQ,SOXL,TQQQ"
input_tickers = st.sidebar.text_area("输入股票代码 (逗号或换行分隔)", default_tickers, height=200)

# 解析输入内容
ticker_list = [s.strip().upper() for s in input_tickers.replace('\n', ',').split(',') if s.strip()]

# 2. 筛选闸门
st.sidebar.subheader("⚙️ 筛选阈值")
min_pf = st.sidebar.number_input("最低 PF7", value=3.6, step=0.1)
min_prob = st.sidebar.number_input("最低胜率 (%)", value=68.0, step=1.0) / 100

# 3. 扫描控制按钮
col1, col2 = st.sidebar.columns(2)
start_btn = col1.button("🚀 开始扫描")
stop_btn = col2.button("⏹️ 停止")

if start_btn:
    st.session_state.scanning = True
    st.session_state.idx = 0
    st.session_state.results = []
    st.rerun()

if stop_btn:
    st.session_state.scanning = False

# ==================== 3. 扫描执行核心 ====================
progress_bar = st.progress(0.0)
status_placeholder = st.empty()

if st.session_state.scanning and st.session_state.idx < len(ticker_list):
    sym = ticker_list[st.session_state.idx]
    status_placeholder.info(f"正在分析: {sym} ({st.session_state.idx + 1}/{len(ticker_list)})")
    progress_bar.progress((st.session_state.idx + 1) / len(ticker_list))
    
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1y&interval=1d"
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10).json()
        q = r["chart"]["result"][0]["indicators"]["quote"][0]
        c, h, l, v = np.array(q["close"]), np.array(q["high"]), np.array(q["low"]), np.array(q["volume"])
        mask = ~np.isnan(c)
        c, h, l, v = c[mask], h[mask], l[mask], v[mask]
        
        if len(c) >= 100:
            score, prob, pf = ScienceEngine.compute_metrics(c, h, l, v)
            st.session_state.results.append({
                "代码": sym, "价格": round(c[-1], 2), "得分": score,
                "胜率": prob, "PF7": pf
            })
    except: pass
    
    st.session_state.idx += 1
    time.sleep(0.05)
    st.rerun()  # 关键：这行保证它会自动跳到下一个

# ==================== 4. 实时表格展示 ====================
if st.session_state.results:
    df = pd.DataFrame(st.session_state.results)
    # 按照侧边栏设定的阈值实时筛选
    filtered = df[(df['PF7'] >= min_pf) | (df['胜率'] >= min_prob)].copy()
    
    st.subheader(f"📊 发现符合条件标的: {len(filtered)} 只")
    
    if not filtered.empty:
        # 美化格式
        filtered['胜率'] = filtered['胜率'].apply(lambda x: f"{x*100:.1f}%")
        filtered['PF7'] = filtered['PF7'].round(2)
        st.dataframe(filtered.sort_values("PF7", ascending=False), use_container_width=True)
    else:
        st.write("暂未发现符合条件的标的，扫描继续中...")

if st.session_state.idx >= len(ticker_list) and len(ticker_list) > 0:
    st.success("🎉 扫描任务全部完成！")
    st.session_state.scanning = False
