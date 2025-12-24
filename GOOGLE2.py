import streamlit as st
import requests
import numpy as np

# ============ 页面基础设置 ============
st.set_page_config(page_title="回测信号面板", layout="wide")
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

st.title("回测信号面板")

# ============ 回测配置（日线） ============
BACKTEST_OPTIONS = ["3个月", "6个月", "1年", "2年", "3年", "5年", "10年"]
BACKTEST_CONFIG = {
    "3个月": {"range": "3mo", "interval": "1d", "steps_per_day": 1},
    "6个月": {"range": "6mo", "interval": "1d", "steps_per_day": 1},
    "1年":  {"range": "1y",  "interval": "1d", "steps_per_day": 1},
    "2年":  {"range": "2y",  "interval": "1d", "steps_per_day": 1},
    "3年":  {"range": "3y",  "interval": "1d", "steps_per_day": 1},
    "5年":  {"range": "5y",  "interval": "1d", "steps_per_day": 1},
    "10年": {"range": "10y", "interval": "1d", "steps_per_day": 1},
}

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range}&interval={interval}"
YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}"

# ============ 工具函数 ============
def format_symbol_for_yahoo(symbol: str) -> str:
    sym = symbol.strip().upper()
    if not sym:
        raise ValueError("股票代码不能为空")

    if sym.isdigit() and len(sym) == 6:
        if sym.startswith(("600", "601", "603", "605", "688")):
            return f"{sym}.SS"  # 上交所
        if sym.startswith(("000", "001", "002", "003", "300")):
            return f"{sym}.SZ"  # 深交所

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
        records = table.get("Data") or table.get("data") or data.get("items") or []
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
            YAHOO_QUOTE_URL.format(symbol=yahoo_symbol),
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

@st.cache_data(ttl=300)
def get_current_price(yahoo_symbol: str):
    try:
        resp = requests.get(
            YAHOO_QUOTE_URL.format(symbol=yahoo_symbol),
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        data = resp.json()["quoteResponse"]["result"][0]
        price = data.get("regularMarketPrice") or data.get("regularMarketPreviousClose")
        change_pct = data.get("regularMarketChangePercent", 0) * 100
        return float(price), float(change_pct)
    except Exception:
        return None, None

def fetch_yahoo_ohlcv(symbol: str, range_str: str, interval: str):
    url = YAHOO_CHART_URL.format(symbol=symbol, range=range_str, interval=interval)
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

# ============ 技术指标 ============
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

# ============ 回测统计 ============
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

    pf = profit_sum / loss_sum if loss_sum > 0 else 0.0

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

# ============ 建议逻辑 ============
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
        if pf >= 1.20: score += 1
        if pf >= 1.60: score += 1
        intensity = max(1, min(5, score))
        label = "建议买入"
        color = "buy"
    elif kind == "sell":
        score = 0
        if prob <= 0.40: score += 1
        if prob <= 0.35: score += 1
        if prob <= 0.30: score += 1
        if pf <= 0.80: score += 1
        if pf <= 0.60: score += 1
        intensity = max(1, min(5, score))
        label = "建议卖出"
        color = "sell"
    else:
        score = 1
        if 0.45 <= prob <= 0.55: score += 1
        if 0.47 <= prob <= 0.53: score += 1
        if 0.90 <= pf <= 1.10: score += 1
        if 0.95 <= pf <= 1.05: score += 1
        intensity = max(1, min(5, score))
        label = "观望"
        color = "hold"

    return label, intensity, color

# ============ 计算单只股票 ============
def compute_stock_metrics(symbol: str, cfg_key: str):
    cfg = BACKTEST_CONFIG[cfg_key]
    yahoo_symbol = format_symbol_for_yahoo(symbol)
    display_name = fetch_display_name(symbol, yahoo_symbol)

    # 获取实时价格和涨跌幅
    current_price, current_change = get_current_price(yahoo_symbol)

    # 获取历史 OHLCV 用于指标和回测
    close, high, low, volume = fetch_yahoo_ohlcv(
        yahoo_symbol, range_str=cfg["range"], interval=cfg["interval"]
    )

    # 计算指标（使用最新数据，包括最新完整K线）
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

    # 回测时用[:-1] 确保“上一完整K线”原则
    prob7, avg7, signals7, max_dd7, pf7, wins7, avg_win7, avg_loss7 = backtest_with_stats(
        close[:-1] if len(close) > 1 else close, score_arr[:-1] if len(score_arr) > 1 else score_arr, steps=steps7
    )
    prob30, avg30, signals30, max_dd30, pf30, wins30, avg_win30, avg_loss30 = backtest_with_stats(
        close[:-1] if len(close) > 1 else close, score_arr[:-1] if len(score_arr) > 1 else score_arr, steps=steps30
    )

    # 价格显示用实时数据，兜底用历史最后价
    price = current_price if current_price is not None else float(close[-1])
    change = current_change if current_change is not None else (float(close[-1] / close[-2] - 1) * 100 if len(close) >= 2 else 0.0)

    last_idx = -1

    indicators = []

    macd_val = float(macd_hist[last_idx])
    macd_status = "bull" if macd_val > 0 else "bear"
    indicators.append({"name": "MACD 多头/空头", "status": macd_status, "desc": ""})

    vol_ratio = float(volume[last_idx] / (vol_ma20[last_idx] + 1e-9))
    vol_target = 1.10
    vol_status = "bull" if vol_ratio > vol_target else "bear" if vol_ratio < 0.90 else "neutral"
    indicators.append({"name": "成交量相对20日均量", "status": vol_status, "desc": f"{vol_target:.2f} / {vol_ratio:.2f}"})

    rsi_val = float(rsi[last_idx])
    rsi_status = "bull" if rsi_val >= 60 else "bear" if rsi_val <= 40 else "neutral"
    indicators.append({"name": "RSI 区间", "status": rsi_status, "desc": f"60.0 / {rsi_val:.1f}"})

    atr_ratio = float(atr[last_idx] / (atr_ma20[last_idx] + 1e-9))
    atr_status = "bull" if atr_ratio > 1.10 else "bear" if atr_ratio < 0.90 else "neutral"
    indicators.append({"name": "ATR 波动率", "status": atr_status, "desc": f"1.10 / {atr_ratio:.2f}"})

    obv_ratio = float(obv[last_idx] / (obv_ma20[last_idx] + 1e-9))
    obv_status = "bull" if obv_ratio > 1.05 else "bear" if obv_ratio < 0.95 else "neutral"
    indicators.append({"name": "OBV 资金趋势", "status": obv_status, "desc": f"1.05 / {obv_ratio:.2f}"})

    return {
        "symbol": yahoo_symbol,
        "display_name": display_name,
        "price": price,
        "change": change,
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

# ============ 缓存 ============
@st.cache_data(show_spinner=False)
def get_stock_metrics_cached(symbol: str, cfg_key: str, version: int = 15):
    return compute_stock_metrics(symbol, cfg_key=cfg_key)

# ============ Streamlit 交互层 ============
def add_symbol_from_input():
    raw_val = st.session_state.get("new_symbol_input", "")
    if not raw_val.strip():
        return
    try:
        sym = resolve_user_input_symbol(raw_val)
    except ValueError as e:
        st.warning(str(e))
        return

    if sym in st.session_state.watchlist:
        st.session_state.watchlist.remove(sym)
    st.session_state.watchlist.insert(0, sym)
    st.session_state.new_symbol_input = ""

default_watchlist = ["QQQ", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA", "TSLA"]
if "watchlist" not in st.session_state:
    st.session_state.watchlist = default_watchlist.copy()

MODE_DEFAULT = "1年"
if "mode_label" not in st.session_state or st.session_state.get("mode_label") not in BACKTEST_CONFIG:
    st.session_state["mode_label"] = MODE_DEFAULT

top_c1, top_c2, top_c3, top_c4 = st.columns([2.4, 1.1, 1.1, 1.4])

with top_c1:
    st.text_input(
        "股票代码",
        value="",
        max_chars=10,
        placeholder="输入股票代码（例：TSLA / 600519 ）",
        label_visibility="collapsed",
        key="new_symbol_input",
        on_change=add_symbol_from_input,
    )
with top_c2:
    st.button("查询")
with top_c3:
    st.selectbox(
        "排序",
        ["默认顺序", "涨跌幅", "7日盈利概率", "30日盈利概率"],
        index=0,
        label_visibility="collapsed",
        key="sort_by",
    )
with top_c4:
    st.selectbox(
        "回测周期",
        BACKTEST_OPTIONS,
        index=BACKTEST_OPTIONS.index(MODE_DEFAULT),
        label_visibility="collapsed",
        key="mode_label",
    )

if st.button("查询"):  # 兼容按钮点击
    add_symbol_from_input()

rows = []
for sym in st.session_state.watchlist:
    try:
        with st.spinner(f"载入 {sym} ..."):
            metrics = get_stock_metrics_cached(sym, cfg_key=st.session_state.mode_label)
        rows.append(metrics)
    except Exception as e:
        st.warning(f"{sym} 加载失败：{e}")
        continue

sort_by = st.session_state.get("sort_by", "默认顺序")
if sort_by == "涨跌幅":
    rows.sort(key=lambda x: x["change"], reverse=True)
elif sort_by == "7日盈利概率":
    rows.sort(key=lambda x: x["prob7"], reverse=True)
elif sort_by == "30日盈利概率":
    rows.sort(key=lambda x: x["prob30"], reverse=True)

# ============ 卡片展示 ============
if not rows:
    st.info("暂无自选股票，请先在上方输入代码添加。")
else:
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
                    line = f"{ind['name']} ({ind['desc']})" if ind["desc"] else ind["name"]
                    indicators_html += (
                        f"<div class='indicator-item'><span>{line}</span>"
                        f"<span class='dot dot-{ind['status']}'></span></div>"
                    )

                adv7_label, adv7_intensity, adv7_kind = decide_advice(row["prob7"], pf7)
                adv30_label, adv30_intensity, adv30_kind = decide_advice(row["prob30"], pf30)

                def build_advice_html(label, intensity, kind):
                    if kind == "buy":
                        dot_class = "dot-score dot-score-buy"
                        text_class = "advice-text advice-buy"
                    elif kind == "sell":
                        dot_class = "dot-score dot-score-sell"
                        text_class = "advice-text advice-sell"
                    else:
                        dot_class = "dot-score dot-score-hold"
                        text_class = "advice-text advice-hold"
                    dots = (
                        f"<span class='{dot_class}'></span>" * intensity +
                        "<span class='dot-score dot-score-off'></span>" * (5 - intensity)
                    )
                    return text_class, label, dots

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
                    <div style="display:flex; gap:6px; align-items:center;">
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
                    <span class="score-label