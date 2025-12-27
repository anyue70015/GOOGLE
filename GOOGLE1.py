import streamlit as st
import requests
import numpy as np
import pandas as pd
import time

# ==================== 1. 核心科学引擎 (严格保持不变) ====================
class ScienceEngine:
    # ... (此处省略 ScienceEngine 类，代码中必须包含你之前最信任的所有指标算法)
    # 确保包含: ema, rolling_mean, compute_metrics (带[:-1]回测切片)
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
        e12, e26 = ScienceEngine.ema(close, 12), ScienceEngine.ema(close, 26)
        macd_hist = (e12 - e26) - ScienceEngine.ema(e12 - e26, 9)
        delta = np.diff(close, prepend=close[0])
        g, l = np.where(delta > 0, delta, 0.0), np.where(delta < 0, -delta, 0.0)
        ge, le = np.empty_like(g), np.empty_like(l)
        ge[0], le[0] = g[0], l[0]
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
        s1, s2, s3, s4, s5 = (macd_hist > 0), (volume > vma * 1.1), (rsi >= 60), (atr > ama * 1.1), (obv > oma * 1.05)
        score_arr = s1.astype(int) + s2.astype(int) + s3.astype(int) + s4.astype(int) + s5.astype(int)
        c_bt, s_bt = close[:-1], score_arr[:-1]
        idx = np.where(s_bt[:-7] >= 3)[0]
        if len(idx) > 0:
            rets = c_bt[idx + 7] / c_bt[idx] - 1
            prob7, pf7 = (rets > 0).mean(), rets[rets > 0].sum() / (abs(rets[rets <= 0].sum()) + 1e-9)
        else: prob7, pf7 = 0.5, 0.0
        return score_arr[-1], prob7, pf7

# ==================== 2. 高效执行层 ====================

st.set_page_config(page_title="科学扫描-全自动版", layout="wide")
st.title("🛡️ 科学实战扫描 (全量自动化)")

# 这里是你那 500 多个硬编码的代码列表
ALL_TICKERS = ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "WDC", "SNDK", "NFLX", "AMD"] # ... 替换成你的完整 503 只

# 初始化 Session State
if 'all_results' not in st.session_state: st.session_state.all_results = []
if 'scan_index' not in st.session_state: st.session_state.scan_index = 0
if 'is_scanning' not in st.session_state: st.session_state.is_scanning = False

# 控制按钮
col1, col2 = st.sidebar.columns(2)
if col1.button("▶️ 开始扫描"): st.session_state.is_scanning = True
if col2.button("⏹️ 停止"): st.session_state.is_scanning = False

# 界面元素
progress_info = st.empty()
progress_bar = st.progress(0.0)
table_placeholder = st.empty()

# 执行扫描
if st.session_state.is_scanning and st.session_state.scan_index < len(ALL_TICKERS):
    batch_size = 5  # 每次刷新前处理 5 个，平衡实时性和稳定性
    
    current_list = ALL_TICKERS[st.session_state.scan_index : st.session_state.scan_index + batch_size]
    
    for sym in current_list:
        progress_info.info(f"正在深度分析: {sym} ({st.session_state.scan_index + 1}/{len(ALL_TICKERS)})")
        
        # 数据请求与计算
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1y&interval=1d"
        try:
            r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10).json()
            q = r["chart"]["result"][0]["indicators"]["quote"][0]
            c, h, l, v = np.array(q["close"]), np.array(q["high"]), np.array(q["low"]), np.array(q["volume"])
            mask = ~np.isnan(c)
            c, h, l, v = c[mask], h[mask], l[mask], v[mask]
            
            if len(c) >= 100:
                score, prob, pf = ScienceEngine.compute_metrics(c, h, l, v)
                st.session_state.all_results.append({
                    "代码": sym, "价格": round(c[-1], 2), "得分": score, 
                    "7日胜率": f"{prob*100:.1f}%", "PF7": round(pf, 2), "RawPF": pf, "RawProb": prob
                })
        except:
            pass
        
        st.session_state.scan_index += 1
        time.sleep(0.5) # 给 API 一点喘息时间

    # 更新进度条
    progress_bar.progress(st.session_state.scan_index / len(ALL_TICKERS))
    st.rerun() # 处理完一个 batch 后刷新界面显示结果

# --- 结果展示区 ---
if st.session_state.all_results:
    df = pd.DataFrame(st.session_state.all_results)
    # 科学筛选：PF>=3.6 或 胜率>=68%
    filtered = df[(df['RawPF'] >= 3.6) | (df['RawProb'] >= 0.68)].sort_values("RawPF", ascending=False)
    
    with table_placeholder.container():
        st.subheader(f"📊 科学筛选结果 (已扫描: {st.session_state.scan_index})")
        st.dataframe(filtered[["代码", "价格", "得分", "7日胜率", "PF7"]], use_container_width=True)

if st.session_state.scan_index >= len(ALL_TICKERS):
    st.success("🎉 全市场扫描任务已完成！")
    st.session_state.is_scanning = False
