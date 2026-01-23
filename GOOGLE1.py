import streamlit as st
import yfinance as yf
import numpy as np
import time
import pandas as pd
import random
import os
import json

st.set_page_config(page_title="30只强势股 短线扫描工具", layout="wide")
st.title("30只强势股 短线扫描工具")

# ── 持久化进度文件 ──
progress_file = "scan_progress_30.json"

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
            st.success("已加载历史进度，可继续扫描")
        except Exception as e:
            st.warning(f"加载进度失败: {e}，从头开始")

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
col1, col2 = st.columns(2)
with col1:
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

with col2:
    if st.button("🔄 重置所有进度（从头开始）"):
        st.session_state.high_prob = []
        st.session_state.scanned_symbols = set()
        st.session_state.failed_count = 0
        st.session_state.fully_scanned = False
        st.session_state.scanning = False
        if os.path.exists(progress_file):
            os.remove(progress_file)
        st.rerun()

st.write("当前只扫描以下 **30只强势股**，低流动性标的会标注⚠️。点击开始扫描后会自动持续运行（每批次刷新一次）。")

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
        time.sleep(random.uniform(0.2, 0.6))
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

# ==================== 指标函数（保持原样） ====================
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
    yahoo_symbol = symbol.upper()  # 全部美股，无需-USD
    
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
        "is_crypto": False,
        "is_low_liquidity": is_low_liquidity
    }

# ==================== 唯一扫描列表：30只强势股 ====================
strong_30 = [
    "SMCI", "CRDO", "WDAY", "KLAC", "LRCX", "AMD", "NVDA", "TSLA", "META", "AMZN",
    "MSFT", "GOOGL", "AVGO", "ARM", "QCOM", "MRVL", "CDNS", "SNPS", "PANW", "CRWD",
    "FTNT", "DDOG", "ZS", "APP", "PLTR", "MSTR", "COIN", "FCX", "AA", "ALB"
]

tickers_to_scan = strong_30
st.write(f"扫描标的：30只强势股（共 {len(tickers_to_scan)} 只）")

mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)
sort_by = st.selectbox("结果排序方式", ["PF7 (盈利因子)", "7日概率"], index=0)

# ==================== session_state 初始化 ====================
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

# ==================== 强制全部30只显示 ====================
forced_symbols = set(strong_30)
computed_symbols = {x["symbol"] for x in st.session_state.high_prob if x}
missing = forced_symbols - computed_symbols

for sym in missing:
    st.session_state.high_prob.append({
        "symbol": sym.upper(),
        "display_symbol": sym.upper() + " (待计算或无数据)",
        "price": 0.0,
        "change": "N/A",
        "score": 0,
        "prob7": 0.0,
        "pf7": 0.0,
        "sig_details": {"MACD>0": False, "放量": False, "RSI≥60": False, "ATR放大": False, "OBV上升": False},
        "is_crypto": False,
        "is_low_liquidity": False
    })

# ==================== 参数变更处理 ====================
total = len(tickers_to_scan)

if st.session_state.get("prev_mode") != mode:
    st.session_state.high_prob = []
    st.session_state.fully_scanned = False
    st.info("回测周期变更，已清除旧结果")

st.session_state.prev_mode = mode

# ==================== 进度条 ====================
progress_bar = st.progress(0)
status_text = st.empty()

current_completed = len(st.session_state.scanned_symbols.intersection(set(tickers_to_scan)))
progress_val = min(1.0, max(0.0, current_completed / total)) if total > 0 else 0.0
progress_bar.progress(progress_val)

# ==================== 显示结果 ====================
if st.session_state.high_prob:
    df_all = pd.DataFrame([x for x in st.session_state.high_prob if x is not None and x["symbol"] in tickers_to_scan])
    
    if not df_all.empty:
        stock_df = df_all[~df_all['is_crypto']].copy()  # 全部是股票
        
        super_stock = stock_df[(stock_df['pf7'] > 4.0) & (stock_df['prob7'] > 0.70)].copy()
        normal_stock = stock_df[((stock_df['pf7'] >= 3.6) | (stock_df['prob7'] >= 0.68)) & ~stock_df['symbol'].isin(super_stock['symbol'])].copy()
        
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
        
        if not super_stock.empty:
            df_s = format_and_sort(super_stock)
            st.subheader(f"🔥 超级优质（PF>4 & 7日>70%） 共 {len(df_s)} 只")
            for _, row in df_s.iterrows():
                details = row['sig_details']
                detail_str = " | ".join([f"{k}: {'是' if v else '否'}" for k,v in details.items()])
                liquidity_warning = " **⚠️ 低流动性 - 滑点风险高**" if row['is_low_liquidity'] else ""
                st.markdown(f"**🔥 {row['display_symbol']}** - ${row['price']:.2f} ({row['change']}) - 得分: {row['score']}/5 - {detail_str} - **7日概率: {row['prob7_fmt']} | PF7: {row['pf7']}**{liquidity_warning}")
        
        if not normal_stock.empty:
            df_n = format_and_sort(normal_stock)
            st.subheader(f"🔹 优质标的 共 {len(df_n)} 只")
            for _, row in df_n.iterrows():
                details = row['sig_details']
                detail_str = " | ".join([f"{k}: {'是' if v else '否'}" for k,v in details.items()])
                liquidity_warning = " **⚠️ 低流动性 - 滑点风险高**" if row['is_low_liquidity'] else ""
                st.markdown(f"**{row['display_symbol']}** - ${row['price']:.2f} ({row['change']}) - 得分: {row['score']}/5 - {detail_str} - **7日概率: {row['prob7_fmt']} | PF7: {row['pf7']}**{liquidity_warning}")
        
        if super_stock.empty and normal_stock.empty:
            st.warning("当前无满足条件的标的")

st.info(f"总标的: {total} | 已完成: {current_completed} | 有结果: {len(st.session_state.high_prob)} | 失败/跳过: {st.session_state.failed_count}")

# ==================== 扫描逻辑 ====================
if st.button("🚀 开始/继续扫描（自动持续运行）"):
    st.session_state.scanning = True

if st.session_state.scanning and current_completed < total:
    with st.spinner("扫描中（每批次刷新一次）..."):
        batch_size = 100  # 实际只有30只，所以一次跑完也行
        processed_in_this_run = 0
        
        remaining = [sym for sym in tickers_to_scan if sym not in st.session_state.scanned_symbols]
        
        for sym in remaining:
            if processed_in_this_run >= batch_size:
                break
            
            anticipated = current_completed + processed_in_this_run + 1
            progress_val = min(1.0, max(0.0, anticipated / total))
            
            status_text.text(f"计算 {sym} ({anticipated}/{total})")
            progress_bar.progress(progress_val)
            
            try:
                metrics = compute_stock_metrics(sym, mode)
                if metrics:
                    st.session_state.high_prob.append(metrics)
                else:
                    st.session_state.failed_count += 1
                st.session_state.scanned_symbols.add(sym)
            except Exception as e:
                st.warning(f"{sym} 异常: {str(e)}")
                st.session_state.failed_count += 1
                st.session_state.scanned_symbols.add(sym)
            
            processed_in_this_run += 1
        
        save_progress()
        
        new_completed = len(st.session_state.scanned_symbols.intersection(set(tickers_to_scan)))
        progress_bar.progress(min(1.0, max(0.0, new_completed / total)))
        
        if new_completed >= total:
            st.session_state.fully_scanned = True
            st.session_state.scanning = False
            st.success("扫描完成！")
        
        st.rerun()

if current_completed >= total:
    st.success("已完成全部30只扫描！")

st.caption("极简版 - 只保留30只强势股 | 2026年1月")
