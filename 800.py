import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
import os
from concurrent.futures import ThreadPoolExecutor

# --- 基础配置 ---
st.set_page_config(page_title="指挥部 - 强制注入版", layout="wide")

# 【手动填写区】请填写你代理软件里显示的 HTTP 端口
MY_PROXY_PORT = "10810"  # 如果是 Clash 请改为 7890

def set_env_proxy(port):
    """强制注入系统环境变量，让所有请求强制走代理"""
    proxy_url = f"http://127.0.0.1:{port}"
    os.environ['http_proxy'] = proxy_url
    os.environ['https_proxy'] = proxy_url
    return proxy_url

def fetch_data(symbol):
    """子线程抓取 - 自动继承环境变量"""
    pair = f"{symbol}/USDT"
    res = {"币种": symbol, "最新价": "连接中"}
    
    # 无需在 ccxt 里传 proxies，因为它会自动读取环境变量
    ex = ccxt.binance({
        'enableRateLimit': True,
        'timeout': 15000,
        'hostname': 'api3.binance.com', 
    })
    
    try:
        tk = ex.fetch_ticker(pair)
        curr_p = tk['last']
        res["最新价"] = f"{curr_p:,.2f}"
        res["24h"] = f"{tk.get('percentage', 0):+.2f}%"

        ohlcv = ex.fetch_ohlcv(pair, '1h', limit=30)
        df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
        
        if not df.empty:
            rsi = ta.rsi(df['c'], length=14).iloc[-1]
            res["RSI"] = round(rsi, 1)
            res["战术诊断"] = "🛒 底部" if rsi < 35 else ("⚠️ 高位" if rsi > 75 else "🔎 观望")
            obv = ta.obv(df['c'], df['v'])
            res["OBV"] = "💎流入" if obv.iloc[-1] > obv.iloc[-2] else "💀流出"
    except Exception as e:
        res["最新价"] = "❌ 断开"
        res["战术诊断"] = "检查代理节点"
    return res

# --- 主界面 ---
st.title("🛰️ 指挥部 - 强制链路连接中")

# 启动时注入环境
current_proxy = set_env_proxy(MY_PROXY_PORT)

placeholder = st.empty()

while True:
    monitor_list = ["BTC", "ETH", "SOL"]
    
    # 线程池抓取
    with ThreadPoolExecutor(max_workers=len(monitor_list)) as executor:
        results = list(executor.map(fetch_data, monitor_list))
    
    df = pd.DataFrame(results)
    
    with placeholder.container():
        st.info(f"强制链路端口: `{MY_PROXY_PORT}` | 模式: 全局注入")
        
        def style_logic(val):
            if not isinstance(val, str): return ''
            if any(x in val for x in ["💎", "🛒"]): return 'color: #00ff00; font-weight: bold'
            if any(x in val for x in ["💀", "⚠️", "❌"]): return 'color: #ff4b4b; font-weight: bold'
            return ''

        if not df.empty:
            st.dataframe(df.style.map(style_logic), use_container_width=True, hide_index=True)
            
    time.sleep(10)

