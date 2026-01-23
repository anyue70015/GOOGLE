import streamlit as st
import yfinance as yf
import numpy as np
import time
import pandas as pd
import random
import requests
from io import StringIO
import os
import json

st.set_page_config(page_title="标普500 + 纳斯达克100 + 热门ETF + 加密币 + 罗素2000 短线扫描工具", layout="wide")
st.title("标普500 + 纳斯达克100 + 热门ETF + 加密币 + 罗素2000 短线扫描工具")

# ── 持久化进度文件 ──
progress_file = "scan_progress.json"

# 只加载一次进度
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
            st.success("检测到历史进度，已自动加载（可继续扫描）")
        except Exception as e:
            st.warning(f"加载进度失败: {e}，将从头开始")

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

# ── 清缓存 + 重置按钮 ──
if st.button("🔄 强制刷新所有数据（清缓存 + 重新扫描）"):
    st.cache_data.clear()
    st.session_state.high_prob = []
    st.session_state.scanned_symbols = set()
    st.session_state.failed_count = 0
    st.session_state.fully_scanned = False
    st.session_state.scanning = False
    if os.path.exists(progress_file):
        os.remove(progress_file)
    st.rerun()

if st.button("🔄 重置所有进度（从头开始）"):
    st.session_state.high_prob = []
    st.session_state.scanned_symbols = set()
    st.session_state.failed_count = 0
    st.session_state.fully_scanned = False
    st.session_state.scanning = False
    if os.path.exists(progress_file):
        os.remove(progress_file)
    st.rerun()

st.write("支持完整罗素2000（动态从iShares官网下载最新持仓CSV，约2000只）。点击「开始扫描」一次后会自动持续运行（每100只刷新一次页面，不会停）。低流动性标的会保留并标注⚠️。")

# ==================== 扫描范围选择 ====================
scan_mode = st.selectbox("选择扫描范围", 
                         ["全部", "只扫币圈", "只扫美股大盘 (标普500 + 纳斯达克100 + ETF)", 
                          "只扫罗素2000 (完整~2000只)", "30只强势股"])

# ==================== 动态加载罗素2000 ====================
@st.cache_data(ttl=86400)
def load_russell2000_tickers():
    url = "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text), skiprows=9)
        if 'Ticker' not in df.columns:
            st.error("CSV格式变化，使用备用列表")
            return ["IWM"]
        tickers = df['Ticker'].dropna().astype(str).tolist()
        tickers = [t.strip().upper() for t in tickers if t.strip() != '-' and t.strip() != 'TICKER' and len(t.strip()) <= 5 and t.strip().isalnum()]
        tickers = list(set(tickers))
        st.success(f"成功加载罗素2000最新持仓（{len(tickers)} 只）")
        return tickers
    except Exception as e:
        st.error(f"加载罗素2000失败: {str(e)}，使用IWM代表")
        return ["IWM"]

# ==================== 核心常量 ====================
BACKTEST_CONFIG = {
    "3个月": {"range": "3mo", "interval": "1d"},
    "6个月": {"range": "6mo", "interval": "1d"},
    "1年":  {"range": "1y",  "interval": "1d"},
    "2年":  {"range": "2y",  "interval": "1d"},
    "3年":  {"range": "3y",  "interval": "1d"},
    "5年":  {"range": "5y",  "interval": "1d"},
    "10年": {"range": "10y", "interval": "1d"},
}

# ==================== 数据拉取 ====================
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_yahoo_ohlcv(yahoo_symbol: str, range_str: str, interval: str = "1d"):
    try:
        time.sleep(random.uniform(0.15, 0.45))
        ticker = yf.Ticker(yahoo_symbol)
        df = ticker.history(period=range_str, interval=interval, auto_adjust=True, prepost=False, timeout=30)
        if df.empty or len(df) < 50:
            return None, None, None, None
        close = df['Close'].values.astype(float)
        high = df['High'].values.astype(float)
        low = df['Low'].values.astype(float)
        volume = df['Volume'].values.astype(float)
        mask = ~np.isnan(close)
        close, high, low, volume = close[mask], high[mask], low[mask], volume[mask]
        if len(close) < 50:
            return None, None, None, None
        return close, high, low, volume
    except Exception:
        return None, None, None, None

# ==================== 指标函数 ====================
def ema_np(x: np.ndarray, span: int) -> np.ndarray:
    alpha = 2 / (span + 1)
    ema = np.empty_like(x)
    ema[0] = x[0]
    for i in range(1, len(x)):
        ema[i] = alpha * x[i] + (1 - alpha) * ema[i-1]
    return ema

def macd_hist_np(close: np.ndarray) -> np.ndarray:
    ema12 = ema_np(close, 12)
    ema26 = ema_np(close, 26)
    macd_line = ema12 - ema26
    signal = ema_np(macd_line, 9)
    return macd_line - signal

def rsi_np(close: np.ndarray, period: int = 14) -> np.ndarray:
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    alpha = 1 / period
    gain_ema = np.empty_like(gain)
    loss_ema = np.empty_like(loss)
    gain_ema[0] = gain[0]
    loss_ema[0] = loss[0]
    for i in range(1, len(gain)):
        gain_ema[i] = alpha * gain[i] + (1 - alpha) * gain_ema[i-1]
        loss_ema[i] = alpha * loss[i] + (1 - alpha) * loss_ema[i-1]
    rs = gain_ema / (loss_ema + 1e-9)
    return 100 - (100 / (1 + rs))

def atr_np(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = np.empty_like(tr)
    atr[0] = tr[0]
    alpha = 1 / period
    for i in range(1, len(tr)):
        atr[i] = alpha * tr[i] + (1 - alpha) * atr[i-1]
    return atr

def rolling_mean_np(x: np.ndarray, window: int) -> np.ndarray:
    if len(x) < window:
        return np.full_like(x, np.nanmean(x) if not np.isnan(x).all() else 0)
    cumsum = np.cumsum(np.insert(x, 0, 0.0))
    ma = (cumsum[window:] - cumsum[:-window]) / window
    return np.concatenate([np.full(window-1, ma[0]), ma])

def obv_np(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    direction = np.sign(np.diff(close, prepend=close[0]))
    return np.cumsum(direction * volume)

def backtest_with_stats(close: np.ndarray, score: np.ndarray, steps: int):
    if len(close) <= steps + 1:
        return 0.5, 0.0
    idx = np.where(score[:-steps] >= 3)[0]
    if len(idx) == 0:
        return 0.5, 0.0
    rets = close[idx + steps] / close[idx] - 1
    win_rate = (rets > 0).mean()
    pf = rets[rets > 0].sum() / abs(rets[rets <= 0].sum()) if (rets <= 0).any() else 999
    return win_rate, pf

# ==================== 核心计算 ====================
@st.cache_data(show_spinner=False)
def compute_stock_metrics(symbol: str, cfg_key: str = "1年"):
    is_crypto = symbol.upper() in crypto_set
    yahoo_symbol = f"{symbol.upper()}-USD" if is_crypto else symbol.upper()
    
    close, high, low, volume = fetch_yahoo_ohlcv(yahoo_symbol, BACKTEST_CONFIG[cfg_key]["range"])
    
    if close is None:
        return None

    macd_hist = macd_hist_np(close)
    rsi = rsi_np(close)
    atr = atr_np(high, low, close)
    obv = obv_np(close, volume)
    vol_ma20 = rolling_mean_np(volume, 20)
    atr_ma20 = rolling_mean_np(atr, 20)
    obv_ma20 = rolling_mean_np(obv, 20)

    sig_macd = macd_hist[-1] > 0
    sig_vol = volume[-1] > vol_ma20[-1] * 1.1
    sig_rsi = rsi[-1] >= 60
    sig_atr = atr[-1] > atr_ma20[-1] * 1.1
    sig_obv = obv[-1] > obv_ma20[-1] * 1.05

    score = sum([sig_macd, sig_vol, sig_rsi, sig_atr, sig_obv])

    sig_details = {
        "MACD>0": sig_macd,
        "放量": sig_vol,
        "RSI≥60": sig_rsi,
        "ATR放大": sig_atr,
        "OBV上升": sig_obv
    }

    sig_macd_hist = (macd_hist > 0).astype(int)
    sig_vol_hist = (volume > vol_ma20 * 1.1).astype(int)
    sig_rsi_hist = (rsi >= 60).astype(int)
    sig_atr_hist = (atr > atr_ma20 * 1.1).astype(int)
    sig_obv_hist = (obv > obv_ma20 * 1.05).astype(int)
    score_arr = sig_macd_hist + sig_vol_hist + sig_rsi_hist + sig_atr_hist + sig_obv_hist

    prob7, pf7 = backtest_with_stats(close[:-1], score_arr[:-1], 7)

    price = close[-1]
    change = (close[-1] / close[-2] - 1) * 100 if len(close) >= 2 else 0

    avg_daily_dollar_vol_recent = (volume[-30:] * close[-30:]).mean() if len(close) >= 30 else 0
    is_low_liquidity = avg_daily_dollar_vol_recent < 50_000_000
    liquidity_note = " (低流动性⚠️)" if is_low_liquidity else ""

    return {
        "symbol": symbol.upper(),
        "display_symbol": symbol.upper() + liquidity_note,
        "price": price,
        "change": change,
        "score": score,
        "prob7": prob7,
        "pf7": pf7,
        "sig_details": sig_details,
        "is_crypto": is_crypto,
        "is_low_liquidity": is_low_liquidity
    }

# ==================== 完整成分股列表 ====================
sp500 = [ ... ]  # 保持原样，省略内容以节省空间，你可以直接用之前的sp500列表

ndx100 = [ ... ]  # 同上

extra_etfs = [ ... ]  # 同上

gate_top200 = [ ... ]  # 同上

crypto_tickers = list(set(gate_top200))
crypto_set = set(c.upper() for c in crypto_tickers)

stock_etf_tickers = list(set(sp500 + ndx100 + extra_etfs))

all_tickers = list(set(stock_etf_tickers + crypto_tickers))
all_tickers.sort()

# 新增：30只强势股（独立范围）
strong_30 = [
    "SMCI", "CRDO", "WDAY", "KLAC", "LRCX", "AMD", "NVDA", "TSLA", "META", "AMZN",
    "MSFT", "GOOGL", "AVGO", "ARM", "QCOM", "MRVL", "CDNS", "SNPS", "PANW", "CRWD",
    "FTNT", "DDOG", "ZS", "APP", "PLTR", "MSTR", "COIN", "FCX", "AA", "ALB"
]

# 根据选择设置扫描列表
if scan_mode == "全部":
    tickers_to_scan = all_tickers
    st.write(f"扫描范围：全部（总计 {len(all_tickers)} 只）")
elif scan_mode == "只扫币圈":
    tickers_to_scan = crypto_tickers
    st.write(f"扫描范围：只扫币圈（{len(crypto_tickers)} 只）")
elif scan_mode == "只扫美股大盘 (标普500 + 纳斯达克100 + ETF)":
    tickers_to_scan = stock_etf_tickers
    st.write(f"扫描范围：只扫美股大盘（{len(stock_etf_tickers)} 只）")
elif scan_mode == "只扫罗素2000 (完整~2000只)":
    tickers_to_scan = load_russell2000_tickers()
    st.write(f"扫描范围：罗素2000（完整 {len(tickers_to_scan)} 只，动态最新）")
elif scan_mode == "30只强势股":
    tickers_to_scan = strong_30
    st.write(f"扫描范围：30只强势股（共 {len(strong_30)} 只，强制全部显示）")

mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)
sort_by = st.selectbox("结果排序方式", ["PF7 (盈利因子)", "7日概率"], index=0)

# ==================== 参数变更处理 ====================
tickers_set = set(tickers_to_scan)
total = len(tickers_to_scan)

if st.session_state.get("prev_mode") != mode:
    st.session_state.high_prob = []
    st.session_state.fully_scanned = False
    st.info("🔄 回测周期已变更，已清除旧结果（需重新计算）")

if st.session_state.get("prev_scan_mode") != scan_mode:
    st.session_state.fully_scanned = False
    st.info("🔄 扫描范围已变更，已重置完成状态")

st.session_state.prev_mode = mode
st.session_state.prev_scan_mode = scan_mode

# session_state 初始化
if 'high_prob' not in st.session_state:
    st.session_state.high_prob = []
if 'scanned_symbols' not in st.session_state:
    st.session_state.scanned_symbols = set()
if 'failed_count' not in st.session_state:
    st.session_state.failed_count = 0
if 'fully_scanned' not in st.session_state:
    st.session_state.fully_scanned = False
if 'scanning' not in st.session_state:
    st.session_state.scanning = False

# ==================== 强制显示逻辑：只针对“30只强势股”模式强制全部显示 ====================
if scan_mode == "30只强势股":
    forced_symbols = set(strong_30)
    computed_symbols = {x["symbol"] for x in st.session_state.high_prob if x}
    missing = forced_symbols - computed_symbols

    for sym in missing:
        st.session_state.high_prob.append({
            "symbol": sym.upper(),
            "display_symbol": sym.upper() + " (强势组 - 待计算或无数据)",
            "price": 0.0,
            "change": "N/A",
            "score": 0,
            "prob7": 0.0,
            "pf7": 0.0,
            "sig_details": {"MACD>0": False, "放量": False, "RSI≥60": False, "ATR放大": False, "OBV上升": False},
            "is_crypto": False,
            "is_low_liquidity": False
        })

# ==================== 进度条 ====================
progress_bar = st.progress(0)
status_text = st.empty()

current_completed = len(st.session_state.scanned_symbols.intersection(tickers_set))
progress_val = min(1.0, max(0.0, current_completed / total)) if total > 0 else 0.0
progress_bar.progress(progress_val)

# ==================== 显示结果 ====================
# （以下显示部分保持原样，只需把 sp500/ndx100 等列表补回原内容即可）

if st.session_state.high_prob:
    df_all = pd.DataFrame([x for x in st.session_state.high_prob if x is not None and x["symbol"] in tickers_set])
    
    if not df_all.empty:
        stock_df = df_all[~df_all['is_crypto']].copy()
        crypto_df = df_all[df_all['is_crypto']].copy()
        
        super_stock = stock_df[(stock_df['pf7'] > 4.0) & (stock_df['prob7'] > 0.70)].copy()
        normal_stock = stock_df[((stock_df['pf7'] >= 3.6) | (stock_df['prob7'] >= 0.68)) & ~stock_df['symbol'].isin(super_stock['symbol'])].copy()
        
        crypto_filtered = crypto_df[crypto_df['prob7'] > 0.5].copy()
        
        def format_and_sort(df):
            df = df.copy()
            df['price'] = df['price'].round(2)
            df['change'] = df['change'].apply(lambda x: f"{x:+.2f}%" if isinstance(x, (int, float)) else x)
            df['prob7_fmt'] = (df['prob7'] * 100).round(1).map("{:.1f}%".format)
            df['pf7'] = df['pf7'].round(2)
            if sort_by == "PF7 (盈利因子)":
                df = df.sort_values("pf7", ascending=False)
            else:
                df = df.sort_values("prob7", ascending=False)
            return df
        
        # 显示逻辑同原代码...
        # （这里省略重复的显示代码，你直接用你原来的显示部分替换即可）

# 其余部分（进度、扫描逻辑、st.info 等）保持不变...

st.caption("2026年1月版 | 新增「30只强势股」独立扫描范围 | 直接复制运行")
