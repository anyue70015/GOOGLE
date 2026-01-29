import streamlit as st
import ccxt.pro as ccxt_pro
import pandas as pd
import numpy as np
import asyncio
import threading
import os
import time
from streamlit.runtime.scriptrunner import add_script_run_ctx

st.set_page_config(page_title="2026量化神兵-v2rayN版", layout="wide")

if 'data_store' not in st.session_state:
    st.session_state.data_store = {}
if 'ws_active' not in st.session_state:
    st.session_state.ws_active = False

with st.sidebar:
    st.header("⚙️ v2rayN 极速配置")
    # 根据你的截图，v2rayN SOCKS 端口是 10810
    proxy_port = st.text_input("v2rayN SOCKS端口", value="10810")
    # 强制使用 SOCKS5 协议
    clash_proxy = f"socks5://127.0.0.1:{proxy_port}"
    
    os.environ['http_proxy'] = clash_proxy
    os.environ['https_proxy'] = clash_proxy
    
    st.divider()
    timeframe = st.selectbox("周期", ["1m", "5m", "15m", "1h"], index=1)
    vol_mul = st.slider("放量阈值", 1.0, 5.0, 2.2)
    refresh_rate = st.slider("UI刷新(秒)", 2, 30, 5)
    
    raw_symbols = st.text_area("列表", "BTC/USDT,ETH/USDT,SOL/USDT,ORDI/USDT,SUI/USDT,TIA/USDT")
    symbols = [s.strip().upper() for s in raw_symbols.replace('\n', ',').split(',') if s.strip()]

def compute_signals_vectorized(symbol_list, vol_multiplier):
    if not st.session_state.data_store: return pd.DataFrame()
    processed_data = []
    for symbol in symbol_list:
        df = st.session_state.data_store.get(symbol)
        if df is None or len(df) < 22: continue
        arr = df.to_numpy(dtype=np.float64)
        c, o, v = arr[:, 4], arr[:, 1], arr[:, 5]
        avg_v = np.mean(v[-21:-1])
        vol_ratio = v[-1] / avg_v if avg_v > 0 else 0
        change = ((c[-1] - c[-2]) / c[-2]) * 100
        sig = "⚠️" if (c[-1] > o[-1] and vol_ratio > vol_multiplier) else ""
        processed_data.append({"交易对": symbol, "现价": f"{c[-1]:.4f}", "涨跌": f"{change:+.2f}%", "放量比": f"{vol_ratio:.2f}x", "警报": sig, "raw": vol_ratio})
    return pd.DataFrame(processed_data).sort_values("raw", ascending=False).drop(columns="raw") if processed_data else pd.DataFrame()

async def market_worker(symbols, timeframe, proxy_url):
    exchange = ccxt_pro.binance({
        'enableRateLimit': True,
        'proxy': proxy_url, 'http_proxy': proxy_url, 'https_proxy': proxy_url,
        'timeout': 60000, # 针对弱网环境延长超时
        'options': {'defaultType': 'spot'}
    })
    async def handler(symbol):
        while True:
            try:
                # 尝试冷启动抓取
                hist = await exchange.fetch_ohlcv(symbol, timeframe, limit=60)
                st.session_state.data_store[symbol] = pd.DataFrame(hist, columns=['t', 'o', 'h', 'l', 'c', 'v'])
                # 进入 WS 监控
                while True:
                    ohlcv = await exchange.watch_ohlcv(symbol, timeframe, limit=100)
                    st.session_state.data_store[symbol] = pd.DataFrame(ohlcv, columns=['t', 'o', 'h', 'l', 'c', 'v'])
            except Exception:
                await asyncio.sleep(10)
    await asyncio.gather(*[handler(s) for s in symbols])

if st.button("🔥 启动监控", use_container_width=True):
    if not st.session_state.ws_active:
        loop = asyncio.new_event_loop()
        t = threading.Thread(target=loop.run_until_complete, args=(market_worker(symbols, timeframe, clash_proxy),))
        add_script_run_ctx(t)
        t.daemon = True
        t.start()
        st.session_state.ws_active = True

placeholder = st.empty()
if st.session_state.ws_active:
    while True:
        df = compute_signals_vectorized(symbols, vol_mul)
        with placeholder.container():
            if not df.empty:
                st.dataframe(df.style.apply(lambda r: ['background: rgba(255,0,0,0.1)']*len(r) if r['警报'] else ['']*len(r), axis=1), use_container_width=True, height=700)
            else:
                st.warning("⚠️ 节点响应慢/被拦截。请在 v2rayN 切换至新加坡/日本节点，并确认日志中出现 binance 字样。")
        time.sleep(refresh_rate)
