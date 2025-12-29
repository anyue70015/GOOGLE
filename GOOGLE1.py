import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO
from datetime import datetime

st.set_page_config(page_title="回测信号面板 - 全市场扫描版", layout="wide")
st.markdown(
    """
    <style>
    body { background:#05060a; }
    .main { background:#05060a; padding-top:10px !important; }

    h1 { font-size:26px !important; font-weight:700 !important; margin-bottom:6px !important; }

    .card {
        background:#14151d;
        border-radius:14px;
        padding:14px 16px 12px;
        border:1px solid #262736;
        box-shadow:0 18px 36px rgba(0,0,0,0.45);
        color:#f5f5f7;
        font-size:13px;
        transition:0.15s;
        margin-bottom:18px;
    }
    .card:hover {
        transform:translateY(-3px);
        box-shadow:0 26px 48px rgba(0,0,0,0.6);
    }

    .card-section {
        display:flex;
        justify-content:space-between;
        align-items:flex-end;
        gap:10px;
    }
    .section-divider {
        border-bottom:1px solid #1f2030;
        margin:10px 0;
    }

    .symbol-line {
        display:flex;
        gap:10px;
        align-items:center;
        font-size:19px;
        margin-bottom:2px;
    }
    .symbol-name { font-weight:800; }
    .symbol-ticker {
        font-size:12px;
        color:#9ca3af;
        padding:2px 6px;
        border:1px solid #262736;
        border-radius:10px;
        background:#0d0e13;
    }
    .symbol-price {
        font-size:19px;
    }
    .change-up { color:#4ade80; font-size:14px; }
    .change-down { color:#fb7185; font-size:14px; }

    .indicator-grid {
        display:flex;
        flex-direction:column;
        gap:8px;
        margin-top:4px;
    }
    .indicator-item {
        display:flex;
        align-items:center;
        justify-content:space-between;
        width:100%;
        background:#191b27;
        border:1px solid #202233;
        border-radius:10px;
        padding:8px 10px;
        font-size:12px;
        color:#d4d4d8;
    }
    .dot { width:6px;height:6px;border-radius:2px;display:inline-block;margin-left:6px; }
    .dot-bull { background:#4ade80; box-shadow:0 0 0 1px rgba(74,222,128,0.25); }
    .dot-neutral { background:#facc15; box-shadow:0 0 0 1px rgba(250,204,21,0.25); }
    .dot-bear { background:#fb7185; box-shadow:0 0 0 1px rgba(251,113,133,0.25); }

    .label { color:#9ca3af; }
    .prob-good { color:#4ade80; font-weight:600; }
    .prob-mid { color:#facc15; font-weight:600; }
    .prob-bad { color:#fb7185; font-weight:600; }

    .score{
        font-size:12px;
        color:#9ca3af;
        margin-top:8px;
        display:flex;
        align-items:center;
        gap:8px;
    }
    .score-label{
        font-size:13px;
        font-weight:700;
        color:#e5e7eb;
        min-width:70px;
    }
    .dot-score{
        width:9px;
        height:9px;
        border-radius:50%;
        display:inline-block;
        margin-right:2px;
    }
    .dot-score-buy{ background:#4ade80; }
    .dot-score-hold{ background:#facc15; }
    .dot-score-sell{ background:#fb7185; }
    .dot-score-off{ background:#4b5563; }
    .advice-text{
        font-size:13px;
        font-weight:600;
    }
    .advice-buy{ color:#4ade80; }
    .advice-hold{ color:#facc15; }
    .advice-sell{ color:#fb7185; }
    .profit-row { font-size:12px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🔥 回测信号面板 - 全市场扫描版")

# ==================== 原完整常量 ====================
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

BACKTEST_OPTIONS = ["1年", "6个月", "2年", "3年", "5年", "10年"]
BACKTEST_CONFIG = {
    "3个月": {"range": "3mo", "interval": "1d", "steps_per_day": 1},
    "6个月": {"range": "6mo", "interval": "1d", "steps_per_day": 1},
    "1年":  {"range": "1y",  "interval": "1d", "steps_per_day": 1},
    "2年":  {"range": "2y",  "interval": "1d", "steps_per_day": 1},
    "3年":  {"range": "3y",  "interval": "1d", "steps_per_day": 1},
    "5年":  {"range": "5y",  "interval": "1d", "steps_per_day": 1},
    "10年": {"range": "10y", "interval": "1d", "steps_per_day": 1},
}

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range}&interval={interval}"

# ==================== 原所有函数（一字不改） ====================
def format_symbol_for_yahoo(symbol: str) -> str:
    sym = symbol.strip().upper()
    if not sym:
        raise ValueError("股票代码不能为空")

    if sym.isdigit() and len(sym) == 6:
        if sym.startswith(("600", "601", "603", "605", "688")):
            return f"{sym}.SS"
        if sym.startswith(("000", "001", "002", "003", "300")):
            return f"{sym}.SZ"

    return sym


def contains_chinese(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def search_eastmoney_symbol(query: str):
    try:
        resp = requests.get(
            "https://searchapi.eastmoney.com/api/suggest/get",
            params={
                "input": query,
                "type": "14",
                "token": "BD5FB5E653E986E07EED55F0F9F3CD9D",
                "format": "json",
                "count": 10,
            },
            headers={"Referer": "https://www.eastmoney.com"},
            timeout=10,
        )
        data = resp.json()
        table = data.get("QuotationCodeTable") or data.get("Data") or {}
        records = (
            table.get("Data")
            or table.get("data")
            or data.get("items")
            or []
        )
        for rec in records:
            code = rec.get("Code") or rec.get("code")
            name = rec.get("Name") or rec.get("name")
            market = str(rec.get("Market") or rec.get("market") or "")
            if code and len(code) == 6 and market in {"0", "1"}:
                return code, name, market
    except Exception:
        return None

    return None


def search_yahoo_symbol_by_name(query: str):
    try:
        resp = requests.get(
            "https://query1.finance.yahoo.com/v1/finance/search",
            params={
                "q": query,
                "quotes_count": 15,
                "news_count": 0,
                "lang": "zh-Hans",
                "region": "HK",
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        data = resp.json()
        for item in data.get("quotes", []):
            symbol = item.get("symbol", "")
            if not (symbol.endswith(".SS") or symbol.endswith(".SZ")):
                continue
            name = item.get("shortname") or item.get("longname") or item.get("exchDisp")
            return symbol.replace(".SS", "").replace(".SZ", ""), name, ""
    except Exception:
        return None

    return None


def resolve_user_input_symbol(user_input: str) -> str:
    raw = user_input.strip()
    if not raw:
        raise ValueError("请输入股票代码或名称")

    if raw.isdigit() and len(raw) == 6:
        return raw

    em_hit = search_eastmoney_symbol(raw)
    if em_hit:
        return em_hit[0]

    yahoo_hit = search_yahoo_symbol_by_name(raw)
    if yahoo_hit:
        return yahoo_hit[0]

    if contains_chinese(raw):
        raise ValueError("未找到匹配的 A 股代码，请改用 6 位代码或美股代码（示例：600519 / TSLA）")

    return raw.upper()


@st.cache_data(show_spinner=False)
def fetch_display_name(symbol: str, yahoo_symbol: str) -> str:
    clean_sym = symbol.strip()

    if clean_sym.isdigit() and len(clean_sym) == 6:
        market_code = "1" if yahoo_symbol.endswith(".SS") else "0"
        try:
            resp = requests.get(
                "https://push2.eastmoney.com/api/qt/stock/get",
                params={"secid": f"{market_code}.{clean_sym}", "fields": "f58,f57"},
                headers={"Referer": "https://quote.eastmoney.com"},
                timeout=8,
            )
            data = resp.json()
            name = data.get("data", {}).get("f58")
            if name:
                return name
        except Exception:
            pass

    try:
        resp = requests.get(
            "https://query1.finance.yahoo.com/v7/finance/quote",
            params={"symbols": yahoo_symbol},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        quote = resp.json().get("quoteResponse", {}).get("result", [])
        if quote:
            info = quote[0]
            for key in ("longName", "shortName", "displayName", "symbol"):
                name = info.get(key)
                if name:
                    return name
    except Exception:
        pass

    return yahoo_symbol


def fetch_yahoo_ohlcv(symbol: str, range_str: str, interval: str):
    url = YAHOO_URL.format(symbol=symbol, range=range_str, interval=interval)
    resp = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15,
    )
    data = resp.json()
    if "chart" not in data or not data["chart"].get("result"):
        raise ValueError("Yahoo 无返回数据")

    result = data["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]

    close = np.array(quote["close"], dtype="float64")
    high = np.array(quote["high"], dtype="float64")
    low = np.array(quote["low"], dtype="float64")
    volume = np.array(quote["volume"], dtype="float64")

    mask = ~np.isnan(close)
    close = close[mask]
    high = high[mask]
    low = low[mask]
    volume = volume[mask]

    if len(close) < 80:
        raise ValueError("可用历史数据太少")

    return close, high, low, volume


def ema_np(x: np.ndarray, span: int) -> np.ndarray:
    alpha = 2 / (span + 1)
    ema = np.zeros_like(x, dtype=float)
    ema[0] = x[0]
    for i in range(1, len(x)):
        ema[i] = alpha * x[i] + (1 - alpha) * ema[i - 1]
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

    gain_ema = np.zeros_like(gain)
    loss_ema = np.zeros_like(loss)

    alpha = 1 / period
    gain_ema[0] = gain[0]
    loss_ema[0] = loss[0]
    for i in range(1, len(gain)):
        gain_ema[i] = alpha * gain[i] + (1 - alpha) * gain_ema[i - 1]
        loss_ema[i] = alpha * loss[i] + (1 - alpha) * loss_ema[i - 1]

    rs = gain_ema / (loss_ema + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def atr_np(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr1 = high - low
    tr2 = np.abs(high - prev_close)
    tr3 = np.abs(low - prev_close)
    tr = np.maximum(tr1, np.maximum(tr2, tr3))

    atr = np.zeros_like(tr)
    atr[0] = tr[0]
    alpha = 1 / period
    for i in range(1, len(tr)):
        atr[i] = alpha * tr[i] + (1 - alpha) * atr[i - 1]
    return atr


def rolling_mean_np(x: np.ndarray, window: int) -> np.ndarray:
    if len(x) < window:
        return np.full_like(x, x.mean(), dtype=float)
    cumsum = np.cumsum(np.insert(x, 0, 0.0))
    ma = (cumsum[window:] - cumsum[:-window]) / window
    head = np.full(window - 1, ma[0])
    return np.concatenate([head, ma])


def obv_np(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    direction = np.sign(np.diff(close, prepend=close[0]))
    return np.cumsum(direction * volume)


def backtest_with_stats(close: np.ndarray, score: np.ndarray, steps: int, min_score: int = 3):
    if len(close) <= steps:
        return 0.0, 0.0, 0, 0.0, 0.0, 0, 0.0, 0.0

    idx = np.where(score[:-steps] >= min_score)[0]
    if len(idx) == 0:
        return 0.0, 0.0, 0, 0.0, 0.0, 0, 0.0, 0.0

    rets = close[idx + steps] / close[idx] - 1.0
    signals = len(rets)
    win_mask = rets > 0
    loss_mask = rets < 0

    wins = int(win_mask.sum())
    losses = int(loss_mask.sum())

    win_rate = float(win_mask.mean())
    avg_ret = float(rets.mean())

    profit_rets = rets[win_mask]
    loss_rets = rets[loss_mask]

    avg_win = float(profit_rets.mean()) if wins > 0 else 0.0
    avg_loss = float(loss_rets.mean()) if losses > 0 else 0.0

    profit_sum = float(profit_rets.sum())
    loss_sum = float(-loss_rets.sum())

    if loss_sum > 0:
        pf = profit_sum / loss_sum
    else:
        pf = 0.0

    equity = np.cumprod(1 + rets)
    peak = np.maximum.accumulate(equity)
    dd = equity / peak - 1
    max_dd = float(dd.min())

    return win_rate, avg_ret, signals, max_dd, pf, wins, avg_win, avg_loss


def prob_class(p):
    if p >= 0.65:
        return "prob-good"
    if p >= 0.45:
        return "prob-mid"
    return "prob-bad"


def decide_advice(prob: float, pf: float):
    if pf <= 0:
        pf = 0.0

    if prob >= 0.60 and pf >= 1.20:
        kind = "buy"
    elif prob <= 0.40 and pf <= 0.80:
        kind = "sell"
    else:
        kind = "hold"

    if kind == "buy":
        score = 0
        if prob >= 0.60: score += 1
        if prob >= 0.65: score += 1
        if prob >= 0.70: score += 1
        if pf   >= 1.20: score += 1
        if pf   >= 1.60: score += 1
        intensity = max(1, min(5, score))
        label = "建议买入"
        color = "buy"
    elif kind == "sell":
        score = 0
        if prob <= 0.40: score += 1
        if prob <= 0.35: score += 1
        if prob <= 0.30: score += 1
        if pf   <= 0.80: score += 1
        if pf   <= 0.60: score += 1
        intensity = max(1, min(5, score))
        label = "建议卖出"
        color = "sell"
    else:
        score = 1
        if 0.45 <= prob <= 0.55: score += 1
        if 0.47 <= prob <= 0.53: score += 1
        if 0.90 <= pf <= 1.10:   score += 1
        if 0.95 <= pf <= 1.05:   score += 1
        intensity = max(1, min(5, score))
        label = "观望"
        color = "hold"

    return label, intensity, color


def build_advice_html(label, intensity, kind):
    if kind == "buy":
        dot_on_class = "dot-score dot-score-buy"
        advice_class = "advice-text advice-buy"
    elif kind == "sell":
        dot_on_class = "dot-score dot-score-sell"
        advice_class = "advice-text advice-sell"
    else:
        dot_on_class = "dot-score dot-score-hold"
        advice_class = "advice-text advice-hold"
    dots = (
        f"<span class='{dot_on_class}'></span>" * intensity +
        "<span class='dot-score dot-score-off'></span>" * (5 - intensity)
    )
    return advice_class, label, dots


def compute_stock_metrics(symbol: str, cfg_key: str):
    cfg = BACKTEST_CONFIG[cfg_key]
    yahoo_symbol = format_symbol_for_yahoo(symbol)
    display_name = fetch_display_name(symbol, yahoo_symbol)
    close, high, low, volume = fetch_yahoo_ohlcv(
        yahoo_symbol, range_str=cfg["range"], interval=cfg["interval"]
    )

    if len(close) > 81:
        close = close[:-1]
        high = high[:-1]
        low = low[:-1]
        volume = volume[:-1]

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

    spd = cfg["steps_per_day"]
    steps7 = 7 * spd
    steps30 = 30 * spd

    prob7, avg7, signals7, max_dd7, pf7, wins7, avg_win7, avg_loss7 = backtest_with_stats(
        close, score_arr, steps=steps7
    )
    prob30, avg30, signals30, max_dd30, pf30, wins30, avg_win30, avg_loss30 = backtest_with_stats(
        close, score_arr, steps=steps30
    )

    last_close = close[-1]
    prev_close = close[-2] if len(close) >= 2 else close[-1]
    change_pct = (last_close / prev_close - 1.0) * 100
    last_idx = -1

    indicators = []

    macd_val = float(macd_hist[last_idx])
    macd_status = "bull" if macd_val > 0 else "bear"
    indicators.append({
        "name": "MACD 多头/空头",
        "status": macd_status,
        "desc": ""
    })

    vol_ratio = float(volume[last_idx] / (vol_ma20[last_idx] + 1e-9))
    vol_target = 1.10
    if vol_ratio > vol_target:
        vol_status = "bull"
    elif vol_ratio < 0.90:
        vol_status = "bear"
    else:
        vol_status = "neutral"
    indicators.append({
        "name": "成交量相对20日均量",
        "status": vol_status,
        "desc": f"{vol_target:.2f} / {vol_ratio:.2f}"
    })

    rsi_val = float(rsi[last_idx])
    if rsi_val >= 60:
        rsi_status = "bull"
    elif rsi_val <= 40:
        rsi_status = "bear"
    else:
        rsi_status = "neutral"
    indicators.append({
        "name": "RSI 区间",
        "status": rsi_status,
        "desc": f"60.0 / {rsi_val:.1f}"
    })

    atr_ratio = float(atr[last_idx] / (atr_ma20[last_idx] + 1e-9))
    if atr_ratio > 1.10:
        atr_status = "bull"
    elif atr_ratio < 0.90:
        atr_status = "bear"
    else:
        atr_status = "neutral"
    indicators.append({
        "name": "ATR 波动率",
        "status": atr_status,
        "desc": f"1.10 / {atr_ratio:.2f}"
    })

    obv_ratio = float(obv[last_idx] / (obv_ma20[last_idx] + 1e-9))
    if obv_ratio > 1.05:
        obv_status = "bull"
    elif obv_ratio < 0.95:
        obv_status = "bear"
    else:
        obv_status = "neutral"
    indicators.append({
        "name": "OBV 资金趋势",
        "status": obv_status,
        "desc": f"1.05 / {obv_ratio:.2f}"
    })

    return {
        "symbol": yahoo_symbol,
        "display_name": display_name,
        "price": float(last_close),
        "change": float(change_pct),
        "prob7": float(prob7),
        "prob30": float(prob30),
        "avg7": float(avg7),
        "avg30": float(avg30),
        "pf7": float(pf7),
        "pf30": float(pf30),
        "avg_win7": float(avg_win7),
        "avg_loss7": float(avg_loss7),
        "avg_win30": float(avg_win30),
        "avg_loss30": float(avg_loss30),
        "indicators": indicators,
    }


@st.cache_data(show_spinner=False)
def get_stock_metrics_cached(symbol: str, cfg_key: str, version: int = 15):
    return compute_stock_metrics(symbol, cfg_key=cfg_key)


# ==================== 新增：股票列表 ====================
COMMON_ETFS = ["SPY","QQQ","IWM","DIA","TLT","GLD","SLV","USO","UNG","BITO","ARKK","SOXX","SMH","XLE","XLF","XLV","XLK","XBI","KWEB","EEM","EWZ"]

@st.cache_data(ttl=86400)
def get_nasdaq100():
    try:
        df = pd.read_csv("https://raw.githubusercontent.com/datasets/nasdaq-100-companies/main/data/nasdaq-100.csv")
        return df['Symbol'].tolist()
    except:
        return []

@st.cache_data(ttl=86400)
def get_sp500():
    try:
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
        df = pd.read_csv(StringIO(requests.get(url, headers=HEADERS).text))
        return df['Symbol'].tolist()
    except:
        return []

all_tickers = list(set(get_nasdaq100() + get_sp500() + COMMON_ETFS))
all_tickers.sort()

# ==================== 侧边栏单股查询 ====================
st.sidebar.header("🔍 单股深度查询")
single_sym = st.sidebar.text_input("输入代码（如 NVDA / 600519）", "")
mode_single = st.sidebar.selectbox("查询周期", list(BACKTEST_CONFIG.keys()), index=2)

if single_sym:
    with st.sidebar:
        with st.spinner("查询中..."):
            try:
                metrics = get_stock_metrics_cached(single_sym, mode_single)
                change_class = "change-up" if metrics["change"] >= 0 else "change-down"
                change_str = f"{metrics['change']:+.2f}%"

                prob7_pct = metrics["prob7"] * 100
                prob30_pct = metrics["prob30"] * 100

                avg_win7_pct = metrics["avg_win7"] * 100
                avg_loss7_pct = metrics["avg_loss7"] * 100
                avg_win30_pct = metrics["avg_win30"] * 100
                avg_loss30_pct = metrics["avg_loss30"] * 100

                pf7 = metrics["pf7"]
                pf30 = metrics["pf30"]

                prob7_class = prob_class(metrics["prob7"])
                prob30_class = prob_class(metrics["prob30"])

                indicators_html = ""
                for ind in metrics["indicators"]:
                    if ind["desc"]:
                        line = f"{ind['name']} ({ind['desc']})"
                    else:
                        line = ind['name']
                    indicators_html += (
                        f"<div class='indicator-item'><span>{line}</span>"
                        f"<span class='dot dot-{ind['status']}'></span></div>"
                    )

                adv7_label, adv7_intensity, adv7_kind = decide_advice(metrics["prob7"], pf7)
                adv30_label, adv30_intensity, adv30_kind = decide_advice(metrics["prob30"], pf30)

                adv7_class, adv7_text, adv7_dots = build_advice_html(adv7_label, adv7_intensity, adv7_kind)
                adv30_class, adv30_text, adv30_dots = build_advice_html(adv30_label, adv30_intensity, adv30_kind)

                display_name = metrics.get("display_name", metrics["symbol"])

                html = f"""
                <div class="card">
                  <div class="card-section">
                    <div class="symbol-line">
                      <span class="symbol-name">{display_name}</span>
                      <span class="symbol-ticker">{metrics['symbol']}</span>
                    </div>
                    <div class="card-section" style="gap:6px;align-items:center;">
                      <span class="symbol-price">${metrics['price']:.2f}</span>
                      <span class="{change_class}">{change_str}</span>
                    </div>
                  </div>

                  <div class="section-divider"></div>

                  <div class="indicator-grid">
                    {indicators_html}
                  </div>

                  <div class="section-divider"></div>

                  <div>
                    <div class="profit-row" style="display:flex;justify-content:space-between;gap:8px;margin-bottom:4px;">
                      <div>
                        <span class="label">7日盈利概率</span>
                        <span class="{prob7_class}"> {prob7_pct:.1f}%</span>
                      </div>
                      <div class="label">均盈 {avg_win7_pct:+.1f}% / 均亏 {avg_loss7_pct:+.1f}% / 盈亏 {pf7:.2f}</div>
                    </div>
                    <div class="profit-row" style="display:flex;justify-content:space-between;gap:8px;">
                      <div>
                        <span class="label">30日盈利概率</span>
                        <span class="{prob30_class}"> {prob30_pct:.1f}%</span>
                      </div>
                      <div class="label">均盈 {avg_win30_pct:+.1f}% / 均亏 {avg_loss30_pct:+.1f}% / 盈亏 {pf30:.2f}</div>
                    </div>
                  </div>

                  <div class="section-divider"></div>

                  <div class="score">
                    <span class="score-label">7日信号</span>
                    <span class="{adv7_class}">{adv7_text}</span>
                    {adv7_dots}
                  </div>
                  <div class="score">
                    <span class="score-label">30日信号</span>
                    <span class="{adv30_class}">{adv30_text}</span>
                    {adv30_dots}
                  </div>
                </div>
                """
                st.markdown(html, unsafe_allow_html=True)
            except Exception as e:
                st.sidebar.error(f"查询失败: {e}")

# ==================== 全扫描 ====================
mode = st.selectbox("全扫描周期", list(BACKTEST_CONFIG.keys()), index=2)

if 'scanned' not in st.session_state:
    st.session_state.scanned = set()
if 'results' not in st.session_state:
    st.session_state.results = []

if len(st.session_state.scanned) < len(all_tickers):
    progress_bar = st.progress(0)
    status_text = st.empty()

    remaining = [s for s in all_tickers if s not in st.session_state.scanned]
    batch = remaining[:1]
    for sym in batch:
        status_text.text(f"扫描 {sym} ... ({len(st.session_state.scanned)+1}/{len(all_tickers)})")
        try:
            metrics = get_stock_metrics_cached(sym, mode)
            st.session_state.results.append(metrics)
        except:
            pass
        st.session_state.scanned.add(sym)
        time.sleep(8)
        progress_bar.progress(len(st.session_state.scanned) / len(all_tickers))
        st.rerun()

# ==================== 原完整展示 + 导出 ====================
if st.session_state.results:
    rows = st.session_state.results[:]
    rows = sorted(rows, key=lambda x: x["prob7"], reverse=True)

    st.subheader(f"🔥 精选信号股（共 {len(rows)} 只） - 周期：{mode}")

    progress_bar = st.progress(len(st.session_state.scanned) / len(all_tickers))
    st.write(f"扫描进度：{len(st.session_state.scanned)} / {len(all_tickers)} 只")

    cols_per_row = 4
    for i in range(0, len(rows), cols_per_row):
        cols = st.columns(cols_per_row)
        for col, row in zip(cols, rows[i:i + cols_per_row]):
            with col:
                change_class = "change-up" if row["change"] >= 0 else "change-down"
                change_str = f"{row['change']:+.2f}%"

                prob7_pct = row["prob7"] * 100
                prob30_pct = row["prob30"] * 100

                avg_win7_pct = row["avg_win7"] * 100
                avg_loss7_pct = row["avg_loss7"] * 100

                avg_win30_pct = row["avg_win30"] * 100
                avg_loss30_pct = row["avg_loss30"] * 100

                pf7 = row["pf7"]
                pf30 = row["pf30"]

                prob7_class = prob_class(row["prob7"])
                prob30_class = prob_class(row["prob30"])

                indicators_html = ""
                for ind in row["indicators"]:
                    if ind["desc"]:
                        line = f"{ind['name']} ({ind['desc']})"
                    else:
                        line = ind["name"]
                    indicators_html += (
                        f"<div class='indicator-item'><span>{line}</span>"
                        f"<span class='dot dot-{ind['status']}'></span></div>"
                    )

                adv7_label, adv7_intensity, adv7_kind = decide_advice(row["prob7"], pf7)
                adv30_label, adv30_intensity, adv30_kind = decide_advice(row["prob30"], pf30)

                adv7_class, adv7_text, adv7_dots = build_advice_html(adv7_label, adv7_intensity, adv7_kind)
                adv30_class, adv30_text, adv30_dots = build_advice_html(adv30_label, adv30_intensity, adv30_kind)

                display_name = row.get("display_name", row["symbol"])
                ticker_label = row["symbol"]

                html = f"""
                <div class="card">
                  <div class="card-section">
                    <div class="symbol-line">
                      <span class="symbol-name">{display_name}</span>
                      <span class="symbol-ticker">{ticker_label}</span>
                    </div>
                    <div class="card-section" style="gap:6px;align-items:center;">
                      <span class="symbol-price">${row['price']:.2f}</span>
                      <span class="{change_class}">{change_str}</span>
                    </div>
                  </div>

                  <div class="section-divider"></div>

                  <div class="indicator-grid">
                    {indicators_html}
                  </div>

                  <div class="section-divider"></div>

                  <div>
                    <div class="profit-row" style="display:flex;justify-content:space-between;gap:8px;margin-bottom:4px;">
                      <div>
                        <span class="label">7日盈利概率</span>
                        <span class="{prob7_class}"> {prob7_pct:.1f}%</span>
                      </div>
                      <div class="label">均盈 {avg_win7_pct:+.1f}% / 均亏 {avg_loss7_pct:+.1f}% / 盈亏 {pf7:.2f}</div>
                    </div>
                    <div class="profit-row" style="display:flex;justify-content:space-between;gap:8px;">
                      <div>
                        <span class="label">30日盈利概率</span>
                        <span class="{prob30_class}"> {prob30_pct:.1f}%</span>
                      </div>
                      <div class="label">均盈 {avg_win30_pct:+.1f}% / 均亏 {avg_loss30_pct:+.1f}% / 盈亏 {pf30:.2f}</div>
                    </div>
                  </div>

                  <div class="section-divider"></div>

                  <div class="score">
                    <span class="score-label">7日信号</span>
                    <span class="{adv7_class}">{adv7_text}</span>
                    {adv7_dots}
                  </div>
                  <div class="score">
                    <span class="score-label">30日信号</span>
                    <span class="{adv30_class}">{adv30_text}</span>
                    {adv30_dots}
                  </div>
                </div>
                """
                st.markdown(html, unsafe_allow_html=True)

    report_lines = [f"--- 回测信号全扫描报告 ({mode}) {datetime.now().strftime('%Y-%m-%d %H:%M')} ---"]
    for row in rows:
        green = sum(1 for d in row["indicators"] if d["status"] == "bull")
        report_lines.append(
            f"{row['symbol']:8} {row.get('display_name',''):20} ${row['price']:.2f} {row['change']:+.2f}%  绿灯:{green}/5  7日:{row['prob7']*100:.1f}% PF{row['pf7']:.2f}  30日:{row['prob30']*100:.1f}% PF{row['pf30']:.2f}"
        )
    report_txt = "\n".join(report_lines)
    st.download_button("📥 导出报告.txt", report_txt.encode('utf-8'), f"信号扫描_{mode}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt")

if st.button("🔄 重置扫描"):
    st.session_state.scanned = set()
    st.session_state.results = []
    st.rerun()

st.caption("所有指标和回测均基于“上一根完整K线” · 8秒/只防封 · 仅供研究")
