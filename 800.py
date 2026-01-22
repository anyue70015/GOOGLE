import streamlit as st
import requests
import numpy as np
import time
import re

# ==================== 页面设置 ====================
st.set_page_config(page_title="回测信号面板 - 自助扫描", layout="wide")

st.markdown(
    """
    <style>
    body { background:#05060a; }
    .main { background:#05060a; padding-top:10px !important; }
    h1 { font-size:26px !important; font-weight:700 !important; margin-bottom:6px !important; }
    .stCode { background:#14151d; border:1px solid #262736; border-radius:10px; padding:12px; color:#e5e7eb; font-family:Consolas, monospace; white-space:pre; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("回测信号面板 - 自助扫描（按PF7排序）")

# ==================== 配置 ====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

BACKTEST_OPTIONS = ["3个月", "6个月", "1年", "2年", "3年", "5年", "10年"]
BACKTEST_CONFIG = {
    "3个月": {"range": "3mo", "interval": "1d"},
    "6个月": {"range": "6mo", "interval": "1d"},
    "1年":  {"range": "1y",  "interval": "1d"},
    "2年":  {"range": "2y",  "interval": "1d"},
    "3年":  {"range": "3y",  "interval": "1d"},
    "5年":  {"range": "5y",  "interval": "1d"},
    "10年": {"range": "10y", "interval": "1d"},
}

# ==================== 工具函数 ====================
def format_symbol_for_yahoo(symbol: str) -> str:
    sym = symbol.strip().upper()
    if sym.isdigit() and len(sym) == 6:
        if sym.startswith(("600", "601", "603", "605", "688")):
            return f"{sym}.SS"
        if sym.startswith(("000", "001", "002", "003", "300", "301")):
            return f"{sym}.SZ"
    return sym

@st.cache_data(ttl=300)
def get_current_prices_batch(symbols: list):
    if not symbols:
        return {}
    yahoo_syms = ",".join(format_symbol_for_yahoo(s) for s in symbols)
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={yahoo_syms}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()["quoteResponse"]["result"]
        result = {}
        for d in data:
            if d and 'symbol' in d:
                orig_sym = d["symbol"].replace(".SS","").replace(".SZ","").upper()
                price = d.get("regularMarketPrice") or d.get("regularMarketPreviousClose")
                change = d.get("regularMarketChangePercent", 0) * 100
                result[orig_sym] = (float(price) if price else None, float(change))
        return result
    except Exception as e:
        st.warning(f"批量价格获取失败: {str(e)}")
        return {}

@st.cache_data(ttl=3600)
def fetch_yahoo_ohlcv(yahoo_symbol: str, range_str: str, interval: str):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?range={range_str}&interval={interval}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()["chart"]["result"][0]
        quote = data["indicators"]["quote"][0]
        close = np.array(quote["close"], dtype=float)
        high = np.array(quote["high"], dtype=float)
        low = np.array(quote["low"], dtype=float)
        volume = np.array(quote["volume"], dtype=float)
        mask = ~np.isnan(close)
        return close[mask], high[mask], low[mask], volume[mask]
    except Exception as e:
        st.warning(f"OHLCV加载失败 {yahoo_symbol}: {str(e)}")
        return None, None, None, None

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
        return np.full_like(x, x.mean())
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

# ==================== 计算单股票 ====================
def compute_stock_metrics(symbol: str, cfg_key: str):
    yahoo_symbol = format_symbol_for_yahoo(symbol)
    try:
        close, high, low, volume = fetch_yahoo_ohlcv(yahoo_symbol, BACKTEST_CONFIG[cfg_key]["range"], "1d")
        if close is None or len(close) < 80:
            return {"symbol": symbol.upper(), "error": "数据不足或加载失败"}

        macd_hist = macd_hist_np(close)
        rsi = rsi_np(close)
        atr = atr_np(high, low, close)
        obv = obv_np(close, volume)
        vol_ma20 = rolling_mean_np(volume, 20)
        atr_ma20 = rolling_mean_np(atr, 20)
        obv_ma20 = rolling_mean_np(obv, 20)

        sig_macd = (macd_hist > 0).astype(int)
        sig_vol = (volume > vol_ma20 * 1.1).astype(int)
        sig_rsi = (rsi >= 60).astype(int)
        sig_atr = (atr > atr_ma20 * 1.1).astype(int)
        sig_obv = (obv > obv_ma20 * 1.05).astype(int)
        score_arr = sig_macd + sig_vol + sig_rsi + sig_atr + sig_obv

        steps7 = 7
        prob7, pf7, _, _ = backtest_with_stats(close[:-1], score_arr[:-1], steps7)

        return {
            "symbol": symbol.upper(),
            "price": None,  # 后面批量覆盖
            "change": 0.0,
            "prob7": prob7,
            "pf7": pf7,
            "score": score_arr[-1],
            "macd_yes": macd_hist[-1] > 0,
            "vol_yes": volume[-1] > vol_ma20[-1]*1.1,
            "rsi_yes": rsi[-1] >= 60,
            "atr_yes": atr[-1] > atr_ma20[-1]*1.1,
            "obv_yes": obv[-1] > obv_ma20[-1]*1.05,
        }
    except Exception as e:
        return {"symbol": symbol.upper(), "error": str(e)}

# ==================== 交互 ====================
col1, col2 = st.columns([3, 1])
with col1:
    default_tickers = """LLY
GEV
MIRM
ABBV
HWM
GE
MU
HII
SCCO
SNDK
WDC
SLV
STX
JNJ
WBD
FOXA
BK
RTX
WELL
PH
GVA
AHR
ATRO
GLW
CMI
APH
PM
COR
CAH
HCA
NEM"""
    tickers_input = st.text_area(
        "输入股票代码（一行一个，或逗号/空格分隔）",
        value=default_tickers,
        height=200,
        key="tickers_input"
    )

with col2:
    if st.button("开始扫描", type="primary", use_container_width=True):
        raw = tickers_input.strip()
        symbols = []
        for line in raw.splitlines():
            cleaned = re.sub(r'[^A-Za-z0-9.\-]', ' ', line).strip()
            symbols.extend([s for s in cleaned.split() if s])
        symbols = list(dict.fromkeys([s.upper() for s in symbols if s]))  # 去重

        if not symbols:
            st.warning("请输入至少一个股票代码")
        else:
            with st.spinner(f"扫描中... ({len(symbols)} 个股票)"):
                batch_prices = get_current_prices_batch(symbols)

                results = []
                for sym in symbols:
                    metrics = compute_stock_metrics(sym, st.session_state.get("mode", "2年"))
                    if sym in batch_prices:
                        metrics["price"], metrics["change"] = batch_prices[sym]
                    else:
                        metrics["price"] = "N/A"
                        metrics["change"] = 0.0
                    results.append(metrics)
                    time.sleep(0.4)  # 防限流

                # 存储结果
                st.session_state["scan_results"] = results

# ==================== 显示结果（纯文本，按PF7降序） ====================
if "scan_results" in st.session_state:
    results = st.session_state["scan_results"]
    valid_results = [r for r in results if "error" not in r and isinstance(r.get("pf7"), (int, float))]

    if valid_results:
        valid_results.sort(key=lambda x: x["pf7"], reverse=True)

        lines = []
        for row in valid_results:
            change_str = f"{row['change']:+.2f}%"
            score_str = f"{int(row['score'])}/5"
            macd_str = "是" if row["macd_yes"] else "否"
            vol_str  = "是" if row["vol_yes"] else "否"
            rsi_str  = "是" if row["rsi_yes"] else "否"
            atr_str  = "是" if row["atr_yes"] else "否"
            obv_str  = "是" if row["obv_yes"] else "否"
            price_str = f"{row['price']:.2f}" if isinstance(row['price'], (int, float)) else row['price']

            line = (
                f"{row['symbol']} - "
                f"价格: ${price_str} ({change_str}) - "
                f"得分: {score_str} - "
                f"MACD>0: {macd_str} | 放量: {vol_str} | RSI≥60: {rsi_str} | ATR放大: {atr_str} | OBV上升: {obv_str} - "
                f"7日概率: {row['prob7']*100:.1f}% | PF7: {row['pf7']:.2f}"
            )
            lines.append(line)

        st.subheader("扫描结果（按 PF7 降序）")
        st.code("\n".join(lines), language="text")

        if st.button("复制到剪贴板（实验性）"):
            st.write("请手动选中上面代码块 → Ctrl+C 复制")
    else:
        st.info("暂无有效结果，或所有股票加载失败。请检查网络/Yahoo数据。")

st.caption("数据来源: Yahoo Finance | 仅供研究参考，不构成投资建议 | 当前时间: 2026年1月")
