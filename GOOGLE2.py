import streamlit as st
import yfinance as yf
import numpy as np
import pandas as pd
import time
import random
from datetime import datetime, timedelta

# ==================== 页面配置 ====================
st.set_page_config(page_title="股票短线扫描-专业版", layout="wide")
st.title("🚀 股票短线深度扫描 (逐日统计 + 下载功能)")

# --- 周期设定 ---
END_DATE_STR = "2026-01-24"
end_dt = datetime.strptime(END_DATE_STR, "%Y-%m-%d")
start_dt = end_dt - timedelta(days=385) 
START_DATE = start_dt.strftime("%Y-%m-%d")

st.info(f"📅 测算周期：{START_DATE} 至 {END_DATE_STR}")

# ==================== 核心算法函数 ====================
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
    # 得分 >= 3 视为信号点
    idx = np.where(score[:-steps] >= 3)[0]
    if len(idx) == 0: return 0.0, 0.0
    rets = close[idx + steps] / close[idx] - 1
    win_rate = (rets > 0).mean()
    pos_ret = rets[rets > 0].sum()
    neg_ret = abs(rets[rets <= 0].sum())
    pf = pos_ret / neg_ret if neg_ret > 0 else (9.9 if pos_ret > 0 else 0.0)
    return win_rate, pf

# ==================== 数据分析核心 ====================
@st.cache_data(ttl=3600, show_spinner=False)
def compute_stock_comprehensive(symbol):
    try:
        time.sleep(random.uniform(0.3, 0.6))
        df = yf.Ticker(symbol).history(start=START_DATE, end=END_DATE_STR, interval="1d")
        if df.empty or len(df) < 50: return None
        
        close = df['Close'].values.astype(float)
        high = df['High'].values.astype(float)
        low = df['Low'].values.astype(float)
        volume = df['Volume'].values.astype(float)
        dates = df.index.strftime("%Y-%m-%d").values

        # 1. 指标计算
        macd_line = ema_np(close, 12) - ema_np(close, 26)
        macd_hist = macd_line - ema_np(macd_line, 9)
        rsi = rsi_np(close)
        atr = atr_np(high, low, close)
        obv = obv_np(close, volume)
        vol_ma20 = rolling_mean_np(volume, 20)
        atr_ma20 = rolling_mean_np(atr, 20)
        obv_ma20 = rolling_mean_np(obv, 20)

        # 2. 判定信号 (您的逻辑)
        sig_macd = (macd_hist > 0).astype(int)
        sig_vol = (volume > vol_ma20 * 1.1).astype(int)
        sig_rsi = (rsi >= 60).astype(int)
        sig_atr = (atr > atr_ma20 * 1.1).astype(int)
        sig_obv = (obv > obv_ma20 * 1.05).astype(int)
        score_arr = sig_macd + sig_vol + sig_rsi + sig_atr + sig_obv

        # 3. 详情列表
        detail_len = min(40, len(close))
        details = []
        for i in range(len(close) - detail_len, len(close)):
            # 这里的 sub_prob 是计算到那一天为止的胜率
            sub_prob, sub_pf = backtest_with_stats(close[:i], score_arr[:i], 7)
            chg = (close[i]/close[i-1]-1)*100 if i > 0 else 0
            details.append({
                "日期": dates[i],
                "价格": round(close[i], 2),
                "涨跌": f"{chg:+.2f}%",
                "得分": int(score_arr[i]), # 这里改名为“得分”，与下方渲染保持一致
                "当日胜率": f"{sub_prob*100:.1f}%",
                "当日PF7": round(sub_pf, 2),
                "指标状态": f"M:{sig_macd[i]}|V:{sig_vol[i]}|R:{sig_rsi[i]}|A:{sig_atr[i]}|O:{sig_obv[i]}"
            })

        final_prob, final_pf = backtest_with_stats(close[:-1], score_arr[:-1], 7)
        return {
            "symbol": symbol.upper(),
            "prob7": final_prob,
            "pf7": final_pf,
            "current_price": close[-1],
            "details": details[::-1],
            "signal_count": len(np.where(score_arr[:-7] >= 3)[0])
        }
    except Exception:
        return None

# ==================== UI 界面 ====================
if 'all_results' not in st.session_state: st.session_state.all_results = []
if 'processed_set' not in st.session_state: st.session_set = set()

with st.sidebar:
    st.header("操作面板")
    file = st.file_uploader("上传股票代码 TXT", type=["txt"])
    if st.button("🗑️ 清空进度"):
        st.session_state.all_results = []
        st.session_set = set()
        st.rerun()

if not file:
    st.warning("请上传 TXT 文件。")
    st.stop()

tickers = list(dict.fromkeys([t.strip().upper() for t in file.read().decode().replace(","," ").split() if t.strip()]))

if st.button("🚀 开始分析"):
    progress = st.progress(0)
    remaining = [s for s in tickers if s not in getattr(st.session_state, 'processed_set', set())]
    for i, s in enumerate(remaining):
        res = compute_stock_comprehensive(s)
        if res: st.session_state.all_results.append(res)
        if 'processed_set' not in st.session_state: st.session_state.processed_set = set()
        st.session_state.processed_set.add(s)
        progress.progress((i + 1) / len(remaining))

if st.session_state.all_results:
    # 汇总表
    df_main = pd.DataFrame([
        {"代码": r['symbol'], "7日胜率(年)": f"{r['prob7']*100:.1f}%", "PF7(年)": r['pf7'], "现价": r['current_price'], "raw_pf": r['pf7']}
        for r in st.session_state.all_results
    ]).sort_values("raw_pf", ascending=False)
    
    st.subheader("🏆 年度排行榜")
    st.dataframe(df_main.drop(columns=['raw_pf']), use_container_width=True)

    # 下载 TXT
    report_lines = [f"{r['symbol']}: 胜率 {r['prob7']*100:.1f}%, PF7 {r['pf7']:.2f}" for r in st.session_state.all_results]
    st.download_button("📥 下载 TXT 报告", "\n".join(report_lines), file_name="report.txt")

    st.divider()
    
    # 明细表
    selected = st.selectbox("查看详情", options=[r['symbol'] for r in st.session_state.all_results])
    if selected:
        stock_res = next(r for r in st.session_state.all_results if r['symbol'] == selected)
        df_detail = pd.DataFrame(stock_res['details'])
        
        # 修正 KeyError：确保 subset 中的名称与 DataFrame 列名完全一致
        # 我们上面在 details 字典里定义的是 "得分"
        st.table(df_detail.style.background_gradient(subset=["得分"], cmap="YlGn"))

st.caption("注：逐日胜率/PF7 反映的是截至当天的历史回测表现。")
