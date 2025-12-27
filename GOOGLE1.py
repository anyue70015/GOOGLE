import streamlit as st
import requests
import numpy as np
import time
import pandas as pd

st.set_page_config(page_title="100%一致验证版", layout="wide")
st.title("🔍 与第一段代码100%一致的验证工具")

# ==================== 完全复制第一段代码的所有函数 ====================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# 1:1复制第一段代码的数据获取
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yahoo_ohlcv_original(yahoo_symbol: str, range_str: str):
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
            raise ValueError("数据不足100个点")
        return close, high, low, volume
    except Exception as e:
        raise ValueError(f"请求失败: {str(e)}")

# 1:1复制第一段代码的EMA
def ema_np_original(x: np.ndarray, span: int) -> np.ndarray:
    alpha = 2 / (span + 1)
    ema = np.empty_like(x)
    ema[0] = x[0]
    for i in range(1, len(x)):
        ema[i] = alpha * x[i] + (1 - alpha) * ema[i-1]
    return ema

# 1:1复制第一段代码的MACD
def macd_hist_np_original(close: np.ndarray) -> np.ndarray:
    ema12 = ema_np_original(close, 12)
    ema26 = ema_np_original(close, 26)
    macd_line = ema12 - ema26
    signal = ema_np_original(macd_line, 9)
    return macd_line - signal

# 1:1复制第一段代码的RSI
def rsi_np_original(close: np.ndarray, period: int = 14) -> np.ndarray:
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

# 1:1复制第一段代码的ATR
def atr_np_original(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = np.empty_like(tr)
    atr[0] = tr[0]
    alpha = 1 / period
    for i in range(1, len(tr)):
        atr[i] = alpha * tr[i] + (1 - alpha) * atr[i-1]
    return atr

# 1:1复制第一段代码的滚动平均（关键！）
def rolling_mean_np_original(x: np.ndarray, window: int) -> np.ndarray:
    if len(x) < window:
        return np.full_like(x, np.nanmean(x) if not np.isnan(x).all() else 0)
    cumsum = np.cumsum(np.insert(x, 0, 0.0))
    ma = (cumsum[window:] - cumsum[:-window]) / window
    return np.concatenate([np.full(window-1, ma[0]), ma])

# 1:1复制第一段代码的OBV
def obv_np_original(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    direction = np.sign(np.diff(close, prepend=close[0]))
    return np.cumsum(direction * volume)

# 1:1复制第一段代码的回测函数
def backtest_with_stats_original(close: np.ndarray, score: np.ndarray, steps: int):
    if len(close) <= steps + 1:
        return 0.5, 0.0
    idx = np.where(score[:-steps] >= 3)[0]
    if len(idx) == 0:
        return 0.5, 0.0
    rets = close[idx + steps] / close[idx] - 1
    win_rate = (rets > 0).mean()
    pf = rets[rets > 0].sum() / abs(rets[rets <= 0].sum()) if (rets <= 0).any() else 999
    return win_rate, pf

# ==================== 对比测试函数 ====================

def compute_original_version(symbol: str, range_str: str = "1y"):
    """运行第一段代码的算法"""
    try:
        close, high, low, volume = fetch_yahoo_ohlcv_original(symbol, range_str)
        
        # 计算指标
        macd_hist = macd_hist_np_original(close)
        rsi = rsi_np_original(close)
        atr = atr_np_original(high, low, close)
        obv = obv_np_original(close, volume)
        
        # 计算移动平均
        vol_ma20 = rolling_mean_np_original(volume, 20)
        atr_ma20 = rolling_mean_np_original(atr, 20)
        obv_ma20 = rolling_mean_np_original(obv, 20)
        
        # 当前信号
        sig_macd = (macd_hist > 0).astype(int)[-1]
        sig_vol = (volume[-1] > vol_ma20[-1] * 1.1).astype(int)
        sig_rsi = (rsi[-1] >= 60).astype(int)
        sig_atr = (atr[-1] > atr_ma20[-1] * 1.1).astype(int)
        sig_obv = (obv[-1] > obv_ma20[-1] * 1.05).astype(int)
        score = sig_macd + sig_vol + sig_rsi + sig_atr + sig_obv
        
        # 历史信号
        sig_macd_hist = (macd_hist > 0).astype(int)
        sig_vol_hist = (volume > vol_ma20 * 1.1).astype(int)
        sig_rsi_hist = (rsi >= 60).astype(int)
        sig_atr_hist = (atr > atr_ma20 * 1.1).astype(int)
        sig_obv_hist = (obv > obv_ma20 * 1.05).astype(int)
        score_arr = sig_macd_hist + sig_vol_hist + sig_rsi_hist + sig_atr_hist + sig_obv_hist
        
        # 回测
        prob7, pf7 = backtest_with_stats_original(close[:-1], score_arr[:-1], 7)
        
        change = (close[-1] / close[-2] - 1) * 100 if len(close) >= 2 else 0
        
        return {
            "symbol": symbol,
            "price": close[-1],
            "change": change,
            "score": score,
            "prob7": prob7,
            "pf7": pf7,
            "data_points": len(close),
            "vol_ma20_last": vol_ma20[-1],
            "volume_last": volume[-1],
            "volume_ratio": volume[-1] / vol_ma20[-1] if vol_ma20[-1] > 0 else 0
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}

# ==================== 界面 ====================

st.header("🔬 100%一致性验证工具")

# 输入要测试的股票
symbols_input = st.text_area(
    "输入要对比的股票代码（每行一个）", 
    "AAPL\nMSFT\nNVDA\nGOOGL\nSPY\nQQQ"
)
symbols = [s.strip().upper() for s in symbols_input.split('\n') if s.strip()]

range_str = st.selectbox("时间范围", ["3mo", "6mo", "1y", "2y", "3y"], index=2)

if st.button("运行100%一致算法"):
    results = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, symbol in enumerate(symbols):
        status_text.text(f"计算 {symbol} ({i+1}/{len(symbols)})")
        result = compute_original_version(symbol, range_str)
        results.append(result)
        progress_bar.progress((i + 1) / len(symbols))
        time.sleep(2)  # 避免API限制
    
    # 显示结果
    df = pd.DataFrame(results)
    
    if "error" in df.columns:
        df_error = df[~df['error'].isna()]
        if not df_error.empty:
            st.warning("以下股票计算失败:")
            st.dataframe(df_error[['symbol', 'error']])
    
    df_success = df[df['error'].isna()].copy()
    
    if not df_success.empty:
        # 应用第一段代码的筛选条件
        filtered = df_success[(df_success['pf7'] >= 3.6) | (df_success['prob7'] >= 0.68)]
        
        st.subheader(f"符合条件: PF7≥3.6 或 胜率≥68% ({len(filtered)}/{len(df_success)})")
        
        for _, row in filtered.iterrows():
            st.write(
                f"**{row['symbol']}** | 价格: ${row['price']:.2f} ({row['change']:+.2f}%) | "
                f"得分: {row['score']}/5 | 胜率: {row['prob7']*100:.1f}% | PF7: {row['pf7']:.2f} | "
                f"成交量比: {row['volume_ratio']:.2f}x"
            )
        
        # 显示所有股票的详细数据
        with st.expander("查看所有股票的详细数据"):
            st.dataframe(df_success.sort_values('pf7', ascending=False))
        
        # 显示数据统计
        st.subheader("数据统计")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("平均PF7", f"{df_success['pf7'].mean():.2f}")
        with col2:
            st.metric("平均胜率", f"{df_success['prob7'].mean()*100:.1f}%")
        with col3:
            st.metric("平均得分", f"{df_success['score'].mean():.2f}")

st.info("💡 这个工具使用与第一段代码完全相同的算法，包括：")
st.info("1. 相同的数据获取（要求≥100个数据点）")
st.info("2. 相同的滚动平均填充方式（关键差异！）")
st.info("3. 相同的回测函数调用：backtest_with_stats(close[:-1], score_arr[:-1], 7)")
st.info("4. 相同的5个技术指标和阈值")
st.info("5. 相同的筛选条件：PF7≥3.6 或 7日概率≥68%")
