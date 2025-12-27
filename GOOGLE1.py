import streamlit as st
import requests
import numpy as np
import pandas as pd
import time

# ==================== 1. 科学引擎 (保持你最信任的算法) ====================
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
        # 严格执行你的 5 维共振模型
        e12, e26 = ScienceEngine.ema(close, 12), ScienceEngine.ema(close, 26)
        mh = (e12 - e26) - ScienceEngine.ema(e12 - e26, 9)
        # RSI (14)
        delta = np.diff(close, prepend=close[0])
        g, l = np.where(delta > 0, delta, 0.0), np.where(delta < 0, -delta, 0.0)
        ge, le = np.empty_like(g), np.empty_like(l); ge[0], le[0] = g[0], l[0]
        for i in range(1, len(g)):
            ge[i] = 0.0714 * g[i] + 0.9286 * ge[i-1]
            le[i] = 0.0714 * l[i] + 0.9286 * le[i-1]
        rsi = 100 - (100 / (1 + (ge / (le + 1e-9))))
        # ATR & OBV
        pc = np.roll(close, 1); pc[0] = close[0]
        tr = np.maximum(high - low, np.maximum(np.abs(high - pc), np.abs(low - pc)))
        atr = np.empty_like(tr); atr[0] = tr[0]
        for i in range(1, len(tr)): atr[i] = 0.0714 * tr[i] + 0.9286 * atr[i-1]
        obv = np.cumsum(np.sign(np.diff(close, prepend=close[0])) * volume)
        # 指标比对
        vma, ama, oma = ScienceEngine.rolling_mean(volume, 20), ScienceEngine.rolling_mean(atr, 20), ScienceEngine.rolling_mean(obv, 20)
        score_arr = (mh>0).astype(int) + (volume>vma*1.1).astype(int) + (rsi>=60).astype(int) + (atr>ama*1.1).astype(int) + (obv>oma*1.05).astype(int)
        # 回测 [:-1]
        c_bt, s_bt = close[:-1], score_arr[:-1]
        idx = np.where(s_bt[:-7] >= 3)[0]
        if len(idx) > 0:
            rets = c_bt[idx + 7] / c_bt[idx] - 1
            prob7, pf7 = (rets > 0).mean(), rets[rets > 0].sum() / (abs(rets[rets <= 0].sum()) + 1e-9)
        else: prob7, pf7 = 0.5, 0.0
        return score_arr[-1], prob7, pf7

# ==================== 2. 全量成分股 (标普500 + 纳指100 + ETF) ====================
def get_all_tickers():
    sp500 = ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "LLY", "JPM", "WMT", "V", "UNH", "MA", "XOM", "ORCL", "COST", "HD", "PG", "NFLX", "JNJ", "ABBV", "BAC", "AMD", "CRM", "ADBE", "WFC", "KO", "CVX", "MRK", "CSCO", "TMO", "ACN", "DIS", "PM", "ABT", "LIN", "MCD", "INTU", "PEP", "ORLY", "WDC", "SNDK"] # 示例，请粘贴你那503个
    ndx100 = ["ADBE", "AMD", "ABNB", "ALNY", "GOOGL", "AMZN", "ARM", "ASML", "AVGO", "CDNS", "CRWD", "DASH", "MELI", "MU", "PANW", "PDD", "PYPL", "QCOM", "SNPS", "VRTX"]
    etfs = ["SPY", "QQQ", "IWM", "XLK", "XLF", "XLE", "XLV", "SMH", "SOXX", "TQQQ", "BITO", "GLD", "SLV"]
    return sorted(list(set(sp500 + ndx100 + etfs)))

# ==================== 3. 自动扫描调度 ====================
st.set_page_config(page_title="科学全量扫描仪", layout="wide")
st.title("🛡️ 科学实战：全量自动化扫描 (标普500/纳指100/ETF)")

if 'results' not in st.session_state: st.session_state.results = []
if 'scanned_count' not in st.session_state: st.session_state.scanned_count = 0
if 'scanning' not in st.session_state: st.session_state.scanning = False

all_list = get_all_tickers()

# 侧边栏控制
st.sidebar.header("控制台")
if st.sidebar.button("🚀 开始全量自动扫描"):
    st.session_state.scanning = True
if st.sidebar.button("⏹️ 停止扫描"):
    st.session_state.scanning = False
if st.sidebar.button("🧹 清空并重置"):
    st.session_state.results = []
    st.session_state.scanned_count = 0
    st.rerun()

# 进度显示
progress_bar = st.progress(st.session_state.scanned_count / len(all_list))
status_text = st.empty()

# 【核心：自动循环逻辑】
if st.session_state.scanning and st.session_state.scanned_count < len(all_list):
    current_symbol = all_list[st.session_state.scanned_count]
    status_text.warning(f"正在扫描第 {st.session_state.scanned_count + 1} 只: {current_symbol}")
    
    # 抓取与计算
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{current_symbol}?range=1y&interval=1d"
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10).json()
        q = r["chart"]["result"][0]["indicators"]["quote"][0]
        c = np.array(q["close"], dtype=float)
        h = np.array(q["high"], dtype=float)
        l = np.array(q["low"], dtype=float)
        v = np.array(q["volume"], dtype=float)
        mask = ~np.isnan(c)
        c, h, l, v = c[mask], h[mask], l[mask], v[mask]
        
        if len(c) >= 100:
            score, prob, pf = ScienceEngine.compute_metrics(c, h, l, v)
            # 存入结果 (包含所有数据方便筛选)
            st.session_state.results.append({
                "代码": current_symbol, "价格": round(c[-1], 2), "得分": score,
                "胜率": prob, "PF7": pf, "昨日价格": c[-2]
            })
    except:
        pass
    
    st.session_state.scanned_count += 1
    time.sleep(0.2) # 防止被反爬封锁
    st.rerun() # 关键：跑完一个自动触发下一次脚本运行

# ==================== 4. 实时结果展示 ====================
if st.session_state.results:
    df = pd.DataFrame(st.session_state.results)
    # 严格按照你的筛选逻辑
    final_df = df[(df['PF7'] >= 3.6) | (df['胜率'] >= 0.68)].copy()
    
    if not final_df.empty:
        final_df = final_df.sort_values("PF7", ascending=False)
        # 格式化显示
        display_df = final_df.copy()
        display_df['胜率'] = display_df['胜率'].apply(lambda x: f"{x*100:.1f}%")
        display_df['PF7'] = display_df['PF7'].round(2)
        
        st.subheader(f"✅ 优质标的筛选结果 ({len(final_df)} 只)")
        st.dataframe(display_df[["代码", "价格", "得分", "胜率", "PF7"]], use_container_width=True)
    else:
        st.info("扫描进行中，暂未发现符合 PF7≥3.6 或 胜率≥68% 的标的...")

st.sidebar.metric("已扫描进度", f"{st.session_state.scanned_count}/{len(all_list)}")
