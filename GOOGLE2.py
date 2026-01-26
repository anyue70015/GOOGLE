import streamlit as st
import yfinance as yf
import numpy as np
import pandas as pd
import time
import random
from datetime import datetime, timedelta

# ==================== 页面配置 ====================
st.set_page_config(page_title="股票短线扫描-深度版", layout="wide")
st.title("🚀 股票短线深度扫描工具 (一年测算 + 40日详情)")

# --- 周期设定 (基于2026年1月24日倒推一年) ---
END_DATE_STR = "2026-01-24"
end_dt = datetime.strptime(END_DATE_STR, "%Y-%m-%d")
# 取385天确保有足够数据计算20日均线和7日回测
start_dt = end_dt - timedelta(days=385)
START_DATE = start_dt.strftime("%Y-%m-%d")

st.info(f"📅 测算周期：{START_DATE} 至 {END_DATE_STR} | 计算逻辑：五项指标共振")

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
    # 根据您指定的逻辑：回测得分 >= 3 的情况
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
        time.sleep(random.uniform(0.3, 0.8))
        df = yf.Ticker(symbol).history(start=START_DATE, end=END_DATE_STR, interval="1d")
        if df.empty or len(df) < 30: return None
        
        close = df['Close'].values.astype(float)
        high = df['High'].values.astype(float)
        low = df['Low'].values.astype(float)
        volume = df['Volume'].values.astype(float)
        dates = df.index.strftime("%Y-%m-%d").values

        # 1. 计算各项指标
        macd_line = ema_np(close, 12) - ema_np(close, 26)
        macd_hist = macd_line - ema_np(macd_line, 9)
        rsi = rsi_np(close)
        atr = atr_np(high, low, close)
        obv = obv_np(close, volume)
        
        vol_ma20 = rolling_mean_np(volume, 20)
        atr_ma20 = rolling_mean_np(atr, 20)
        obv_ma20 = rolling_mean_np(obv, 20)

        # 2. 判定信号序列 (您的指定逻辑)
        sig_macd = (macd_hist > 0).astype(int)
        sig_vol = (volume > vol_ma20 * 1.1).astype(int)
        sig_rsi = (rsi >= 60).astype(int)
        sig_atr = (atr > atr_ma20 * 1.1).astype(int)
        sig_obv = (obv > obv_ma20 * 1.05).astype(int)
        
        score_arr = sig_macd + sig_vol + sig_rsi + sig_atr + sig_obv

        # 3. 计算一年期回测 (排除最后一天以保证回测严谨)
        prob7, pf7 = backtest_with_stats(close[:-1], score_arr[:-1], 7)
        
        # 4. 提取最近 40 个交易日详情
        detail_len = min(40, len(close))
        details = []
        for i in range(len(close) - detail_len, len(close)):
            chg = (close[i]/close[i-1]-1)*100 if i > 0 else 0
            details.append({
                "日期": dates[i],
                "价格": round(close[i], 2),
                "涨跌幅": f"{chg:+.2f}%",
                "综合得分": int(score_arr[i]),
                "MACD": "✅" if sig_macd[i] else "❌",
                "放量": "✅" if sig_vol[i] else "❌",
                "RSI": "✅" if sig_rsi[i] else "❌",
                "ATR": "✅" if sig_atr[i] else "❌",
                "OBV": "✅" if sig_obv[i] else "❌"
            })

        return {
            "symbol": symbol.upper(),
            "prob7": prob7,
            "pf7": pf7,
            "current_price": close[-1],
            "details": details[::-1], # 倒序显示
            "signal_count": len(np.where(score_arr[:-7] >= 3)[0])
        }
    except Exception:
        return None

# ==================== 用户界面展示 ====================
if 'all_results' not in st.session_state: st.session_state.all_results = []
if 'processed_set' not in st.session_state: st.session_state.processed_set = set()

with st.sidebar:
    st.header("配置")
    file = st.file_uploader("上传 TXT 股票列表", type=["txt"])
    if st.button("🗑️ 清空进度"):
        st.session_state.all_results = []
        st.session_state.processed_set = set()
        st.rerun()

if not file:
    st.warning("请先上传包含股票代码的 TXT 文件。")
    st.stop()

tickers = list(dict.fromkeys([t.strip().upper() for t in file.read().decode().replace(","," ").split() if t.strip()]))

if st.button("🚀 开始全量深度扫描"):
    progress = st.progress(0)
    status = st.empty()
    
    remaining = [s for s in tickers if s not in st.session_state.processed_set]
    for i, s in enumerate(remaining):
        status.text(f"正在分析 {s} ({i+1}/{len(remaining)})")
        res = compute_stock_comprehensive(s)
        if res:
            st.session_state.all_results.append(res)
        st.session_state.processed_set.add(s)
        progress.progress((i + 1) / len(remaining))
    st.success("扫描完成！")

# 结果呈现
if st.session_state.all_results:
    df_main = pd.DataFrame([
        {
            "代码": r['symbol'], 
            "7日胜率(年)": f"{r['prob7']*100:.1f}%", 
            "PF7(年)": round(r['pf7'], 2),
            "信号次数": r['signal_count'],
            "现价": r['current_price'],
            "raw_pf7": r['pf7']
        } for r in st.session_state.all_results
    ]).sort_values("raw_pf7", ascending=False)

    st.subheader("🏆 测算排行 (按一年期盈利因子排序)")
    st.dataframe(df_main.drop(columns=['raw_pf7']), use_container_width=True)

    st.divider()
    st.subheader("🔍 最近 40 个交易日评分明细")
    selected = st.selectbox("选择要查看的股票", options=[r['symbol'] for r in st.session_state.all_results])
    
    if selected:
        stock_res = next(r for r in st.session_state.all_results if r['symbol'] == selected)
        df_detail = pd.DataFrame(stock_res['details'])
        
        # 使用 matplotlib 驱动的颜色渐变 (因为用户已安装 matplotlib)
        st.table(df_detail.style.background_gradient(subset=["综合得分"], cmap="YlGn"))

st.caption("提示：表格中“✅”代表该项指标满足您的设定条件。PF7 > 1.0 代表策略盈利。")
