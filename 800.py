import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
import os
import requests

# --- 基础配置 ---
st.set_page_config(page_title="指挥部 - 最终终极版", layout="wide")

# 【核心：根据你的截图，10811 通常是 HTTP/Mixed 端口】
PROXY_PORT = "10811" 

def force_proxy_setup():
    """强制注入最稳健的 HTTP 代理环境变量"""
    proxy_url = f"http://127.0.0.1:{PROXY_PORT}"
    os.environ['http_proxy'] = proxy_url
    os.environ['https_proxy'] = proxy_url
    # 禁用 Python 的默认分流，强制全部走代理
    os.environ['no_proxy'] = '' 
    return proxy_url

def fetch_data_stable(symbol):
    """
    使用浏览器已验证的域名，并增加重试逻辑
    """
    pair = f"{symbol}/USDT"
    # 初始化 ccxt，强制锁定 api.binance.me
    ex = ccxt.binance({
        'enableRateLimit': True,
        'timeout': 30000, 
        'hostname': 'api.binance.me', 
    })
    
    try:
        # 获取行情
        tk = ex.fetch_ticker(pair)
        curr_p = tk['last']
        
        # 获取K线计算RSI
        ohlcv = ex.fetch_ohlcv(pair, '1h', limit=35)
        df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
        rsi_val = ta.rsi(df['c'], length=14).iloc[-1] if len(df) >= 14 else 50
        
        # 计算OBV流向判断
        obv = ta.obv(df['c'], df['v'])
        obv_direction = "💎流入" if len(obv) > 1 and obv.iloc[-1] > obv.iloc[-2] else "💀流出"
        
        return {
            "币种": symbol,
            "最新价": f"{curr_p:,.2f}",
            "24h涨跌": f"{tk.get('percentage', 0):+.2f}%",
            "RSI": round(rsi_val, 1),
            "资金流": obv_direction,
            "状态": "✅ 正常"
        }
    except Exception as e:
        return {
            "币种": symbol,
            "最新价": "❌ 重连中",
            "24h涨跌": "-",
            "RSI": "-",
            "资金流": "-",
            "状态": "请开启全局代理"
        }

# --- 界面展示 ---
st.title("🛰️ 终极通达监控站")

# 1. 注入环境
proxy_url = force_proxy_setup()

# 2. 增加一个手动刷新按钮，方便调试
if st.button("🔄 手动刷新链路"):
    st.rerun()

placeholder = st.empty()

while True:
    # 监控列表
    targets = ["BTC", "ETH", "SOL"]
    
    # 获取数据
    results = [fetch_data_stable(s) for s in targets]
    df = pd.DataFrame(results)
    
    with placeholder.container():
        st.success(f"📡 链路状态：已连接至 {proxy_url} (域名: api.binance.me)")
        
        def color_logic(val):
            if "✅" in str(val) or "💎" in str(val): return 'color: #00ff00; font-weight: bold'
            if "❌" in str(val) or "💀" in str(val): return 'color: #ff4b4b; font-weight: bold'
            return ''

        # 渲染表格
        st.dataframe(
            df.style.map(color_logic),
            use_container_width=True,
            hide_index=True
        )
        
        # 如果全部失败，显示提示
        if "❌ 重连中" in df.values:
            st.warning("⚠️ 提示：如果浏览器能开但此处不通，请将代理软件切换至【全局模式 (Global)】")

    time.sleep(10)
