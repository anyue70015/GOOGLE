import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
import urllib3

# 彻底禁用 SSL 警告（因为我们要强制穿透）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 基础配置 ---
st.set_page_config(page_title="指挥部 - 强制穿透版", layout="wide")

# 确认使用 10811 (Mixed) 或 10809 (HTTP)
PROXY_PORT = "10811" 

def fetch_data_ignore_ssl(symbol):
    pair = f"{symbol}/USDT"
    
    # 终极配置：跳过证书检查 + 伪装浏览器 + 锁定域名
    ex = ccxt.binance({
        'proxies': {
            'http': f'http://127.0.0.1:{PROXY_PORT}',
            'https': f'http://127.0.0.1:{PROXY_PORT}',
        },
        'enableRateLimit': True,
        'timeout': 30000,
        'hostname': 'api.binance.me', 
        # 核心：禁用 SSL 验证，防止代理拦截
        'verify': False, 
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0 Safari/537.36',
        }
    })
    
    try:
        # 抓取 Ticker
        tk = ex.fetch_ticker(pair)
        
        # 抓取 K 线
        ohlcv = ex.fetch_ohlcv(pair, '1h', limit=35)
        df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
        
        rsi = ta.rsi(df['c'], length=14).iloc[-1]
        obv = ta.obv(df['c'], df['v'])
        trend = "💎流入" if obv.iloc[-1] > obv.iloc[-2] else "💀流出"
        
        return {
            "币种": symbol,
            "最新价": f"{tk['last']:,.2f}",
            "RSI": round(rsi, 1),
            "资金流": trend,
            "链路": "✅ 强制穿透成功"
        }
    except Exception as e:
        return {
            "币种": symbol,
            "最新价": "---",
            "RSI": "-",
            "资金流": "-",
            "链路": "❌ 物理阻断"
        }

# --- 界面 ---
st.title("🛰️ 终极指挥部 - 强制非安全穿透")
st.warning("⚠️ 当前已开启 [SSL 禁用模式]，正在强制绕过代理握手拦截...")

if st.button("🚀 重新连接"):
    st.rerun()

placeholder = st.empty()

while True:
    targets = ["BTC", "ETH", "SOL"]
    results = [fetch_data_ignore_ssl(s) for s in targets]
    
    df = pd.DataFrame(results)
    
    with placeholder.container():
        def color_map(val):
            if "✅" in str(val) or "💎" in str(val): return 'color: #00ff00; font-weight: bold'
            if "❌" in str(val) or "💀" in str(val): return 'color: #ff4b4b; font-weight: bold'
            return ''

        st.dataframe(df.style.map(color_map), use_container_width=True, hide_index=True)
    
    time.sleep(10)
