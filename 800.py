import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta

# --- 核心配置 ---
st.set_page_config(page_title="指挥部 - 暴力打通版", layout="wide")

# 根据你的截图，v2rayN 的混合端口通常是 10811
# 我们直接把代理写进 ccxt 的配置里，不依赖环境变量
PROXY_CONFIG = {
    'http': 'http://127.0.0.1:10811',
    'https': 'http://127.0.0.1:10811',
}

def fetch_data_brute_force(symbol):
    pair = f"{symbol}/USDT"
    # 直接在初始化时塞入代理，并切换到 binance.us (有时这个域名更稳) 或 binance.me
    ex = ccxt.binance({
        'proxies': PROXY_CONFIG,
        'enableRateLimit': True,
        'timeout': 50000, # 提高到 50 秒，对抗你 2300ms 的延迟
        'hostname': 'api.binance.me', 
    })
    
    try:
        # 尝试最基础的 ping
        ex.public_get_ping() 
        
        tk = ex.fetch_ticker(pair)
        return {
            "币种": symbol,
            "最新价": f"{tk['last']:,.2f}",
            "状态": "✅ 通畅"
        }
    except Exception as e:
        return {
            "币种": symbol,
            "最新价": "❌ 失败",
            "状态": f"节点太慢或被封"
        }

# --- UI 渲染 ---
st.title("🛰️ 终极暴力测试版")
if st.button("⚡ 强制重连"):
    st.rerun()

results = [fetch_data_brute_force(s) for s in ["BTC", "ETH"]]
st.table(pd.DataFrame(results))
