import streamlit as st
import requests
import numpy as np
import pandas as pd
import time
from datetime import datetime

# ==================== 页面设置 ====================
st.set_page_config(page_title="币圈信号面板 (Binance API)", layout="wide")

st.markdown(
    """
    <style>
    /* 原版完整 CSS，保持不变 */
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
    .card:hover { transform:translateY(-3px); box-shadow:0 26px 48px rgba(0,0,0,0.6); }

    .card-section { display:flex; justify-content:space-between; align-items:flex-end; gap:10px; }
    .section-divider { border-bottom:1px solid #1f2030; margin:10px 0; }

    .symbol-line { display:flex; gap:10px; align-items:center; font-size:19px; margin-bottom:2px; }
    .symbol-name { font-weight:800; }
    .symbol-ticker { font-size:12px; color:#9ca3af; padding:2px 6px; border:1px solid #262736; border-radius:10px; background:#0d0e13; }
    .symbol-price { font-size:19px; }
    .change-up { color:#4ade80; font-size:14px; }
    .change-down { color:#fb7185; font-size:14px; }

    .indicator-grid { display:flex; flex-direction:column; gap:8px; margin-top:4px; }
    .indicator-item { display:flex; align-items:center; justify-content:space-between; width:100%; background:#191b27; border:1px solid #202233; border-radius:10px; padding:8px 10px; font-size:12px; color:#d4d4d8; }
    .dot { width:6px;height:6px;border-radius:2px;display:inline-block;margin-left:6px; }
    .dot-bull { background:#4ade80; box-shadow:0 0 0 1px rgba(74,222,128,0.25); }
    .dot-neutral { background:#facc15; box-shadow:0 0 0 1px rgba(250,204,21,0.25); }
    .dot-bear { background:#fb7185; box-shadow:0 0 0 0 1px rgba(251,113,133,0.25); }

    .label { color:#9ca3af; }
    .prob-good { color:#4ade80; font-weight:600; }
    .prob-mid { color:#facc15; font-weight:600; }
    .prob-bad { color:#fb7185; font-weight:600; }

    .score { font-size:12px; color:#9ca3af; margin-top:8px; display:flex; align-items:center; gap:8px; }
    .score-label { font-size:13px; font-weight:700; color:#e5e7eb; min-width:70px; }
    .dot-score { width:9px; height:9px; border-radius:50%; display:inline-block; margin-right:2px; }
    .dot-score-buy { background:#4ade80; }
    .dot-score-hold { background:#facc15; }
    .dot-score-sell { background:#fb7185; }
    .dot-score-off { background:#4b5563; }
    .advice-text { font-size:13px; font-weight:600; }
    .advice-buy { color:#4ade80; }
    .advice-hold { color:#facc15; }
    .advice-sell { color:#fb7185; }
    .profit-row { font-size:12px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("币圈回测信号面板 (Binance API)")

# ==================== Binance API 配置 ====================
BINANCE_BASE = "https://api.binance.com"

# 中文名称映射
CRYPTO_NAMES = {
    "BTCUSDT": "比特币", "ETHUSDT": "以太坊", "SOLUSDT": "Solana", "BNBUSDT": "币安币",
    "XRPUSDT": "瑞波币", "DOGEUSDT": "狗狗币", "ADAUSDT": "艾达币", "AVAXUSDT": "雪崩",
    "TRXUSDT": "波场", "LINKUSDT": "Chainlink", "DOTUSDT": "波卡", "SUIUSDT": "Sui",
    "TONUSDT": "TON", "HBARUSDT": "Hedera", "PEPEUSDT": "Pepe", "WIFUSDT": "dogwifhat",
}

# ==================== 工具函数 ====================
def format_binance_symbol(symbol: str) -> str:
    sym = symbol.strip().upper().replace("/", "").replace("-", "").replace(" ", "")
    if sym.endswith("USDT"):
        return sym
    # 自动补 USDT
    return sym + "USDT"

@st.cache_data(ttl=30, show_spinner=False)  # 30秒更新一次价格
def get_binance_price(symbol: str):
    binance_sym = format_binance_symbol(symbol)
    try:
        ticker = requests.get(f"{BINANCE_BASE}/api/v3/ticker/24hr", params={"symbol": binance_sym}, timeout=10).json()
        price = float(ticker["lastPrice"])
        change = float(ticker["priceChangePercent"])
        return price, change
    except Exception:
        return None, None

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_binance_klines(symbol: str, interval: str = "1d", limit: int = 1000):
    binance_sym = format_binance_symbol(symbol)
    params = {"symbol": binance_sym, "interval": interval, "limit": limit}
    try:
        data = requests.get(f"{BINANCE_BASE}/api/v3/klines", params=params, timeout=15).json()
        df = pd.DataFrame(data, columns=["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["volume"] = df["volume"].astype(float)
        return df[["close", "high", "low", "volume"]].values[-500:]  # 取最近500条
    except Exception as e:
        raise ValueError(f"Binance K线获取失败: {e}")

# ==================== 指标函数（同前） ====================
# ema_np, macd_hist_np, rsi_np, atr_np, rolling_mean_np, obv_np, backtest_with_stats, prob_class, decide_advice
# （与之前完全相同，复制粘贴即可）

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
    gain_ema = np.empty_like(gain); loss_ema = np.empty_like(loss)
    gain_ema[0] = gain[0]; loss_ema[0] = loss[0]
    for i in range(1, len(gain)):
        gain_ema[i] = alpha * gain[i] + (1 - alpha) * gain_ema[i-1]
        loss_ema[i] = alpha * loss[i] + (1 - alpha) * loss_ema[i-1]
    rs = gain_ema / (loss_ema + 1e-9)
    return 100 - (100 / (1 + rs))

def atr_np(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    prev_close = np.roll(close, 1); prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = np.empty_like(tr); atr[0] = tr[0]
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
    avg_win = rets[rets > 0].mean() * 100 if (rets > 0).any() else 0
    avg_loss = rets[rets <= 0].mean() * 100 if (rets <= 0).any() else 0
    return win_rate, pf, avg_win, avg_loss

def prob_class(p): return "prob-good" if p >= 0.65 else "prob-mid" if p >= 0.45 else "prob-bad"

def decide_advice(prob: float, pf: float):
    if prob >= 0.60 and pf >= 1.2:
        kind = "buy"; intensity = 3 + (prob > 0.65) + (pf > 1.6)
    elif prob <= 0.40 and pf <= 0.8:
        kind = "sell"; intensity = 3 + (prob < 0.35) + (pf < 0.6)
    else:
        kind = "hold"; intensity = 3
    intensity = max(1, min(5, intensity))
    label = "建议买入" if kind == "buy" else "建议卖出" if kind == "sell" else "观望"
    return label, intensity, kind

# ==================== 计算函数 ====================
@st.cache_data(show_spinner=False)
def compute_binance_metrics(symbol: str, cfg_key: str = "1年"):
    binance_sym = format_binance_symbol(symbol)
    display_name = CRYPTO_NAMES.get(binance_sym, binance_sym.replace("USDT", ""))

    price, change = get_binance_price(binance_sym)
    data = fetch_binance_klines(binance_sym, "1d", 500)
    close, high, low, volume = data[:,0], data[:,1], data[:,2], data[:,3]

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

    prob7, pf7, avg_win7, avg_loss7 = backtest_with_stats(close[:-1], score_arr[:-1], 7)
    prob30, pf30, avg_win30, avg_loss30 = backtest_with_stats(close[:-1], score_arr[:-1], 30)

    indicators = [
        {"name": "MACD 多头/空头", "status": "bull" if macd_hist[-1] > 0 else "bear", "desc": ""},
        {"name": "成交量相对20日均量", "status": "bull" if volume[-1] > vol_ma20[-1]*1.1 else "bear" if volume[-1] < vol_ma20[-1]*0.9 else "neutral", "desc": f"1.10 / {volume[-1]/vol_ma20[-1]:.2f}"},
        {"name": "RSI 区间", "status": "bull" if rsi[-1] >= 60 else "bear" if rsi[-1] <= 40 else "neutral", "desc": f"60.0 / {rsi[-1]:.1f}"},
        {"name": "ATR 波动率", "status": "bull" if atr[-1] > atr_ma20[-1]*1.1 else "bear" if atr[-1] < atr_ma20[-1]*0.9 else "neutral", "desc": f"1.10 / {atr[-1]/atr_ma20[-1]:.2f}"},
        {"name": "OBV 资金趋势", "status": "bull" if obv[-1] > obv_ma20[-1]*1.05 else "bear" if obv[-1] < obv_ma20[-1]*0.95 else "neutral", "desc": f"1.05 / {obv[-1]/obv_ma20[-1]:.2f}"},
    ]

    return {
        "symbol": binance_sym.replace("USDT", ""),
        "display_name": display_name,
        "price": price or close[-1],
        "change": change or 0.0,
        "prob7": prob7,
        "prob30": prob30,
        "pf7": pf7,
        "pf30": pf30,
        "avg_win7": avg_win7,
        "avg_loss7": avg_loss7,
        "avg_win30": avg_win30,
        "avg_loss30": avg_loss30,
        "indicators": indicators,
    }

# ==================== 界面 ====================
if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["BTC", "ETH", "SOL", "BNB", "SUI", "DOGE", "TON", "XRP"]

col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    new = st.text_input("添加币种", placeholder="BTC / ETH / SUIUSDT / pepe", key="new")
with col2:
    if st.button("添加"):
        if st.session_state.new.strip():
            sym = st.session_state.new.strip().upper()
            if sym not in st.session_state.watchlist:
                st.session_state.watchlist.insert(0, sym)
            st.rerun()
with col3:
    if st.button("清空缓存"):
        st.cache_data.clear()
        st.success("缓存已清空")
        st.rerun()

rows = []
for sym in st.session_state.watchlist:
    try:
        with st.spinner(f"加载 {sym}..."):
            metrics = compute_binance_metrics(sym)
        rows.append(metrics)
        time.sleep(0.6)
    except Exception as e:
        st.warning(f"{sym} 加载失败: {e}")

# ==================== 卡片展示（同前） ====================
if not rows:
    st.info("暂无数据，请添加币种")
else:
    for i in range(0, len(rows), 4):
        cols = st.columns(4)
        for j, row in enumerate(rows[i:i+4]):
            with cols[j]:
                # 渲染卡片（与之前完全相同的 html 代码）
                # 复制你喜欢的卡片 html 部分即可
                change_class = "change-up" if row["change"] >= 0 else "change-down"
                change_str = f"{row['change']:+.2f}%"
                indicators_html = "".join(
                    f"<div class='indicator-item'><span>{ind['name']} {f'({ind['desc']})' if ind['desc'] else ''}</span><span class='dot dot-{ind['status']}'></span></div>"
                    for ind in row["indicators"]
                )
                adv7_label, adv7_intensity, adv7_kind = decide_advice(row["prob7"], row["pf7"])
                adv30_label, adv30_intensity, adv30_kind = decide_advice(row["prob30"], row["pf30"])
                dots7 = f"<span class='dot-score dot-score-{'buy' if adv7_kind=='buy' else 'sell' if adv7_kind=='sell' else 'hold'}'></span>" * adv7_intensity + "<span class='dot-score dot-score-off'></span>" * (5 - adv7_intensity)
                dots30 = f"<span class='dot-score dot-score-{'buy' if adv30_kind=='buy' else 'sell' if adv30_kind=='sell' else 'hold'}'></span>" * adv30_intensity + "<span class='dot-score dot-score-off'></span>" * (5 - adv30_intensity)

                html = f'''
                <div class="card">
                  <div class="card-section">
                    <div class="symbol-line">
                      <span class="symbol-name">{row["display_name"]}</span>
                      <span class="symbol-ticker">{row["symbol"]}</span>
                    </div>
                    <div style="display:flex;gap:6px;align-items:center;">
                      <span class="symbol-price">${row["price"]:.4f}</span>
                      <span class="{change_class}">{change_str}</span>
                    </div>
                  </div>
                  <div class="section-divider"></div>
                  <div class="indicator-grid">{indicators_html}</div>
                  <div class="section-divider"></div>
                  <div class="profit-row" style="display:flex;justify-content:space-between;margin-bottom:4px;">
                    <div><span class="label">7日盈利概率</span> <span class="{prob_class(row["prob7"])}">{row["prob7"]*100:.1f}%</span></div>
                    <div class="label">均盈 {row["avg_win7"]:+.1f}% / 均亏 {row["avg_loss7"]:+.1f}% / PF {row["pf7"]:.2f}</div>
                  </div>
                  <div class="profit-row" style="display:flex;justify-content:space-between;">
                    <div><span class="label">30日盈利概率</span> <span class="{prob_class(row["prob30"])}">{row["prob30"]*100:.1f}%</span></div>
                    <div class="label">均盈 {row["avg_win30"]:+.1f}% / 均亏 {row["avg_loss30"]:+.1f}% / PF {row["pf30"]:.2f}</div>
                  </div>
                  <div class="section-divider"></div>
                  <div class="score"><span class="score-label">7日信号</span> <span class="advice-text advice-{adv7_kind}">{adv7_label}</span> {dots7}</div>
                  <div class="score"><span class="score-label">30日信号</span> <span class="advice-text advice-{adv30_kind}">{adv30_label}</span> {dots30}</div>
                </div>
                '''
                st.markdown(html, unsafe_allow_html=True)

st.caption("数据来源 Binance 官方 API，价格实时更新，24小时不间断。回测基于历史日线，仅供研究参考，不构成投资建议。")
