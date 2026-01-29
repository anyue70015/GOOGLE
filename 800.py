import streamlit as st
import ccxt.pro as ccxt_pro
import pandas as pd
import numpy as np
import asyncio
import threading
import os
import time
from streamlit.runtime.scriptrunner import add_script_run_ctx

# ==========================================
# 1. 页面基础配置
# ==========================================
st.set_page_config(page_title="2026量化神兵-v2rayN专用版", layout="wide")

if 'data_store' not in st.session_state:
    st.session_state.data_store = {}
if 'ws_active' not in st.session_state:
    st.session_state.ws_active = False

# ==========================================
# 2. 侧边栏：核心配置 (适配 v2rayN)
# ==========================================
with st.sidebar:
    st.header("⚙️ v2rayN 监控配置")
    
    # 截图显示 v2rayN 的 SOCKS 端口是 10810，HTTP 是 10809
    # 建议量化交易优先使用 SOCKS5
    proxy_port = st.text_input("代理端口 (v2rayN建议10810)", value="10810")
    
    # 构建 SOCKS5 代理字符串
    clash_proxy = f"socks5://127.0.0.1:{proxy_port}"
    
    # 环境变量注入
    os.environ['http_proxy'] = clash_proxy
    os.environ['https_proxy'] = clash_proxy
    
    st.info(f"当前代理协议: {clash_proxy}")
    
    st.divider()
    
    timeframe = st.selectbox("K线周期", ["1m", "5m", "15m", "1h"], index=1)
    vol_mul = st.slider("放量阈值 (x)", 1.0, 5.0, 2.2)
    refresh_rate = st.slider("UI 刷新频率 (秒)", 2, 30, 5)
    
    raw_symbols = st.text_area("监控列表 (支持空格/逗号/换行)", 
                              "BTC/USDT,ETH/USDT,SOL/USDT,ORDI/USDT,SUI/USDT,TIA/USDT")
    symbols = [s.strip().upper() for s in raw_symbols.replace('\n', ',').replace(' ', ',').split(',') if s.strip()]
    
    if st.button("🧹 重置连接"):
        st.session_state.data_store = {}
        st.session_state.ws_active = False
        st.rerun()

# ==========================================
# 3. 高性能向量化计算引擎
# ==========================================
def compute_signals_vectorized(symbol_list, vol_multiplier):
    if not st.session_state.data_store:
        return pd.DataFrame()

    processed_data = []
    for symbol in symbol_list:
        df = st.session_state.data_store.get(symbol)
        if df is None or len(df) < 22:
            continue
        
        arr = df.to_numpy(dtype=np.float64)
        close_prices, open_prices, volumes = arr[:, 4], arr[:, 1], arr[:, 5]

        curr_c, prev_c = close_prices[-1], close_prices[-2]
        curr_o, curr_v = open_prices[-1], volumes[-1]
        
        avg_v = np.mean(volumes[-21:-1])
        vol_ratio = curr_v / avg_v if avg_v > 0 else 0
        change_pct = ((curr_c - prev_c) / prev_c) * 100

        sig1 = (curr_c > curr_o) and (vol_ratio > vol_multiplier)
        sig2 = (vol_ratio > 1.3) and (change_pct > 0.7)
        
        active_sigs = [str(i) for i, s in enumerate([sig1, sig2], 1) if s]
        
        processed_data.append({
            "交易对": symbol,
            "现价": f"{curr_c:.4f}",
            "涨跌幅": f"{change_pct:+.2f}%",
            "放量比": f"{vol_ratio:.2f}x",
            "信号": ",".join(active_sigs),
            "警报": "⚠️" if active_sigs else "",
            "sort_key": vol_ratio
        })

    if not processed_data: return pd.DataFrame()
    res_df = pd.DataFrame(processed_data)
    return res_df.sort_values("sort_key", ascending=False).drop(columns=["sort_key"])

# ==========================================
# 4. 增强版数据抓取线程
# ==========================================
async def market_worker(symbols, timeframe, proxy_url):
    # 针对 v2rayN 优化的连接参数
    exchange = ccxt_pro.binance({
        'enableRateLimit': True,
        'proxy': proxy_url,      # 适配 SOCKS5
        'http_proxy': proxy_url,
        'https_proxy': proxy_url,
        'timeout': 30000,        # 增加超时到30秒，适配免费节点
        'options': {'defaultType': 'spot'}
    })

    async def single_symbol_handler(symbol):
        # --- A: 强制冷启动 ---
        retry = 0
        while retry < 5:
            try:
                history = await exchange.fetch_ohlcv(symbol, timeframe, limit=60)
                if history:
                    st.session_state.data_store[symbol] = pd.DataFrame(
                        history, columns=['t', 'o', 'h', 'l', 'c', 'v']
                    )
                    break
            except Exception as e:
                retry += 1
                await asyncio.sleep(3)

        # --- B: WebSocket 实时接管 ---
        while True:
            try:
                ohlcv = await exchange.watch_ohlcv(symbol, timeframe, limit=100)
                if ohlcv:
                    st.session_state.data_store[symbol] = pd.DataFrame(
                        ohlcv, columns=['t', 'o', 'h', 'l', 'c', 'v']
                    )
            except Exception as e:
                await asyncio.sleep(15)

    try:
        tasks = [single_symbol_handler(s) for s in symbols]
        await asyncio.gather(*tasks)
    finally:
        await exchange.close()

def start_background_loop(symbols, timeframe, proxy_url):
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_until_complete, 
                         args=(market_worker(symbols, timeframe, proxy_url),))
    add_script_run_ctx(t) 
    t.daemon = True
    t.start()

# ==========================================
# 5. 主界面渲染
# ==========================================
st.title("🚀 2026 量化扫描器-v2rayN版")

if st.button("🔥 启动监控", use_container_width=True):
    if not st.session_state.ws_active:
        start_background_loop(symbols, timeframe, clash_proxy)
        st.session_state.ws_active = True
        st.toast("正在建立 SOCKS5 连接...")

placeholder = st.empty()

if st.session_state.ws_active:
    while True:
        df_display = compute_signals_vectorized(symbols, vol_mul)
        with placeholder.container():
            if not df_display.empty:
                st.write(f"📊 监控中: {len(st.session_state.data_store)} 币种 | 刷新: {time.strftime('%H:%M:%S')}")
                def highlight_row(row):
                    return ['background-color: rgba(255, 75, 75, 0.2);' if row['警报'] == '⚠️' else '' for _ in row]
                st.dataframe(df_display.style.apply(highlight_row, axis=1), use_container_width=True, height=750)
            else:
                st.info("💡 正在通过 v2rayN 同步历史数据，若超过 30 秒无反应，请检查：\n1. 节点是否支持币安 (勿用香港节点)\n2. v2rayN 是否开启了 Tun 模式")
        time.sleep(refresh_rate)
else:
    st.warning("👈 请输入 v2rayN 的端口 (默认10810) 并启动")
