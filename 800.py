import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
import os

# --- 核心配置 ---
st.set_page_config(page_title="指挥部 - 穿透模式", layout="wide")

# 强制锁定 10811，这是 v2rayN 最通用的 Mixed 端口
# 如果 10811 依旧拦截，请尝试改为 10809 (HTTP 端口)
PROXY_PORT = "10811"
PROXY_URL = f"http://127.0.0.1:{PROXY_PORT}"

def get_exchange_instance():
    """
    创建一个具备持久连接能力的交易所实例
    """
    return ccxt.binance({
        'proxies': {
            'http': PROXY_URL,
            'https': PROXY_URL,
        },
        'enableRateLimit': True,
        'timeout': 40000,
        'hostname': 'api.binance.me', # 浏览器已验证可行的域名
        'headers': {
            # 完整伪装浏览器头部
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
    })

def fetch_safe(symbol):
    pair = f"{symbol}/USDT"
    ex = get_exchange_instance()
    try:
        # 第一步：只拿价格，测试链路
        tk = ex.fetch_ticker(pair)
        
        # 第二步：获取 K 线
        ohlcv = ex.fetch_ohlcv(pair, '1h', limit=30)
        df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
        
        # 计算核心指标
        rsi = ta.rsi(df['c'], length=14).iloc[-1]
        obv = ta.obv(df['c'], df['v'])
        obv_s = "💎流入" if obv.iloc[-1] > obv.iloc[-2] else "💀流出"
        
        return {
            "币种": symbol,
            "最新价": f"{tk['last']:,.2f}",
            "RSI": round(rsi, 1),
            "OBV": obv_s,
            "链路": "✅ 穿透成功"
        }
    except Exception as e:
        error_msg = str(e)
        # 简化报错显示
        state = "❌ 节点截断" if "EOF" in error_msg else "⚠️ 超时"
        return {
            "币种": symbol, "最新价": "等待中", "RSI": "-", "OBV": "-", "链路": state
        }

# --- UI 渲染 ---
st.title("🛰️ 终极指挥部 - 深度链路穿透版")
st.caption(f"当前物理链路：{PROXY_URL} | 目标：api.binance.me")

if st.button("⚡ 暴力重置连接"):
    # 清理所有环境变量，防止冲突
    os.environ.pop('http_proxy', None)
    os.environ.pop('https_proxy', None)
    st.rerun()

placeholder = st.empty()

while True:
    # 采用串行抓取，避免并发导致节点限流
    results = []
    for s in ["BTC", "ETH", "SOL"]:
        results.append(fetch_safe(s))
    
    df = pd.DataFrame(results)
    
    with placeholder.container():
        def style_map(val):
            if "✅" in str(val) or "💎" in str(val): return 'color: #00ff00; font-weight: bold'
            if "❌" in str(val) or "💀" in str(val): return 'color: #ff4b4b; font-weight: bold'
            return ''

        st.dataframe(df.style.map(style_map), use_container_width=True, hide_index=True)
        
        if "❌ 节点截断" in df.values:
            st.error("🚨 节点依然掐断连接！请检查 v2rayN 底部状态栏，确保【启用Tun】是开启状态，且系统代理设为【自动配置系统代理】。")

    time.sleep(12)
