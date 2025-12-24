import streamlit as st
import requests
import numpy as np
import time

# ==================== 页面设置 ====================
st.set_page_config(page_title="币圈回测信号面板 (Yahoo Finance)", layout="wide")

# CSS 使用三单引号
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

st.title("币圈回测信号面板 (Yahoo Finance API)")

# ==================== 配置 ====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

YAHOO_CRYPTO = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "BNB": "BNB-USD",
    "XRP": "XRP-USD",
    "DOGE": "DOGE-USD",
    "ADA": "ADA-USD",
    "AVAX": "AVAX-USD",
    "TRX": "TRX-USD",
    "LINK": "LINK-USD",
    "DOT": "DOT-USD",
    "TON": "TON11419-USD",
    "SUI": "SUI-USD",
    "PEPE": "PEPE24478-USD",
    "WIF": "WIF-USD",
    "SHIB": "SHIB-USD",
}

CHINESE_NAMES = {
    "BTC-USD": "比特币",
    "ETH-USD": "以太坊",
    "SOL-USD": "Solana",
    "BNB-USD": "币安币",
    "XRP-USD": "
