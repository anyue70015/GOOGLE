import streamlit as st
import pandas as pd
import requests
import time
import urllib3
import os

# 1. 基础配置
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="全球量化指挥部 - 最终战略版", layout="wide")

# 【修正重点】定义统一代理变量名
MY_PROXY = {"http": "http://127.0.0.1:10811", "https": "http://127.0.0.1:10811"}
DIRECT = {"http": None, "https": None} 

BN_MIRROR = "https://www.bmwweb.academy"
BN_FAPI = "https://fapi.binance.com"

SYMBOLS = ["BTC", "RENDER", "SUI", "TAO", "ETH", "SOL", "XRP", "UNI", "BCH", "HYPE", "DOGE", "AAVE", "ZEC", "CHZ"]

# ------------------------------------------------
# 2. 诊断引擎
# ------------------------------------------------
def fetch_accurate_change(symbol, interval, lookback):
    """回溯 K 线精准计算涨幅"""
    # 修正：将 PROXY_7890 改为 MY_PROXY
    url = f"{BN_FAPI}/fapi/v1/klines?symbol={symbol}USDT&interval={interval}&limit={lookback + 1}"
    try:
        r = requests.get(url, timeout=2.0, verify=False, proxies=MY_PROXY)
        if r.status_code == 200:
            ks = r.json()
            if len(ks) > 0:
                start_price, current_price = float(ks[0][1]), float(ks[-1][4])
                return (current_price - start_price) / start_price * 100
    except Exception as e:
        pass # 生产环境可打印 st.error(e) 调试
    return 0.0

def fetch_data_row(s):
    try:
        if s == "HYPE":
            try:
                url = "https://www.okx.com/api/v5/market/ticker?instId=HYPE-USDT"
                r = requests.get(url, timeout=2.0, proxies=DIRECT)
                d = r.json()['data'][0]
                price = float(d['last'])
                vol = float(d['vol24h']) * price
                src = "OKX直连"
            except:
                url = f"{BN_MIRROR}/fapi/v1/ticker/24hr?symbol=HYPEUSDT"
                # 修正：将 PROXY_7890 改为 MY_PROXY
                d = requests.get(url, timeout=2.0, verify=False, proxies=MY_PROXY).json()
                price, vol, src = float(d['lastPrice']), float(d['quoteVolume']), "BN合约"
        else:
            url = f"{BN_MIRROR}/api/v3/ticker/24hr?symbol={s}USDT"
            # 修正：将 PROXY_7890 改为 MY_PROXY
            d = requests.get(url, timeout=2.0, verify=False, proxies=MY_PROXY).json()
            price, vol, src = float(d['lastPrice']), float(d['quoteVolume']), "BN现货"

        m1 = fetch_accurate_change(s, "1m", 1)
        m5 = fetch_accurate_change(s, "1m", 5)
        h1 = fetch_accurate_change(s, "1m", 60)
        c24 = fetch_accurate_change(s, "1h", 24)

        return {
            "币种": s,
            "最新价": round(price, 4) if price < 10 else round(price, 2),
            "1m%": m1, 
            "5m%": m5, 
            "1h%": h1, 
            "24h%": c24,
            "净流入(万)": round((c24 * vol / 1000000), 1),
            "战术/战略诊断": get_strategy_logic(m1, m5, h1, c24),
            "来源": src
        }
    except: return None
