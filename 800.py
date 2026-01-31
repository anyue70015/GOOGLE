import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta

# --- 核心配置 ---
st.set_page_config(page_title="指挥部 - 强制穿透版", layout="wide")

# v2rayN 的标准端口
# 如果 10811 不行，请务必尝试改为 10809 (HTTP专用) 或 10808 (SOCKS专用)
PROXY_PORT = "10811" 

def fetch_data_direct(symbol):
    """
    完全独立、不依赖系统环境的抓取逻辑
    """
    pair = f"{symbol}/USDT"
    
    # 强制独立代理设置，避开环境变量干扰
    ex = ccxt.binance({
        'proxies': {
            'http': f'http://127.0.0.1:{PROXY_PORT}',
            'https': f'http://127.0.0.1:{PROXY_PORT}',
        },
        'enableRateLimit': True,
        'timeout': 45000, # 针对 326ms 延迟，给足握手时间
        'hostname': 'api.binance.me', 
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0 Safari/537.36',
        }
    })
    
    try:
        # 1. 抓取行情 (限制重试)
        tk = ex.fetch_ticker(pair)
        
        # 2. 抓取K线
        ohlcv = ex.fetch_ohlcv(pair, '1h', limit=35)
        df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
        
        # 3. 计算指标
        rsi = ta.rsi(df['c'], length=14).iloc[-1]
        obv = ta.obv(df['c'], df['v'])
        trend = "💎流入" if obv.iloc[-1] > obv.iloc[-2] else "💀流出"
        
        return {
            "币种": symbol,
            "最新价": f"{tk['last']:,.2f}",
            "RSI": round(rsi, 1),
            "资金流": trend,
            "状态": "✅ 正常"
        }
    except Exception as e:
        # 将具体错误打印到控制台
        print(f"Error for {symbol}: {e}")
        return {
            "币种": symbol,
            "最新价": "超时/断开",
            "RSI": "-",
            "资金流": "-",
            "状态": "⚠️ 链路阻断"
        }

# --- UI 渲染 ---
st.title("🛰️ 终极指挥部 - 独立链路模式")
st.caption(f"当前强制出口：127.0.0.1:{PROXY_PORT} | 协议：Mixed/HTTP")

if st.button("⚡ 暴力重跑程序"):
    st.rerun()

placeholder = st.empty()

# 主循环
while True:
    # 串行请求，防止瞬间并发导致节点丢包
    results = []
    for s in ["BTC", "ETH"]:
        results.append(fetch_data_direct(s))
        time.sleep(0.5) # 币种间隔
    
    df = pd.DataFrame(results)
    
    with placeholder.container():
        def color_logic(val):
            if "✅" in str(val) or "💎" in str(val): return 'color: #00ff00; font-weight: bold'
            if "⚠️" in str(val) or "💀" in str(val): return 'color: #ff4b4b; font-weight: bold'
            return ''

        st.dataframe(df.style.map(color_logic), use_container_width=True, hide_index=True)
        
        if "⚠️ 链路阻断" in df.values:
            st.info("💡 解决办法：\n1. 请在 v2rayN 右下角切换【系统代理】为【清除系统代理】后再运行。\n2. 尝试将代码中的 PROXY_PORT 改为 10809 (HTTP端口)。")

    time.sleep(12)
