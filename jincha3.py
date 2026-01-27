import streamlit as st
import yfinance as yf
import numpy as np
import pandas as pd
import time
import random
from datetime import datetime, timedelta

# ==================== 页面配置 ====================
st.set_page_config(page_title="短线扫描器-深度汇总版", layout="wide")
st.title("📈 股票短线扫描 (新增 PF7 > 3.5 批量打包)")

# --- 动态结束日期：取今天（追求最新信号） ---
today = datetime.now().date()
end_dt = today
END_DATE_STR = end_dt.strftime("%Y-%m-%d")

# 侧边栏选择回测周期
timeframe = st.sidebar.selectbox("回测周期", ["6个月", "1年", "2年"], index=1)  # 默认1年

# 根据选择设置天数
if timeframe == "6个月":
    start_dt = end_dt - timedelta(days=180)
elif timeframe == "1年":
    start_dt = end_dt - timedelta(days=365)
else:  # 2年
    start_dt = end_dt - timedelta(days=730)

START_DATE = start_dt.strftime("%Y-%m-%d")

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

def backtest_with_stats(close: np.ndarray, score: np.ndarray, steps: int = 7):
    """
    优化版回测函数：
    - 样本过短返回 nan, nan, 0
    - 使用 np.inf 处理无负收益情况
    - 加 trade_count 返回，用于判断PF可信度
    - 加 rets nan/inf 安全处理
    """
    if len(close) <= steps + 1:
        return np.nan, np.nan, 0  # 样本太短

    idx = np.where(score[:-steps] >= 3)[0]
    trade_count = len(idx)
    if trade_count == 0:
        return 0.5, 0.0, 0  # 无信号

    rets = close[idx + steps] / close[idx] - 1
    rets = np.nan_to_num(rets, nan=0.0, posinf=0.0, neginf=0.0)  # 安全处理

    win_rate = np.mean(rets > 0) if len(rets) > 0 else 0.5

    pos_ret = np.sum(rets[rets > 0])
    neg_ret = np.abs(np.sum(rets[rets <= 0]))

    if neg_ret < 1e-8:
        pf = np.inf if pos_ret > 0 else 0.0
    else:
        pf = pos_ret / neg_ret

    return win_rate, pf, trade_count

@st.cache_data(ttl=3600, show_spinner=False)
def compute_stock_comprehensive(symbol):
    try:
        df = yf.Ticker(symbol).history(start=START_DATE, end=END_DATE_STR, interval="1d")
        if df.empty or len(df) < 50: return None
        close, high, low, volume = df['Close'].values, df['High'].values, df['Low'].values, df['Volume'].values
        dates = df.index.strftime("%Y-%m-%d").values

        macd_hist = (ema_np(close, 12) - ema_np(close, 26)) - ema_np((ema_np(close, 12) - ema_np(close, 26)), 9)
        score_arr = (macd_hist > 0).astype(int) + \
                    (volume > rolling_mean_np(volume, 20) * 1.1).astype(int) + \
                    (rsi_np(close) >= 60).astype(int) + \
                    (atr_np(high, low, close) > rolling_mean_np(atr_np(high, low, close), 20) * 1.1).astype(int) + \
                    (obv_np(close, volume) > rolling_mean_np(obv_np(close, volume), 20) * 1.05).astype(int)

        # 当前最新一天信号（使用 [-1]）
        sig_macd = macd_hist[-1] > 0
        sig_vol = volume[-1] > rolling_mean_np(volume, 20)[-1] * 1.1
        sig_rsi = rsi_np(close)[-1] >= 60
        sig_atr = atr_np(high, low, close)[-1] > rolling_mean_np(atr_np(high, low, close), 20)[-1] * 1.1
        sig_obv = obv_np(close, volume)[-1] > rolling_mean_np(obv_np(close, volume), 20)[-1] * 1.05

        score = sum([sig_macd, sig_vol, sig_rsi, sig_atr, sig_obv])

        # 整体回测：使用[:-1]，排除最后一天信号（无前视偏差）
        f_prob, f_pf, trade_count = backtest_with_stats(close[:-1], score_arr[:-1], 7)

        # 逐日细节（保持原滚动方式，用于稳定性观察）
        detail_len = min(40, len(close))
        details = []
        for i in range(len(close) - detail_len, len(close)):
            sub_prob, sub_pf, _ = backtest_with_stats(close[:i], score_arr[:i], 7)
            chg = (close[i]/close[i-1]-1)*100 if i > 0 else 0
            details.append({
                "日期": dates[i], 
                "价格": round(close[i], 2), 
                "涨跌": f"{chg:+.2f}%",
                "得分": int(score_arr[i]),
                "胜率": f"{sub_prob*100:.1f}%" if np.isfinite(sub_prob) else "N/A", 
                "PF7": round(sub_pf, 2) if np.isfinite(sub_pf) else ("∞" if np.isinf(sub_pf) else "N/A")
            })
        
        last_chg = (close[-1]/close[-2]-1)*100 if len(close) > 1 else 0
        
        return {
            "symbol": symbol.upper(), 
            "prob7": f_prob, 
            "pf7": f_pf, 
            "price": close[-1], 
            "chg": f"{last_chg:+.2f}%",
            "score": score, 
            "details": details[::-1],
            "trade_count": trade_count  # 新增，可用于后续过滤
        }
    except: return None

# ==================== UI 展示 ====================
if 'results' not in st.session_state: st.session_state.results = []
with st.sidebar:
    file = st.file_uploader("上传代码 TXT", type=["txt"])
    if st.button("清空结果"): st.session_state.results = []

if file:
    tickers = list(dict.fromkeys([t.strip().upper() for t in file.read().decode().split() if t.strip()]))
    if st.button("开始分析"):
        for s in tickers:
            res = compute_stock_comprehensive(s)
            if res and res not in st.session_state.results: 
                st.session_state.results.append(res)

if st.session_state.results:
    df_main = pd.DataFrame(st.session_state.results).sort_values("pf7", ascending=False)
    
    # 处理 pf7 显示（inf / nan）
    df_main['pf7_display'] = df_main['pf7'].apply(
        lambda x: "∞" if np.isinf(x) else (f"{x:.2f}" if np.isfinite(x) else "N/A")
    )
    
    st.subheader("🏆 年度排行榜")
    st.dataframe(df_main[["symbol", "pf7_display", "prob7", "score", "price", "chg"]], use_container_width=True)

    # --- 汇总下载 1: 年度排行 ---
    summary_txt = f"{'代码':<10} {'PF7':<10} {'胜率':<10} {'得分':<10} {'价格':<10} {'涨幅':<10}\r\n"
    summary_txt += "-"*65 + "\r\n"
    for _, r in df_main.iterrows():
        pf_str = "∞" if np.isinf(r['pf7']) else (f"{r['pf7']:.2f}" if np.isfinite(r['pf7']) else "N/A")
        summary_txt += f"{r['symbol']:<10} {pf_str:<10} {r['prob7']*100:<10.1f}% {r['score']:<10} {r['price']:<10.2f} {r['chg']:<10}\r\n"
    
    # --- 汇总下载 2: PF7 > 3.5 优质票 40日明细打包 ---
    premium_txt = "=== PF7 > 3.5 优质股票近40日明细汇总报告 ===\r\n\r\n"
    premium_stocks = [r for r in st.session_state.results if np.isfinite(r['pf7']) and r['pf7'] > 3.5]
    premium_stocks = sorted(premium_stocks, key=lambda x: x['pf7'], reverse=True)

    if premium_stocks:
        for p_stock in premium_stocks:
            pf_str = "∞" if np.isinf(p_stock['pf7']) else f"{p_stock['pf7']:.2f}"
            premium_txt += f"【股票代码: {p_stock['symbol']} | 年度PF7: {pf_str}】\r\n"
            premium_txt += f"{'日期':<12} {'价格':<10} {'涨跌':<10} {'得分':<8} {'胜率':<10} {'PF7':<10}\r\n"
            premium_txt += "-"*65 + "\r\n"
            for d in p_stock['details']:
                premium_txt += f"{d['日期']:<12} {d['价格']:<10.2f} {d['涨跌']:<10} {d['得分']:<8} {d['胜率']:<10} {d['PF7']:<10.2f}\r\n"
            premium_txt += "\r\n" + "="*65 + "\r\n\r\n"
    else:
        premium_txt += "本次扫描未发现 PF7 > 3.5 的股票。\r\n"

    col1, col2 = st.columns(2)
    with col1:
        st.download_button("📥 下载汇总排行 (TXT)", summary_txt, file_name="Summary_Report.txt")
    with col2:
        st.download_button("🔥 下载优质票(PF7>3.5)明细打包 (TXT)", premium_txt, file_name="Premium_Stocks_40D_Details.txt")

    st.divider()
    
    # --- 单个股票逐日明细展示 ---
    selected = st.selectbox("选择股票查看 40 日明细 (同步排序)", options=df_main["symbol"].tolist())
    if selected:
        res_data = next(r for r in st.session_state.results if r['symbol'] == selected)
        df_detail = pd.DataFrame(res_data['details'])
        
        detail_txt = f"股票: {selected} 最近 40 日明细\r\n"
        detail_txt += f"{'日期':<12} {'价格':<10} {'涨跌':<10} {'得分':<8} {'胜率':<10} {'PF7':<10}\r\n"
        detail_txt += "-"*65 + "\r\n"
        for _, d in df_detail.iterrows():
            detail_txt += f"{d['日期']:<12} {d['价格']:<10.2f} {d['涨跌']:<10} {d['得分']:<8} {d['胜率']:<10} {d['PF7']:<10.2f}\r\n"
        
        st.download_button(f"📥 下载 {selected} 逐日明细 (TXT)", detail_txt, file_name=f"{selected}_Detail.txt")
        st.table(df_detail.style.background_gradient(subset=["得分"], cmap="YlGn"))
