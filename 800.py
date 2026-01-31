import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
import os
from concurrent.futures import ThreadPoolExecutor

# --- 核心配置区 ---
st.set_page_config(page_title="指挥部 - 最终通达版", layout="wide")

# 【非常重要】请确认你代理软件的 SOCKS 端口（通常 v2rayN 是 10808，Clash 是 7890）
SOCKS_PORT = "10810" 

def setup_global_proxy(port):
    """
    强制注入系统环境变量
    使用 socks5h 协议可以强制代理软件接管 DNS 和所有流量，绕过直连误判
    """
    p_url = f"socks5h://127.0.0.1:{port}"
    os.environ['http_proxy'] = p_url
    os.environ['https_proxy'] = p_url
    return p_url

def fetch_data(symbol):
    """
    抓取函数 - 增加多重容错和长超时
    """
    pair = f"{symbol}/USDT"
    res = {"币种": symbol, "最新价": "连接中", "战术诊断": "初始化"}
    
    # 强制锁定浏览器能通的 api.binance.me 域名
    ex = ccxt.binance({
        'enableRateLimit': True,
        'timeout': 30000,        # 延长超时至 30 秒防止 EOF
        'hostname': 'api.binance.me', 
        'options': {'defaultType': 'spot'}
    })
    
    # 增加 3 次自动重试逻辑，对付节点不稳
    for attempt in range(3):
        try:
            # 抓取 Ticker
            tk = ex.fetch_ticker(pair)
            curr_p = tk['last']
            res["最新价"] = f"{curr_p:,.2f}"
            res["24h"] = f"{tk.get('percentage', 0):+.2f}%"

            # 抓取 K 线做技术分析
            ohlcv = ex.fetch_ohlcv(pair, '1h', limit=40)
            df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
            
            if not df.empty:
                rsi = ta.rsi(df['c'], length=14).iloc[-1]
                res["RSI"] = round(rsi, 1)
                
                # OBV 流向判断
                obv = ta.obv(df['c'], df['v'])
                res["OBV"] = "💎流入" if obv.iloc[-1] > obv.iloc[-2] else "💀流出"
                
                # 简单战术逻辑
                if rsi < 35: res["战术诊断"] = "🛒 底部吸筹"
                elif rsi > 70: res["战术诊断"] = "⚠️ 风险高位"
                else: res["战术诊断"] = "🔎 观望中"
            
            # 只要成功一次就跳出重试
            break 
            
        except Exception as e:
            if attempt < 2:
                time.sleep(2) # 失败重试等待
                continue
            res["最新价"] = "❌ 断开"
            res["战术诊断"] = "节点解析失败"
            # 打印具体错误到后台日志方便排查
            print(f"Error fetching {symbol}: {e}")
            
    return res

# --- UI 逻辑区 ---
st.title("🛰️ 终极通达指挥部")

# 1. 注入环境变量（主线程）
current_proxy = setup_global_proxy(SOCKS_PORT)

placeholder = st.empty()

# 2. 运行主循环
while True:
    # 监控列表，你可以自行增加
    monitor_list = ["BTC", "ETH", "SOL"]
    
    # 使用 ThreadPoolExecutor 并行抓取，避免单币种卡死影响全局
    with ThreadPoolExecutor(max_workers=len(monitor_list)) as executor:
        # 子线程会自动继承主线程设置的 os.environ 代理
        results = list(executor.map(fetch_data, monitor_list))
    
    df = pd.DataFrame(results)
    
    with placeholder.container():
        st.success(f"📡 链路协议：{current_proxy} (域名锁定: api.binance.me)")
        
        # 视觉样式
        def style_df(val):
            if not isinstance(val, str): return ''
            if "💎" in val or "🛒" in val: return 'background-color: #002200; color: #00ff00'
            if "💀" in val or "⚠️" in val or "❌" in val: return 'background-color: #220000; color: #ff4b4b'
            return ''

        if not df.empty:
            st.dataframe(
                df.style.applymap(style_df), 
                use_container_width=True, 
                hide_index=True
            )
            
    # 每 15 秒更新一次
    time.sleep(15)
