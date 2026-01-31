import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
import socket
from concurrent.futures import ThreadPoolExecutor

# --- 基础配置 ---
st.set_page_config(page_title="指挥部 - 万能雷达线程安全版", layout="wide")

def is_port_open(port):
    """快速检测本地端口是否开放"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.1)
        return s.connect_ex(('127.0.0.1', port)) == 0

def auto_radar_probe():
    """万能雷达：主线程运行，探测可用出口"""
    import requests
    # 覆盖你提到的所有端口及常见范围
    priority_ports = [7890, 10809, 10808, 10810, 10811, 1080, 1081, 7897, 7891]
    test_url = "https://api3.binance.com/api/v3/ping"
    
    # 1. 快速扫描常用端口
    for port in priority_ports:
        if is_port_open(port):
            url = f"http://127.0.0.1:{port}"
            try:
                if requests.get(test_url, proxies={"http": url, "https": url}, timeout=1).status_code == 200:
                    return url
            except: continue
    return None

def fetch_data(args):
    """
    子线程抓取函数 - 绝对不调用 st.session_state
    args 结构: (symbol, proxy_url)
    """
    symbol, proxy = args
    pair = f"{symbol}/USDT"
    res = {"币种": symbol, "最新价": "📡 扫描中"}
    
    ex = ccxt.binance({
        'enableRateLimit': True,
        'timeout': 10000,
        'hostname': 'api3.binance.com',
        'proxies': {'http': proxy, 'https': proxy} if proxy else {}
    })
    
    try:
        tk = ex.fetch_ticker(pair)
        curr_p = tk['last']
        res["最新价"] = f"{curr_p:,.2f}"
        res["24h"] = f"{tk.get('percentage', 0):+.2f}%"

        # 获取数据计算指标
        ohlcv = ex.fetch_ohlcv(pair, '1h', limit=30)
        df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
        
        if not df.empty:
            rsi = ta.rsi(df['c'], length=14).iloc[-1]
            res["RSI"] = round(rsi, 1)
            res["战术诊断"] = "🛒 底部" if rsi < 35 else ("⚠️ 高位" if rsi > 75 else "🔎 观望")
            
            obv = ta.obv(df['c'], df['v'])
            res["OBV"] = "💎流入" if obv.iloc[-1] > obv.iloc[-2] else "💀流出"
    except Exception:
        res["最新价"] = "❌ 断开"
        res["战术诊断"] = "节点异常"
    return res

# --- 主界面逻辑 ---
st.title("🛰️ 指挥部 - 万能雷达探测中")

# 在主线程初始化和存储状态
if 'proxy_url' not in st.session_state:
    st.session_state.proxy_url = None

# 如果没有锁定代理，执行雷达扫描
if st.session_state.proxy_url is None:
    with st.status("雷达正在扫描 127.0.0.1 的所有可能出口...", expanded=True) as status:
        found_url = auto_radar_probe()
        if found_url:
            st.session_state.proxy_url = found_url
            status.update(label=f"🎯 已锁定万能出口: {found_url}", state="complete")
        else:
            status.update(label="❌ 未发现可用代理，请确保代理软件已开启全局模式", state="error")

placeholder = st.empty()

while True:
    # 1. 提取当前代理地址（主线程操作）
    current_proxy = st.session_state.proxy_url
    
    # 2. 准备任务参数包 (Symbol, Proxy) -> 避免子线程访问 session_state
    monitor_list = ["BTC", "ETH", "SOL"]
    task_args = [(s, current_proxy) for s in monitor_list]

    # 3. 多线程执行
    with ThreadPoolExecutor(max_workers=len(monitor_list)) as executor:
        results = list(executor.map(fetch_data, task_args))
    
    df = pd.DataFrame(results)
    
    # 4. 渲染界面
    with placeholder.container():
        if current_proxy:
            st.success(f"📡 链路正常：{current_proxy}")
        else:
            if st.button("手动重新扫描"):
                st.session_state.proxy_url = None
                st.rerun()

        def style_logic(val):
            if not isinstance(val, str): return ''
            if "💎" in val or "🛒" in val: return 'color: #00ff00; font-weight: bold'
            if "💀" in val or "⚠️" in val: return 'color: #ff4b4b; font-weight: bold'
            return ''

        if not df.empty:
            st.dataframe(df.style.map(style_logic), use_container_width=True, hide_index=True)

    time.sleep(15)
