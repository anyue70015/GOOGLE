import streamlit as st
import pandas as pd
import requests
import time
import urllib3
import random

# 基础配置
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="全球量化指挥部 - 云端生存版", layout="wide")

# --- 云端生存级域名列表 ---
# 如果第一个不通，系统会自动尝试后面的
BINANCE_ENDPOINTS = [
    "https://fapi.binance.com",
    "https://fapi1.binance.com",
    "https://fapi2.binance.com",
    "https://fapi3.binance.com",
    "https://fapi.binance.us"
]

SYMBOLS = ["BTC", "RENDER", "SUI", "TAO", "ETH", "SOL", "XRP", "UNI", "BCH", "HYPE", "DOGE", "AAVE", "ZEC", "CHZ"]

# 模拟真实的浏览器请求头，防止被 403
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache"
}

# ------------------------------------------------
# 2. 增强型抓取引擎
# ------------------------------------------------
def safe_request(path, params=None):
    """自动轮询不同的币安节点，绕过 IP 封锁"""
    for base_url in BINANCE_ENDPOINTS:
        try:
            url = f"{base_url}{path}"
            r = requests.get(url, params=params, headers=HEADERS, timeout=2, verify=False)
            if r.status_code == 200:
                return r.json()
        except:
            continue
    return None

def fetch_data_row(s):
    try:
        # 1. 获取基础行情数据
        ticker_data = safe_request("/fapi/v1/ticker/24hr", {"symbol": f"{s}USDT"})
        if not ticker_data:
            # HYPE 特殊逻辑：尝试 OKX
            if s == "HYPE":
                r_okx = requests.get("https://www.okx.com/api/v5/market/ticker?instId=HYPE-USDT", timeout=2)
                d = r_okx.json()['data'][0]
                price, c24, vol = float(d['last']), float(d['last']) * float(d['vol24h']), float(d['vol24h'])
            else: return None
        else:
            price = float(ticker_data['lastPrice'])
            c24 = float(ticker_data['priceChangePercent'])
            vol = float(ticker_data['quoteVolume'])

        # 2. 高精度回溯 (1m/5m/1h)
        # 获取 120 根 1m 线，一次性计算三个维度
        k_data = safe_request("/fapi/v1/klines", {"symbol": f"{s}USDT", "interval": "1m", "limit": 120})
        
        if k_data:
            # 计算 1m: 最新收盘 - 当前根开盘
            m1 = (float(k_data[-1][4]) - float(k_data[-1][1])) / float(k_data[-1][1]) * 100
            # 计算 5m: 最新收盘 - 5根前的开盘
            m5 = (float(k_data[-1][4]) - float(k_data[-5][1])) / float(k_data[-5][1]) * 100
            # 计算 1h: 最新收盘 - 60根前的开盘
            h1 = (float(k_data[-1][4]) - float(k_data[-60][1])) / float(k_data[-60][1]) * 100
        else:
            m1 = m5 = h1 = 0.0

        return {
            "币种": s,
            "最新价": round(price, 4) if price < 10 else round(price, 2),
            "1m%": m1, "5m%": m5, "1h%": h1, "24h%": c24,
            "净流入(万)": round((c24 * vol / 10000000), 1),
            "战术诊断": "🎯 突击" if m1 > 0.1 else "⚖️ 盘整",
            "来源": "Binance-Multi"
        }
    except: return None

# ------------------------------------------------
# 3. 页面渲染
# ------------------------------------------------
st.title("🛰️ 全球量化指挥部 - 云端最终版")

# 侧边栏调试信息
st.sidebar.header("系统状态")
st.sidebar.write("✅ 域名轮询开启")
st.sidebar.write("✅ 浏览器头伪装开启")

placeholder = st.empty()

while True:
    rows = []
    # 随机化币种顺序，避免被币安检测到固定步频抓取
    random.shuffle(SYMBOLS)
    
    for s in SYMBOLS:
        res = fetch_data_row(s)
        if res: rows.append(res)
    
    if rows:
        df = pd.DataFrame(rows).sort_values(by="1m%", ascending=False)
        with placeholder.container():
            st.dataframe(
                df.style.format({"1m%": "{:+,.2f}%", "5m%": "{:+,.2f}%", "24h%": "{:+,.2f}%"}),
                use_container_width=True, hide_index=True
            )
            st.caption(f"📊 实时监测中 | 刷新时间: {time.strftime('%H:%M:%S')}")
    else:
        st.warning("⚠️ 节点正在被风控，系统正在自动更换接入点...")

    time.sleep(4)
