import streamlit as st
import requests
import numpy as np
import pandas as pd
import time

st.set_page_config(page_title="币圈回测信号面板 (CoinGecko)", layout="wide")

st.markdown(
    '''
    <style>
    /* 完整原CSS，使用三单引号避免错误 */
    body { background:#05060a; }
    .main { background:#05060a; padding-top:10px !important; }
    h1 { font-size:26px !important; font-weight:700 !important; margin-bottom:6px !important; }

    .card { background:#14151d; border-radius:14px; padding:14px 16px 12px; border:1px solid #262736; box-shadow:0 18px 36px rgba(0,0,0,0.45); color:#f5f5f7; font-size:13px; transition:0.15s; margin-bottom:18px; }
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
    .dot-bear { background:#fb7185; box-shadow:0 0 0 1px rgba(251,113,133,0.25); }

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
    ''',
    unsafe_allow_html=True,
)

st.title("币圈回测信号面板 (CoinGecko API)")

# CoinGecko ID 映射（常见币种）
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
    "WIF": "dogwifcoin",
}

CHINESE_NAMES = {
    "bitcoin": "比特币", "ethereum": "以太坊", "solana": "Solana", "binancecoin": "币安币",
    "ripple": "瑞波币", "dogecoin": "狗狗币", "cardano": "艾达币", "avalanche-2": "雪崩协议",
    "tron": "波场", "chainlink": "Chainlink", "polkadot": "波卡", "toncoin": "TON",
    "sui": "Sui", "pepe": "Pepe", "dogwifcoin": "dogwifhat",
}

def get_coingecko_id(coin: str) -> str:
    coin = coin.strip().lower()
    return COINGECKO_IDS.get(coin.upper(), coin)

@st.cache_data(ttl=60, show_spinner=False)
def get_price_and_change(coin_id: str):
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"
    try:
        data = requests.get(url, timeout=10).json()
        if coin_id in data:
            return data[coin_id]["usd"], data[coin_id]["usd_24h_change"]
    except Exception:
        pass
    return None, None

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_coingecko_ohlc(coin_id: str, days: int = 365):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc?vs_currency=usd&days={days}"
    try:
        data = requests.get(url, timeout=15).json()
        if len(data) == 0:
            raise ValueError("无OHLC数据")
        df = pd.DataFrame(data, columns=["time", "open", "high", "low", "close"])
        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        volume = np.ones(len(close))  # CoinGecko OHLC 无volume，设为1避免除零
        return close, high, low, volume
    except Exception as e:
        raise ValueError(f"获取OHLC失败: {str(e)}")

# 其余指标函数（ema_np, macd_hist_np 等）保持不变，复制之前代码即可

# ...（这里粘贴所有指标函数：ema_np, macd_hist_np, rsi_np, atr_np, rolling_mean_np, obv_np, backtest_with_stats, prob_class, decide_advice）

# 主计算函数（改用CoinGecko）
@st.cache_data(show_spinner=False)
def compute_coingecko_metrics(coin: str):
    coin_id = get_coingecko_id(coin)
    display_name = CHINESE_NAMES.get(coin_id, coin.upper())

    price, change = get_price_and_change(coin_id)
    close, high, low, volume = fetch_coingecko_ohlc(coin_id, days=365)

    if len(close) < 50:
        raise ValueError("历史数据不足")

    # 计算指标（同之前）
    # ...（复制所有指标计算代码）

    return {
        "symbol": coin.upper(),
        "display_name": display_name,
        "price": price or close[-1],
        "change": change or 0.0,
        # 其他字段同前
    }

# 交互和展示部分保持不变，只把 compute_binance_metrics 换成 compute_coingecko_metrics

st.caption("数据来源 CoinGecko API（全球无限制访问），价格实时更新。回测基于历史日线，仅供参考。")
