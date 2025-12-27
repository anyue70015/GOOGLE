import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO

st.set_page_config(page_title="短线扫描-完全一致版", layout="wide")
st.title("🔬 与第一段代码完全一致的版本")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yahoo_ohlcv(yahoo_symbol: str, range_str: str):
    """完全复制第一段代码的数据获取函数"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?range={range_str}&interval=1d"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()["chart"]["result"][0]
        quote = data["indicators"]["quote"][0]
        close = np.array(quote["close"], dtype=float)
        high = np.array(quote["high"], dtype=float)
        low = np.array(quote["low"], dtype=float)
        volume = np.array(quote["volume"], dtype=float)
        mask = ~np.isnan(close)
        close, high, low, volume = close[mask], high[mask], low[mask], volume[mask]
        if len(close) < 100:
            raise ValueError("数据不足")
        return close, high, low, volume
    except Exception as e:
        raise ValueError(f"请求失败: {str(e)}")

def ema_np(x: np.ndarray, span: int) -> np.ndarray:
    """完全复制第一段代码的EMA"""
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
    """完全复制第一段代码的回测函数"""
    if len(close) <= steps + 1:
        return 0.5, 0.0
    idx = np.where(score[:-steps] >= 3)[0]
    if len(idx) == 0:
        return 0.5, 0.0
    rets = close[idx + steps] / close[idx] - 1
    win_rate = (rets > 0).mean()
    pf = rets[rets > 0].sum() / abs(rets[rets <= 0].sum()) if (rets <= 0).any() else 999
    return win_rate, pf

@st.cache_data(show_spinner=False)
def compute_stock_metrics(symbol: str, cfg_key: str = "1年"):
    """完全复制第一段代码的核心计算逻辑"""
    yahoo_symbol = symbol.upper()
    
    # 使用相同的范围配置
    RANGES = {"3个月": "3mo", "1年": "1y", "3年": "3y"}
    range_str = RANGES.get(cfg_key, "1y")
    
    close, high, low, volume = fetch_yahoo_ohlcv(yahoo_symbol, range_str)

    # 计算所有指标
    macd_hist = macd_hist_np(close)
    rsi = rsi_np(close)
    atr = atr_np(high, low, close)
    obv = obv_np(close, volume)
    vol_ma20 = rolling_mean_np(volume, 20)
    atr_ma20 = rolling_mean_np(atr, 20)
    obv_ma20 = rolling_mean_np(obv, 20)

    # 当前信号（完全一致）
    sig_macd = (macd_hist > 0).astype(int)[-1]
    sig_vol = (volume[-1] > vol_ma20[-1] * 1.1).astype(int)
    sig_rsi = (rsi[-1] >= 60).astype(int)
    sig_atr = (atr[-1] > atr_ma20[-1] * 1.1).astype(int)
    sig_obv = (obv[-1] > obv_ma20[-1] * 1.05).astype(int)
    score = sig_macd + sig_vol + sig_rsi + sig_atr + sig_obv

    # 历史信号（完全一致）
    sig_macd_hist = (macd_hist > 0).astype(int)
    sig_vol_hist = (volume > vol_ma20 * 1.1).astype(int)
    sig_rsi_hist = (rsi >= 60).astype(int)
    sig_atr_hist = (atr > atr_ma20 * 1.1).astype(int)
    sig_obv_hist = (obv > obv_ma20 * 1.05).astype(int)
    score_arr = sig_macd_hist + sig_vol_hist + sig_rsi_hist + sig_atr_hist + sig_obv_hist

    # 回测（完全一致的关键！）
    prob7, pf7 = backtest_with_stats(close[:-1], score_arr[:-1], 7)

    price = close[-1]
    change = (close[-1] / close[-2] - 1) * 100 if len(close) >= 2 else 0

    return {
        "symbol": symbol.upper(),
        "price": price,
        "change": change,
        "score": score,
        "prob7": prob7,
        "pf7": pf7,
        "macd": macd_hist[-1],
        "rsi": rsi[-1],
        "volume_ratio": volume[-1] / vol_ma20[-1] if vol_ma20[-1] > 0 else 1.0,
        "atr_ratio": atr[-1] / atr_ma20[-1] if atr_ma20[-1] > 0 else 1.0,
        "obv_ratio": obv[-1] / obv_ma20[-1] if obv_ma20[-1] > 0 else 1.0,
    }

# ==================== 界面部分 ====================
st.sidebar.header("⚙️ 设置")
mode = st.sidebar.selectbox("回测周期", ["3个月", "1年", "3年"], index=1)
filter_threshold = st.sidebar.selectbox(
    "筛选条件",
    ["PF7≥3.6 或 7日概率≥68%", "得分≥3 且 PF7≥3.5", "只看得分≥4"],
    index=0
)

# 股票池（使用第二段代码的动态获取，但可以硬编码）
@st.cache_data(ttl=86400)
def get_tickers():
    # 为了测试，先用小范围
    test_symbols = ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "TSLA", "AMZN", "SPY", "QQQ"]
    return test_symbols

all_tickers = get_tickers()

# 初始化session state
if 'results' not in st.session_state:
    st.session_state.results = []
if 'scanned' not in st.session_state:
    st.session_state.scanned = set()

# 扫描按钮
if st.button("开始扫描（完全一致算法）"):
    st.session_state.results = []
    st.session_state.scanned = set()
    
    progress_bar = st.progress(0)
    
    for i, symbol in enumerate(all_tickers):
        try:
            metrics = compute_stock_metrics(symbol, mode)
            if metrics:
                st.session_state.results.append(metrics)
            st.session_state.scanned.add(symbol)
            
            progress_bar.progress((i + 1) / len(all_tickers))
            time.sleep(1)  # 避免API限制
            
        except Exception as e:
            st.warning(f"{symbol} 失败: {str(e)}")
            st.session_state.scanned.add(symbol)

# 显示结果
if st.session_state.results:
    df = pd.DataFrame(st.session_state.results)
    
    # 应用筛选
    if filter_threshold == "PF7≥3.6 或 7日概率≥68%":
        filtered = df[(df['pf7'] >= 3.6) | (df['prob7'] >= 0.68)]
    elif filter_threshold == "得分≥3 且 PF7≥3.5":
        filtered = df[(df['score'] >= 3) & (df['pf7'] >= 3.5)]
    else:
        filtered = df[df['score'] >= 4]
    
    st.subheader(f"筛选结果 ({len(filtered)} 只)")
    
    for _, row in filtered.iterrows():
        st.write(
            f"**{row['symbol']}** | 价格: ${row['price']:.2f} ({row['change']:+.2f}%) | "
            f"得分: {row['score']}/5 | 胜率: {row['prob7']*100:.1f}% | PF7: {row['pf7']:.2f}"
        )
    
    # 显示详细数据
    with st.expander("查看详细数据"):
        st.dataframe(filtered)

st.info("💡 这个版本使用了与第一段代码完全相同的算法，包括：")
st.info("1. 相同的数据获取和清洗逻辑")
st.info("2. 相同的5个技术指标计算")
st.info("3. 相同的滚动平均计算方法")
st.info("4. 相同的关键：backtest_with_stats(close[:-1], score_arr[:-1], 7)")
st.info("5. 相同的PF7计算逻辑（避免除零处理）")
