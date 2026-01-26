import streamlit as st
import yfinance as yf
import numpy as np
import time
import pandas as pd
import random
import os
import json

st.set_page_config(page_title="我的股票 短线扫描工具", layout="wide")
st.title("我的股票 短线扫描工具")

# ── 持久化进度文件 ──
progress_file = "scan_progress_my_stocks.json"

if 'progress_loaded' not in st.session_state:
    st.session_state.progress_loaded = True
    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r") as f:
                data = json.load(f)
            st.session_state.high_prob = data.get("high_prob", [])
            st.session_state.scanned_symbols = set(data.get("scanned_symbols", []))
            st.session_state.failed_count = data.get("failed_count", 0)
            st.session_state.fully_scanned = data.get("fully_scanned", False)
            st.success("检测到历史进度，已自动加载")
        except Exception as e:
            st.warning(f"加载进度失败: {e}")

def save_progress():
    data = {
        "high_prob": st.session_state.high_prob,
        "scanned_symbols": list(st.session_state.scanned_symbols),
        "failed_count": st.session_state.failed_count,
        "fully_scanned": st.session_state.fully_scanned
    }
    try:
        with open(progress_file, "w") as f:
            json.dump(data, f)
    except:
        pass

# ── 重置按钮 ──
col_r1, col_r2 = st.columns(2)
with col_r1:
    if st.button("🔄 强制刷新所有数据"):
        st.cache_data.clear()
        st.session_state.high_prob = []
        st.session_state.scanned_symbols = set()
        st.session_state.failed_count = 0
        st.session_state.fully_scanned = False
        st.session_state.scanning = False
        if os.path.exists(progress_file): os.remove(progress_file)
        st.rerun()

# ── 文件上传 ──
uploaded_file = st.file_uploader("选择股票列表文件 (.txt)", type=["txt"])

if uploaded_file is not None:
    content = uploaded_file.read().decode("utf-8")
    raw = content.replace("\n", " ").replace(",", " ").strip()
    tickers_to_scan = list(dict.fromkeys([t.strip().upper() for t in raw.split() if t.strip()]))
    st.success(f"成功读取 {len(tickers_to_scan)} 只股票")
else:
    st.info("请上传TXT文件")
    st.stop()

# ==================== 核心常量 ====================
START_DATE = "2025-12-26"
END_DATE = "2026-01-24"
INTERVAL = "1d"

# ==================== 数据拉取（已去掉20天硬限制） ====================
@st.cache_data(ttl=300, show_spinner=False)
def fetch_yahoo_ohlcv(yahoo_symbol: str):
    try:
        time.sleep(random.uniform(0.5, 1.5)) # 稍微缩短等待时间
        ticker = yf.Ticker(yahoo_symbol)
        df = ticker.history(start=START_DATE, end=END_DATE, interval=INTERVAL, auto_adjust=True, timeout=20)
        
        # 只要不是完全没数据就继续，不再限制必须满20行
        if df.empty or len(df) < 1:
            return None, None, None, None, None
            
        dates = df.index.strftime("%Y-%m-%d").values
        close = df['Close'].values.astype(float)
        high = df['High'].values.astype(float)
        low = df['Low'].values.astype(float)
        volume = df['Volume'].values.astype(float)
        
        mask = ~np.isnan(close)
        return dates[mask], close[mask], high[mask], low[mask], volume[mask]
    except:
        return None, None, None, None, None

# ==================== 指标函数 ====================
def ema_np(x, span):
    if len(x) < 1: return x
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
    for i in range(1, len(tr)): atr[i] = alpha * tr[i] + (1 - alpha) * atr[i-1]
    return atr

def rolling_mean_np(x, window):
    if len(x) < window: window = max(1, len(x))
    return pd.Series(x).rolling(window=window, min_periods=1).mean().values

def obv_np(close, volume):
    return np.cumsum(np.sign(np.diff(close, prepend=close[0])) * volume)

def backtest_with_stats(close, score, steps):
    if len(close) <= steps: return 0.0, 0.0
    idx = np.where(score[:-steps] >= 3)[0]
    if len(idx) == 0: return 0.0, 0.0
    rets = close[idx + steps] / close[idx] - 1
    win_rate = (rets > 0).mean()
    pf = rets[rets > 0].sum() / abs(rets[rets <= 0].sum()) if (rets <= 0).any() else 9.9
    return win_rate, pf

# ==================== 核心计算 ====================
@st.cache_data(show_spinner=False)
def compute_stock_metrics(symbol: str):
    dates, close, high, low, volume = fetch_yahoo_ohlcv(symbol.upper())
    if dates is None: return None

    data_len = len(close)
    macd_hist = macd_hist_np(close)
    rsi = rsi_np(close)
    atr = atr_np(high, low, close)
    obv = obv_np(close, volume)
    
    # 动态窗口大小
    win = min(20, data_len)
    v_ma, a_ma, o_ma = rolling_mean_np(volume, win), rolling_mean_np(atr, win), rolling_mean_np(obv, win)

    daily_metrics = []
    for i in range(data_len):
        s_macd = macd_hist[i] > 0
        s_vol = volume[i] > v_ma[i] * 1.1 if i > 0 else False
        s_rsi = rsi[i] >= 60
        s_atr = atr[i] > a_ma[i] * 1.1 if i > 0 else False
        s_obv = obv[i] > o_ma[i] * 1.05 if i > 0 else False
        
        score = sum([s_macd, s_vol, s_rsi, s_atr, s_obv])
        daily_metrics.append({
            "date": dates[i], "price": close[i], 
            "change": (close[i]/close[i-1]-1)*100 if i>0 else 0,
            "score": score, 
            "sig_details": {"MACD": s_macd, "放量": s_vol, "RSI": s_rsi, "ATR": s_atr, "OBV": s_obv}
        })

    score_arr = np.array([m['score'] for m in daily_metrics])
    prob7, pf7 = backtest_with_stats(close, score_arr, 7)
    
    return {
        "symbol": symbol.upper(), "prob7": prob7, "pf7": pf7,
        "daily_metrics": daily_metrics, "recent_rising": (data_len > 2 and score_arr[-1] > score_arr[-2])
    }

# ==================== 界面展示逻辑 ====================
if 'high_prob' not in st.session_state: st.session_state.high_prob = []
if 'scanned_symbols' not in st.session_state: st.session_state.scanned_symbols = set()
if 'scanning' not in st.session_state: st.session_state.scanning = False

if st.button("🚀 开始/继续扫描"):
    st.session_state.scanning = True

if st.session_state.scanning:
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    remaining = [s for s in tickers_to_scan if s not in st.session_state.scanned_symbols]
    for i, sym in enumerate(remaining):
        status_text.text(f"正在扫描: {sym} ({i+1}/{len(remaining)})")
        res = compute_stock_metrics(sym)
        if res:
            st.session_state.high_prob = [m for m in st.session_state.high_prob if m["symbol"] != sym]
            st.session_state.high_prob.append(res)
        else:
            st.session_state.failed_count = st.session_state.get('failed_count', 0) + 1
        
        st.session_state.scanned_symbols.add(sym)
        progress_bar.progress((i + 1) / len(remaining))
        
        if (i + 1) % 5 == 0: # 每5只保存并刷新一次
            save_progress()
            st.rerun()
    
    st.session_state.scanning = False
    save_progress()
    st.success("扫描全部完成！")

# ==================== 结果显示 ====================
if st.session_state.high_prob:
    df_res = pd.DataFrame(st.session_state.high_prob).sort_values("pf7", ascending=False)
    st.subheader(f"扫描结果 ({len(df_res)}只)")
    
    for _, row in df_res.iterrows():
        with st.expander(f"{row['symbol']} - 7日概率: {row['prob7']*100:.1f}% | PF7: {row['pf7']:.2f}"):
            for dm in reversed(row['daily_metrics']):
                st.write(f"{dm['date']} | 价格: {dm['price']:.2f} ({dm['change']:+.2f}%) | 得分: {dm['score']} | {dm['sig_details']}")
