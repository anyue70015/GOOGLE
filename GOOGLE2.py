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

# ============ 回测配置 ============
BACKTEST_OPTIONS = ["3个月", "6个月", "1年", "2年", "3年", "5年", "10年"]
BACKTEST_CONFIG = {
    "3个月": {"range": "3mo", "interval": "1d", "steps_per_day": 1},
    "6个月": {"range": "6mo", "interval": "1d", "steps_per_day": 1},
    "1年":   {"range": "1y",  "interval": "1d", "steps_per_day": 1},
    "2年":   {"range": "2y",  "interval": "1d", "steps_per_day": 1},
    "3年":   {"range": "3y",  "interval": "1d", "steps_per_day": 1},
    "5年":   {"range": "5y",  "interval": "1d", "steps_per_day": 1},
    "10年":  {"range": "10y", "interval": "1d", "steps_per_day": 1},
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
            params={"input": query, "type": "14", "token": "BD5FB5E653E986E07EED55F0F9F3CD9D", "format": "json", "count": 10},
            headers={"Referer": "https://www.eastmoney.com"},
            timeout=10,
        )
        data = resp.json()
        records = data.get("QuotationCodeTable", {}).get("Data", []) or []
        for rec in records:
            code = rec.get("Code")
            if code and len(code) == 6:
                return code, rec.get("Name"), ""
    except Exception:
        pass
    return None

def search_yahoo_symbol_by_name(query: str):
    try:
        resp = requests.get(
            "https://query1.finance.yahoo.com/v1/finance/search",
            params={"q": query, "quotes_count": 15, "news_count": 0, "lang": "zh-Hans", "region": "HK"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        data = resp.json()
        for item in data.get("quotes", []):
            symbol = item.get("symbol", "")
            if symbol.endswith((".SS", ".SZ")):
                return symbol.replace(".SS", "").replace(".SZ", ""), item.get("shortname") or item.get("longname"), ""
    except Exception:
        pass
    return None

def resolve_user_input_symbol(user_input: str) -> str:
    raw = user_input.strip()
    if not raw:
        raise ValueError
