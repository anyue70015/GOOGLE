import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta

# --- 基础配置 ---
st.set_page_config(page_title="指挥部 - 高延迟暴力重连版", layout="wide")

# 根据你图 7 的截图， mixed 端口是 10811，这是最稳的端口
PROXY_CONFIG = {
    'http': 'http://127.0.0.1:10811',
    'https': 'http://127.0.0.1:10811',
}

def fetch_data_with_patience(symbol):
    """
    针对 2300ms 极高延迟节点优化的抓取函数
    """
    pair = f"{symbol}/USDT"
    # 强制锁定 binance.me
    ex = ccxt.binance({
        'proxies': PROXY_CONFIG,
        'enableRateLimit': True,
        'timeout': 60000, # 极长超时：60秒，对付你 2秒多的物理延迟
        'hostname': 'api.binance.me', 
    })
    
    # 暴力重试机制
    for i in range(3):
        try:
            # 基础行情
            tk = ex.fetch_ticker(pair)
            
            # K线分析
            ohlcv = ex.fetch_ohlcv(pair, '1h', limit=30)
            df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
            rsi = ta.rsi(df['c'], length=14).iloc[-1] if not df.empty else 50
            
            return {
                "币种": symbol,
                "最新价": f"{tk['last']:,.2f}",
                "RSI": round(rsi, 1),
                "状态": "✅ 已穿透高延迟"
            }
        except Exception as e:
            if i < 2:
                time.sleep(1) # 失败了歇一秒再试
                continue
            return {
                "币种": symbol,
                "最新价": "❌ 链路拥堵",
                "RSI": "-",
                "状态": "节点延迟过高"
            }

# --- 界面渲染 ---
st.title("🛰️ 终极暴力监控站")
st.warning(f"检测到物理链路延迟高达 2000ms+，正在通过 10811 端口进行暴力穿透...")

if st.button("⚡ 强制重试链路"):
    st.rerun()

placeholder = st.empty()

while True:
    # 减少并发，一个一个抓，防止由于节点太差导致并发死锁
    results = []
    for s in ["BTC", "ETH"]:
        results.append(fetch_data_with_patience(s))
    
    df = pd.DataFrame(results)
    
    with placeholder.container():
        def style_logic(val):
            if "✅" in str(val): return 'color: #00ff00; font-weight: bold'
            if "❌" in str(val): return 'color: #ff4b4b; font-weight: bold'
            return ''
            
        st.dataframe(df.style.map(style_logic), use_container_width=True, hide_index=True)
    
    time.sleep(10)
