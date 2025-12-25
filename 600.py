import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO, BytesIO

st.set_page_config(page_title="标普500 + 纳斯达克100 大盘扫描工具", layout="wide")
st.title("标普500 + 纳斯达克100 自动扫描工具（固定顺序 + 已扫不重扫 + 多改进）")

# ==================== 核心常量 ====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

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
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yahoo_ohlcv(yahoo_symbol: str, range_str: str, interval: str = "1d"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?range={range_str}&interval={interval}"
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
        return 0.5, 0.0, 0.0, 0.0
    idx = np.where(score[:-steps] >= 3)[0]
    if len(idx) == 0:
        return 0.5, 0.0, 0.0, 0.0
    rets = close[idx + steps] / close[idx] - 1
    win_rate = (rets > 0).mean()
    pf = rets[rets > 0].sum() / abs(rets[rets <= 0].sum()) if (rets <= 0).any() else 999
    avg_win = rets[rets > 0].mean() if (rets > 0).any() else 0
    avg_loss = rets[rets <= 0].mean() if (rets <= 0).any() else 0
    return win_rate, pf, avg_win, avg_loss

# ==================== 核心计算 ====================
@st.cache_data(show_spinner=False)
def compute_stock_metrics(symbol: str, cfg_key: str = "1年"):
    yahoo_symbol = symbol.upper()
    close, high, low, volume = fetch_yahoo_ohlcv(yahoo_symbol, BACKTEST_CONFIG[cfg_key]["range"])

    macd_hist = macd_hist_np(close)
    rsi = rsi_np(close)
    atr = atr_np(high, low, close)
    obv = obv_np(close, volume)
    vol_ma20 = rolling_mean_np(volume, 20)
    atr_ma20 = rolling_mean_np(atr, 20)
    obv_ma20 = rolling_mean_np(obv, 20)

    sig_macd = (macd_hist > 0).astype(int)[-1]
    sig_vol = (volume[-1] > vol_ma20[-1] * 1.1).astype(int)
    sig_rsi = (rsi[-1] >= 60).astype(int)
    sig_atr = (atr[-1] > atr_ma20[-1] * 1.1).astype(int)
    sig_obv = (obv[-1] > obv_ma20[-1] * 1.05).astype(int)
    score = sig_macd + sig_vol + sig_rsi + sig_atr + sig_obv

    sig_macd_hist = (macd_hist > 0).astype(int)
    sig_vol_hist = (volume > vol_ma20 * 1.1).astype(int)
    sig_rsi_hist = (rsi >= 60).astype(int)
    sig_atr_hist = (atr > atr_ma20 * 1.1).astype(int)
    sig_obv_hist = (obv > obv_ma20 * 1.05).astype(int)
    score_arr = sig_macd_hist + sig_vol_hist + sig_rsi_hist + sig_atr_hist + sig_obv_hist

    prob7, pf7, avg_win7, avg_loss7 = backtest_with_stats(close[:-1], score_arr[:-1], 7)
    prob30, pf30, avg_win30, avg_loss30 = backtest_with_stats(close[:-1], score_arr[:-1], 30)

    price = close[-1]
    change = (close[-1] / close[-2] - 1) * 100 if len(close) >= 2 else 0

    signals_detail = []
    if sig_macd: signals_detail.append("MACD柱>0")
    if sig_vol: signals_detail.append("放量>1.1x MA20")
    if sig_rsi: signals_detail.append("RSI≥60")
    if sig_atr: signals_detail.append("ATR放量>1.1x")
    if sig_obv: signals_detail.append("OBV>1.05x MA20")

    return {
        "symbol": symbol.upper(),
        "price": price,
        "change": change,
        "score": score,
        "signals": " | ".join(signals_detail) if signals_detail else "无",
        "prob7": prob7,
        "pf7": pf7,
        "prob30": prob30,
        "pf30": pf30,
    }

# ==================== 加载成分股（固定顺序） ====================
@st.cache_data(ttl=86400)
def load_sp500_tickers():
    url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text))
    return df['Symbol'].tolist()

# 更新为2025年12月最新Nasdaq-100列表（基于Wikipedia 2025-12-22更新）
ndx100 = ["ADBE","AMD","ABNB","ALNY","GOOGL","GOOG","AMZN","AEP","AMGN","ADI","AAPL","AMAT","APP","ARM","ASML","AZN","TEAM","ADSK","ADP","AXON","BKR","BKNG","AVGO","CDNS","CHTR","CTAS","CSCO","CCEP","CTSH","CMCSA","CEG","CPRT","CSGP","COST","CRWD","CSX","DDOG","DXCM","FANG","DASH","EA","EXC","FAST","FER","FTNT","GEHC","GILD","HON","IDXX","INSM","INTC","INTU","ISRG","KDP","KLAC","KHC","LRCX","LIN","MAR","MRVL","MELI","META","MCHP","MU","MSFT","MSTR","MDLZ","MPWR","MNST","NFLX","NVDA","NXPI","ORLY","ODFL","PCAR","PLTR","PANW","PAYX","PYPL","PDD","PEP","QCOM","REGN","ROP","ROST","STX","SHOP","SBUX","SNPS","TMUS","TTWO","TSLA","TXN","TRI","VRSK","VRTX","WBD","WDC","WDAY","XEL","ZS"]

sp500 = load_sp500_tickers()
all_tickers = list(set(sp500 + ndx100))
all_tickers.sort()  # 固定字母顺序

st.write(f"总计 {len(all_tickers)} 只股票（固定字母顺序） | Nasdaq-100 已更新至2025年12月最新")

mode = st.selectbox("回测周期", list(BACKTEST_CONFIG.keys()), index=2)
prob7_threshold = st.slider("7日盈利概率阈值 (%)", 50, 90, 65) / 100.0
sort_by = st.selectbox("结果排序方式", ["PF7 (盈利因子)", "7日概率", "PF30", "30日概率"], index=0)

# ==================== session_state ====================
if 'high_prob' not in st.session_state:
    st.session_state.high_prob = []
if 'scanned_symbols' not in st.session_state:
    st.session_state.scanned_symbols = set()
if 'failed_count' not in st.session_state:
    st.session_state.failed_count = 0

result_container = st.container()
progress_bar = st.progress(len(st.session_state.scanned_symbols) / len(all_tickers))
status_text = st.empty()

# ==================== 实时显示 ====================
with result_container:
    if st.session_state.high_prob:
        if sort_by == "PF7 (盈利因子)":
            displayed = sorted(st.session_state.high_prob, key=lambda x: x["pf7"], reverse=True)
        elif sort_by == "PF30":
            displayed = sorted(st.session_state.high_prob, key=lambda x: x["pf30"], reverse=True)
        elif sort_by == "30日概率":
            displayed = sorted(st.session_state.high_prob, key=lambda x: x["prob30"], reverse=True)
        else:
            displayed = sorted(st.session_state.high_prob, key=lambda x: x["prob7"], reverse=True)
        
        st.subheader(f"已发现 {len(displayed)} 只 ≥ {prob7_threshold*100:.0f}% (7日概率) 的股票（实时排序：{sort_by}）")
        for row in displayed:
            change_str = f"{row['change']:+.2f}%"
            st.markdown(f"**{row['symbol']}** - 价格: ${row['price']:.2f} ({change_str}) - "
                        f"得分: {row['score']}/5 ({row['signals']}) - "
                        f"**7日概率: {row['prob7']*100:.1f}% | PF7: {row['pf7']:.2f}** - "
                        f"30日概率: {row['prob30']*100:.1f}% | PF30: {row['pf30']:.2f}")

# 导出CSV
if st.session_state.high_prob:
    df_export = pd.DataFrame(st.session_state.high_prob)
    csv = df_export.to_csv(index=False).encode()
    st.download_button(
        label="导出当前结果为CSV",
        data=csv,
        file_name=f"高概率股票_{time.strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )

st.info(f"已扫描: {len(st.session_state.scanned_symbols)}/{len(all_tickers)} | 失败: {st.session_state.failed_count} | 已发现高概率: {len(st.session_state.high_prob)}")

# ==================== 自动扫描 ====================
with st.spinner("自动扫描中（保持页面打开）..."):
    for sym in all_tickers:
        if sym in st.session_state.scanned_symbols:
            continue
        status_text.text(f"正在计算 {sym} ({len(st.session_state.scanned_symbols)+1}/{len(all_tickers)})")
        progress_bar.progress((len(st.session_state.scanned_symbols) + 1) / len(all_tickers))
        try:
            metrics = compute_stock_metrics(sym, mode)
            st.session_state.scanned_symbols.add(sym)
            if metrics["prob7"] >= prob7_threshold:
                st.session_state.high_prob.append(metrics)
                with result_container:
                    st.rerun()
        except Exception as e:
            st.session_state.failed_count += 1
            st.warning(f"{sym} 失败: {str(e)}")
            st.session_state.scanned_symbols.add(sym)
        time.sleep(8)

st.success("所有股票扫描完成！结果永久保存")

if st.button("重置所有进度（从头开始）"):
    st.session_state.high_prob = []
    st.session_state.scanned_symbols = set()
    st.session_state.failed_count = 0
    st.rerun()

st.caption("改进版：Nasdaq-100更新至2025年12月最新 | 显示得分明细 | 支持PF排序 | 新增30日胜率/PF | 支持导出CSV | 实时更新")
