import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
import socket

# --- 核心配置 ---
st.set_page_config(page_title="指挥部 - 深度隧道版", layout="wide")

# v2rayN 默认 SOCKS 端口是 10808，混合端口是 10811
# 我们直接尝试 SOCKS 协议，因为它比 HTTP 协议在代码端更稳
SOCKS_PORT = "10811" 

def fetch_data_tunnel(symbol):
    """
    深度隧道模式：使用 socks5h 强制远程解析，跳过本地一切干扰
    """
    pair = f"{symbol}/USDT"
    
    # 初始化 ccxt，直接注入 SOCKS5h 代理
    # socks5h 中的 'h' 代表远程 DNS 解析，专门对付“浏览器通代码不通”
    ex = ccxt.binance({
        'proxies': {
            'http': f'socks5h://127.0.0.1:{SOCKS_PORT}',
            'https': f'socks5h://127.0.0.1:{SOCKS_PORT}',
        },
        'enableRateLimit': True,
        'timeout': 30000, 
        'hostname': 'api.binance.me', # 浏览器已经跑通的地址
    })
    
    try:
        # 1. 抓取行情
        tk = ex.fetch_ticker(pair)
        
        # 2. 抓取 K 线
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
            "链路": "✅ 深度穿透成功"
        }
    except Exception as e:
        # 记录具体错误
        err_str = str(e)
        status = "⚠️ 代理端口错" if "10061" in err_str else "❌ 节点握手失败"
        return {
            "币种": symbol, "最新价": "---", "RSI": "-", "资金流": "-", "链路": status
        }

# --- UI 渲染 ---
st.title("🛰️ 终极指挥部 - 深度隧道模式")
st.info(f"正在通过 SOCKS5h 隧道连接 127.0.0.1:{SOCKS_PORT}，强制远程 DNS 解析...")

if st.button("🚀 暴力重启链路"):
    st.rerun()

placeholder = st.empty()

while True:
    # 串行执行，确保每一跳都稳健
    targets = ["BTC", "ETH", "SOL"]
    results = []
    
    for s in targets:
        results.append(fetch_data_tunnel(s))
        time.sleep(1) # 给节点一点缓冲时间
        
    df = pd.DataFrame(results)
    
    with placeholder.container():
        def color_map(val):
            if "✅" in str(val) or "💎" in str(val): return 'color: #00ff00; font-weight: bold'
            if "❌" in str(val) or "⚠️" in str(val) or "💀" in str(val): return 'color: #ff4b4b; font-weight: bold'
            return ''

        st.dataframe(df.style.map(color_map), use_container_width=True, hide_index=True)
        
        if "❌ 节点握手失败" in df.values:
            st.warning("🚨 节点握手失败！请检查 v2rayN：\n1. 确保选中了延迟为 326ms 的那个蓝色节点。\n2. 确保 v2rayN 的底部【系统代理】显示为【清除系统代理】（不要让它劫持 Python）。")

    time.sleep(10)
