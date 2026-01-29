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
# 1. 懒人代理配置 (自动识别 Clash)
# ==========================================
CLASH_PROXY = "http://127.0.0.1:7890"
os.environ['http_proxy'] = CLASH_PROXY
os.environ['https_proxy'] = CLASH_PROXY

st.set_page_config(page_title="2026量化神兵-极速版", layout="wide")

# ==========================================
# 2. 全局状态初始化
# ==========================================
if 'data_store' not in st.session_state:
    st.session_state.data_store = {}  # 存放每个币种的 DataFrame
if 'ws_active' not in st.session_state:
    st.session_state.ws_active = False

# ==========================================
# 3. 高性能向量化信号引擎
# ==========================================
def compute_signals_vectorized(symbols, vol_multiplier):
    if not st.session_state.data_store:
        return pd.DataFrame()

    processed_data = []
    for symbol in symbols:
        df = st.session_state.data_store.get(symbol)
        if df is None or len(df) < 22:
            continue
        
        # 转换为 NumPy 矩阵加速计算 (t, o, h, l, c, v)
        arr = df.to_numpy(dtype=np.float64)
        close_prices = arr[:, 4]
        open_prices = arr[:, 1]
        volumes = arr[:, 5]

        curr_c, prev_c = close_prices[-1], close_prices[-2]
        curr_o, curr_v = open_prices[-1], volumes[-1]
        
        # 计算过去 20 根 K 线的均量
        avg_v = np.mean(volumes[-21:-1])
        vol_ratio = curr_v / avg_v if avg_v > 0 else 0
        change_pct = ((curr_c - prev_c) / prev_c) * 100

        # 信号判定
        sig1 = (curr_c > curr_o) and (vol_ratio > vol_multiplier) # 阳线放量
        sig2 = (vol_ratio > 1.5) and (change_pct > 0.8)          # 动能突破
        
        active_sigs = [str(i) for i, s in enumerate([sig1, sig2], 1) if s]
        
        processed_data.append({
            "交易对": symbol,
            "现价": f"{curr_c:.4f}",
            "涨幅%": f"{change_pct:+.2f}%",
            "放量比": f"{vol_ratio:.2f}x",
            "信号": ",".join(active_sigs),
            "警报": "⚠️" if active_sigs else "",
            "sort_key": vol_ratio
        })

    if not processed_data: return pd.DataFrame()
    
    res_df = pd.DataFrame(processed_data)
    return res_df.sort_values("sort_key", ascending=False).drop(columns=["sort_key"])

# ==========================================
# 4. 后台异步 WebSocket 线程
# ==========================================
async def watch_market(symbols, timeframe):
    # 初始化交易所，带上代理
    exchange = ccxt_pro.binance({
        'enableRateLimit': True,
        'proxies': {'http': CLASH_PROXY, 'https': CLASH_PROXY},
        'options': {'defaultType': 'spot'}
    })

    async def symbol_loop(symbol):
        while True:
            try:
                # 获取数据（ccxt.pro 会自动处理增量更新）
                ohlcv = await exchange.watch_ohlcv(symbol, timeframe, limit=100)
                df = pd.DataFrame(ohlcv, columns=['t', 'o', 'h', 'l', 'c', 'v'])
                st.session_state.data_store[symbol] = df
            except Exception as e:
                await asyncio.sleep(10) # 报错重试

    tasks = [symbol_loop(s) for s in symbols]
    await asyncio.gather(*tasks)

def start_ws_thread(symbols, timeframe):
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_until_complete, args=(watch_market(symbols, timeframe),))
    add_script_run_ctx(t) # 注入 Streamlit 上下文
    t.daemon = True
    t.start()

# ==========================================
# 5. Streamlit UI 界面
# ==========================================
st.title("🚀 2026 极速聚合扫描器")

with st.sidebar:
    st.header("配置中心")
    proxy_status = st.success(f"代理状态: {CLASH_PROXY}")
    timeframe = st.selectbox("K线周期", ["1m", "5m", "15m", "1h"], index=1)
    vol_mul = st.slider("放量阈值", 1.0, 5.0, 2.5)
    refresh_rate = st.slider("UI刷新频率(秒)", 2, 30, 5)
    
    raw_symbols = st.text_area("输入交易对 (逗号或换行隔开)", "BTC/USDT,ETH/USDT,SOL/USDT,ORDI/USDT")
    symbols = [s.strip().upper() for s in raw_symbols.replace('\n', ',').split(',') if s.strip()]

if st.button("🔥 启动实时监控", use_container_width=True):
    if not st.session_state.ws_active:
        start_ws_thread(symbols, timeframe)
        st.session_state.ws_active = True
        st.toast("WebSocket 已在后台启动")

# 数据展示区
placeholder = st.empty()

if st.session_state.ws_active:
    while True:
        df_display = compute_signals_vectorized(symbols, vol_mul)
        
        with placeholder.container():
            st.write(f"📊 正在监控 {len(st.session_state.data_store)}/{len(symbols)} 个交易对 | 更新时间: {time.strftime('%H:%M:%S')}")
            
            if not df_display.empty:
                # 信号高亮样式
                def highlight_signal(row):
                    return ['background-color: #4B0000' if row['警报'] == '⚠️' else '' for _ in row]
                
                st.dataframe(
                    df_display.style.apply(highlight_signal, axis=1),
                    use_container_width=True, 
                    height=600
                )
            else:
                st.info("正在补齐 WebSocket 数据，请稍候...")
        
        time.sleep(refresh_rate)
else:
    st.info("请在左侧配置交易对并点击启动按钮。")
