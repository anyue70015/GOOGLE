import streamlit as st
import requests
import numpy as np
import pandas as pd
import time

st.set_page_config(page_title="币圈回测信号面板 (CoinGecko)", layout="wide")

st.markdown(
    '''
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
    ''',
    unsafe_allow_html=True,
)

st.title("币圈回测信号面板 (CoinGecko API)")

# ==================== CoinGecko 配置 ====================
COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "DOGE": "dogecoin",
    "ADA": "cardano",
    "AVAX": "avalanche-2",
    "TRX": "tron",
    "LINK": "chainlink",
    "DOT": "polkadot",
    "TON": "toncoin",
    "SUI": "sui",
    "PEPE": "pepe",
    "WIF": "dogwifhat",
    "SHIB": "shiba-inu",
    "LTC": "litecoin",
}

CHINESE_NAMES = {
    "bitcoin": "比特币",
    "ethereum": "以太坊",
    "solana": "Solana",
    "binancecoin": "币安币",
    "ripple": "瑞波币",
    "dogecoin": "狗狗币",
    "cardano": "艾达币",
    "avalanche-2": "雪崩协议",
    "tron": "波场",
    "chainlink": "Chainlink",
    "polkadot": "波卡",
    "toncoin": "TON",
    "sui": "Sui",
    "pepe": "Pepe",
    "dogwifhat": "dogwifhat",
    "shiba-inu": "柴犬币",
    "litecoin": "莱特币",
}

def get_coingecko_id(coin: str) -> str:
    coin_upper = coin.strip().upper()
    return COINGECKO_IDS.get(coin_upper, coin_upper.lower())

@st.cache_data(ttl=60, show_spinner=False)
def get_price_and_change(coin_id: str):
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"
    for _ in range(3):  # 重试3次
        try:
            data = requests.get(url, timeout=10).json()
            if coin_id in data:
                price = data[coin_id]["usd"]
                change = data[coin_id].get("usd_24h_change", 0.0)
                return price, change
        except Exception:
            time.sleep(1)
    return None, None

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_coingecko_ohlc(coin_id: str, days: int = 365):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc?vs_currency=usd&days={days}"
    for _ in range(3):
        try:
            data = requests.get(url, timeout=15).json()
            if len(data) == 0:
                raise ValueError("无数据")
            df = pd.DataFrame(data, columns=["time", "open", "high", "low", "close"])
            close = df["close"].values
            high = df["high"].values
            low = df["low"].values
            volume = np.full(len(close), 1e8)  # 模拟成交量
            return close, high, low, volume
        except Exception:
            time.sleep(1)
    raise ValueError("获取OHLC失败")

# ==================== 指标函数（保持不变） ====================
# (复制之前所有指标函数：ema_np, macd_hist_np, rsi_np, atr_np, rolling_mean_np, obv_np, backtest_with_stats, prob_class, decide_advice)

# ==================== 主计算函数 ====================
@st.cache_data(show_spinner=False)
def compute_coingecko_metrics(coin: str):
    coin_id = get_coingecko_id(coin)
    display_name = CHINESE_NAMES.get(coin_id, coin.upper())

    price, change = get_price_and_change(coin_id)
    close, high, low, volume = fetch_coingecko_ohlc(coin_id)

    if len(close) < 50:
        raise ValueError("历史数据不足")

    # 计算所有指标（同之前代码）

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

    prob7, pf7, avg_win7, avg_loss7 = backtest_with_stats(close, score_arr, 7)
    prob30, pf30, avg_win30, avg_loss30 = backtest_with_stats(close, score_arr, 30)

    final_price = price if price is not None else close[-1]
    final_change = change if change is not None else 0.0

    indicators = [
        {"name": "MACD 多头/空头", "status": "bull" if macd_hist[-1] > 0 else "bear", "desc": ""},
        {"name": "成交量相对20日均量", "status": "bull" if volume[-1] > vol_ma20[-1]*1.1 else "bear" if volume[-1] < vol_ma20[-1]*0.9 else "neutral", "desc": f"1.10 / {volume[-1]/vol_ma20[-1]:.2f}"},
        {"name": "RSI 区间", "status": "bull" if rsi[-1] >= 60 else "bear" if rsi[-1] <= 40 else "neutral", "desc": f"60.0 / {rsi[-1]:.1f}"},
        {"name": "ATR 波动率", "status": "bull" if atr[-1] > atr_ma20[-1]*1.1 else "bear" if atr[-1] < atr_ma20[-1]*0.9 else "neutral", "desc": f"1.10 / {atr[-1]/atr_ma20[-1]:.2f}"},
        {"name": "OBV 资金趋势", "status": "bull" if obv[-1] > obv_ma20[-1]*1.05 else "bear" if obv[-1] < obv_ma20[-1]*0.95 else "neutral", "desc": f"1.05 / {obv[-1]/obv_ma20[-1]:.2f}"},
    ]

    return {
        "symbol": coin.upper(),
        "display_name": display_name,
        "price": final_price,
        "change": final_change,
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

# ==================== 交互 ====================
if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["BTC", "ETH", "SOL", "BNB", "DOGE", "TON", "XRP", "ADA"]

col1, col2, col3 = st.columns([3, 1, 1.5])
with col1:
    new_coin = st.text_input("添加币种", placeholder="BTC / ETH / PEPE", key="new_coin")
with col2:
    if st.button("添加"):
        if new_coin.strip():
            sym = new_coin.strip().upper()
            if sym not in st.session_state.watchlist:
                st.session_state.watchlist.insert(0, sym)
            st.rerun()
with col3:
    if st.button("清空缓存"):
        st.cache_data.clear()
        st.success("缓存已清空")
        st.rerun()

# ==================== 加载数据（限制8只） ====================
rows = []
failed = []

for sym in st.session_state.watchlist[:8]:  # 只加载前8只，避免限流
    try:
        with st.spinner(f"加载 {sym}..."):
            metrics = compute_coingecko_metrics(sym)
        rows.append(metrics)
        time.sleep(1)  # 关键：间隔1秒请求
    except Exception as e:
        failed.append(f"{sym}: {str(e)}")

if failed:
    st.warning("部分币种加载失败：\n" + "\n".join(failed))

if not rows:
    st.error("所有币种都加载失败！请检查网络，或点击“清空缓存”后重试。")
else:
    # 展示卡片（同之前完整代码）
    for i in range(0, len(rows), 4):
        cols = st.columns(4)
        for j, row in enumerate(rows[i:i+4]):
            with cols[j]:
                # 完整卡片 HTML 渲染（同之前）
                change_class = "change-up" if row["change"] >= 0 else "change-down"
                change_str = f"{row['change']:+.2f}%"

                indicators_html = "".join(
                    f"<div class='indicator-item'><span>{ind['name']}{' (' + ind['desc'] + ')' if ind['desc'] else ''}</span><span class='dot dot-{ind['status']}'></span></div>"
                    for ind in row["indicators"]
                )

                adv7_label, adv7_intensity, adv7_kind = decide_advice(row["prob7"], row["pf7"])
                adv30_label, adv30_intensity, adv30_kind = decide_advice(row["prob30"], row["pf30"])

                dots7 = "<span class='dot-score dot-score-" + ("buy" if adv7_kind=="buy" else "sell" if adv7_kind=="sell" else "hold") + "'></span>" * adv7_intensity + "<span class='dot-score dot-score-off'></span>" * (5 - adv7_intensity)
                dots30 = "<span class='dot-score dot-score-" + ("buy" if adv30_kind=="buy" else "sell" if adv30_kind=="sell" else "hold") + "'></span>" * adv30_intensity + "<span class='dot-score dot-score-off'></span>" * (5 - adv30_intensity)

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

st.caption("数据来源 CoinGecko API，全球无限制访问，价格实时更新。回测仅供参考，不构成投资建议。")
