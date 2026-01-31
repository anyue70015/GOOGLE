import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta

# --- 基础配置 ---
st.set_page_config(page_title="指挥部 - 模拟浏览器版", layout="wide")

# 根据你图 7 的截图，使用 mixed 端口 10811
# 如果依然不通，请在 v2rayN 中确认 HTTP 代理端口（通常是 10809）
PROXY_URL = "http://127.0.0.1:10811"

def fetch_data_as_browser(symbol):
    pair = f"{symbol}/USDT"
    
    # 强制伪装成 Chrome 浏览器，对齐你浏览器的成功握手特征
    ex = ccxt.binance({
        'proxies': {
            'http': PROXY_URL,
            'https': PROXY_URL,
        },
        'enableRateLimit': True,
        'timeout': 30000,
        'hostname': 'api.binance.me', 
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.binance.me/'
        }
    })
    
    try:
        # 获取基础行情
        tk = ex.fetch_ticker(pair)
        
        # 获取K线做技术分析
        ohlcv = ex.fetch_ohlcv(pair, '1h', limit=30)
        df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
        
        rsi = ta.rsi(df['c'], length=14).iloc[-1] if not df.empty else 50
        obv = ta.obv(df['c'], df['v'])
        obv_trend = "💎流入" if len(obv) > 1 and obv.iloc[-1] > obv.iloc[-2] else "💀流出"
        
        return {
            "币种": symbol,
            "最新价": f"{tk['last']:,.2f}",
            "RSI": round(rsi, 1),
            "资金流": obv_trend,
            "链路状态": "✅ 握手成功"
        }
    except Exception as e:
        # 如果依然报错，将具体原因打印到后台
        print(f"DEBUG: {symbol} 失败原因 -> {e}")
        return {
            "币种": symbol,
            "最新价": "❌ 拦截",
            "RSI": "-",
            "资金流": "-",
            "链路状态": "节点掐断连接"
        }

# --- UI 渲染 ---
st.title("🛰️ 终极对齐版 - 浏览器流量特征模拟")
st.info(f"当前策略：伪装 Chrome 访问 `api.binance.me` | 端口：{PROXY_URL}")

if st.button("🔄 刷新链路"):
    st.rerun()

placeholder = st.empty()

# 循环更新
while True:
    # 先跑 BTC 和 ETH 验证
    results = [fetch_data_as_browser("BTC"), fetch_data_as_browser("ETH")]
    df = pd.DataFrame(results)
    
    with placeholder.container():
        def color_row(val):
            if "✅" in str(val): return 'color: #00ff00; font-weight: bold'
            if "❌" in str(val): return 'color: #ff4b4b; font-weight: bold'
            return ''
            
        st.dataframe(df.style.map(color_row), use_container_width=True, hide_index=True)
        
        if "❌ 拦截" in df.values:
            st.error("⚠️ 节点仍然掐断连接！请进入 v2rayN 设置，彻底关闭『Mux 多路复用』并重启软件。")

    time.sleep(10)
