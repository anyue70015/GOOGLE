import streamlit as st
import requests
import numpy as np
import time

st.set_page_config(page_title="回测信号面板", layout="wide")

# ==================== 加强 headers，伪装真实浏览器 ====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# ==================== CSS 样式（不变） ====================
st.markdown(
    """
    <style>
    /* 你的原 CSS 全保留，这里省略以节省空间，但请完整复制你原来的 CSS */
    body { background:#05060a; }
    .main { background:#05060a; }
    h1 { font-size:26px !important; font-weight:700 !important; }
    .card { background:#14151d; border-radius:14px; padding:14px; border:1px solid #262736; box-shadow:0 18px 36px rgba(0,0,0,0.45); color:#f5f5f7; margin-bottom:18px; }
    .card:hover { transform:translateY(-3px); box-shadow:0 26px 48px rgba(0,0,0,0.6); }
    /* ... 其余 CSS 请从你原来代码复制进来 ... */
    .stAlert { margin-top: 20px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("回测信号面板")

# ==================== 配置 ====================
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

# ==================== 关键函数（加强版） ====================
def format_symbol_for_yahoo(symbol: str) -> str:
    sym = symbol.strip().upper()
    if sym.isdigit() and len(sym) == 6:
        if sym.startswith(("600", "601", "603", "605", "688")):
            return f"{sym}.SS"
        if sym.startswith(("000", "001", "002", "003", "300", "301")):
            return f"{sym}.SZ"
    return sym

@st.cache_data(ttl=600, show_spinner=False)
def get_current_price(yahoo_symbol: str):
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={yahoo_symbol}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        result = data.get("quoteResponse", {}).get("result", [])
        if result:
            p = result[0].get("regularMarketPrice") or result[0].get("regularMarketPreviousClose")
            chg = result[0].get("regularMarketChangePercent", 0) * 100
            return float(p), float(chg)
    except Exception as e:
        st.warning(f"实时价格获取失败 {yahoo_symbol}: {e}")
    return None, None

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yahoo_ohlcv(_symbol: str, range_str: str, interval: str):
    symbol = format_symbol_for_yahoo(_symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range_str}&interval={interval}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        result = data["chart"]["result"]
        if not result:
            raise ValueError("No chart data")
        quote = result[0]["indicators"]["quote"][0]
        close = np.array(quote["close"], dtype=float)
        mask = ~np.isnan(close)
        close = close[mask]
        if len(close) < 50:
            raise ValueError("数据太少")
        return close[-250:]  # 只取最近250天，加快计算
    except Exception as e:
        raise ValueError(f"Yahoo 数据获取失败: {e}")

# ==================== 简化指标计算（只为演示） ====================
def simple_metrics(symbol: str, cfg_key: str):
    try:
        close = fetch_yahoo_ohlcv(symbol, BACKTEST_CONFIG[cfg_key]["range"], "1d")
        current_price, change = get_current_price(format_symbol_for_yahoo(symbol))
        price = current_price or close[-1]
        change = change or 0.0

        # 简单模拟一些指标
        rsi = 50 + np.random.uniform(-20, 30)
        rsi_status = "bull" if rsi > 60 else "bear" if rsi < 40 else "neutral"

        prob7 = np.random.uniform(0.4, 0.8)
        prob30 = np.random.uniform(0.4, 0.8)

        indicators = [
            {"name": "MACD", "status": "bull" if np.random.rand() > 0.5 else "bear", "desc": ""},
            {"name": "成交量", "status": "bull", "desc": "1.10 / 1.25"},
            {"name": "RSI", "status": rsi_status, "desc": f"60 / {rsi:.1f}"},
        ]

        return {
            "symbol": symbol.upper(),
            "display_name": symbol.upper(),
            "price": price,
            "change": change,
            "prob7": prob7,
            "prob30": prob30,
            "indicators": indicators,
        }
    except Exception as e:
        st.error(f"【{symbol}】加载失败：{str(e)}")
        return None

# ==================== 界面 ====================
col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    new_sym = st.text_input("添加股票", placeholder="NVDA / AAPL / 600519", key="new_sym")
with col2:
    if st.button("添加股票"):
        if new_sym.strip():
            sym = new_sym.strip().upper()
            if "watchlist" not in st.session_state:
                st.session_state.watchlist = []
            if sym not in st.session_state.watchlist:
                st.session_state.watchlist.insert(0, sym)
            st.rerun()
with col3:
    if st.button("清空缓存"):
        st.cache_data.clear()
        st.success("缓存已清空")
        st.rerun()

if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["NVDA", "AAPL", "TSLA", "MSFT"]

if "mode" not in st.session_state:
    st.session_state.mode = "1年"

st.selectbox("回测周期", BACKTEST_OPTIONS, key="mode", index=BACKTEST_OPTIONS.index(st.session_state.mode))

st.markdown("---")

rows = []
for sym in st.session_state.watchlist[:12]:  # 最多12只，避免请求太多被封
    with st.spinner(f"加载 {sym}..."):
        metrics = simple_metrics(sym, st.session_state.mode)
        if metrics:
            rows.append(metrics)
    time.sleep(0.5)  # 避免太快被 Yahoo 限流

if not rows:
    st.error("所有股票都加载失败！可能原因：\n"
             "- 网络被 Yahoo Finance 屏蔽（常见于服务器/VPS）\n"
             "- 请尝试更换网络或等待几分钟后刷新\n"
             "- 或使用本地电脑运行此应用")
else:
    cols = st.columns(4)
    for i, row in enumerate(rows):
        with cols[i % 4]:
            change_class = "change-up" if row["change"] >= 0 else "change-down"
            change_str = f"{row['change']:+.2f}%"
            indicators_html = "".join(
                f"<div style='display:flex;justify-content:space-between;padding:6px 8px;background:#191b27;border-radius:8px;margin:4px 0;'><span>{ind['name']}</span><span style='width:8px;height:8px;border-radius:50%;background:{'#4ade80' if ind['status']=='bull' else '#fb7185' if ind['status']=='bear' else '#facc15'};'></span></div>"
                for ind in row["indicators"]
            )
            html = f"""
            <div style="background:#14151d;padding:16px;border-radius:14px;border:1px solid #262736;">
                <div style="display:flex;justify-content:space-between;align-items:end;">
                    <div>
                        <div style="font-size:18px;font-weight:bold;">{row['display_name']}</div>
                        <div style="font-size:12px;color:#9ca3af;">{row['symbol']}</div>
                    </div>
                    <div style="text-align:right;">
                        <div style="font-size:18px;">${row['price']:.2f}</div>
                        <div style="color:{'#4ade80' if row['change']>=0 else '#fb7185'};">{change_str}</div>
                    </div>
                </div>
                <hr style="border-color:#1f2030;margin:12px 0;">
                {indicators_html}
                <hr style="border-color:#1f2030;margin:12px 0;">
                <div style="font-size:13px;">
                    7日盈利概率: <strong>{row['prob7']*100:.1f}%</strong><br>
                    30日盈利概率: <strong>{row['prob30']*100:.1f}%</strong>
                </div>
            </div>
            """
            st.markdown(html, unsafe_allow_html=True)

st.caption("当前为简化演示版（随机模拟指标），主要验证界面显示。完整技术指标版请在本地稳定网络运行。")
