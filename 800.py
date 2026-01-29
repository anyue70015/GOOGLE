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
# 1. 页面配置
# ==========================================
st.set_page_config(page_title="2026量化神兵-极速版", layout="wide")

if 'data_store' not in st.session_state:
    st.session_state.data_store = {}
if 'ws_active' not in st.session_state:
    st.session_state.ws_active = False

# ==========================================
# 2. 侧边栏：配置中心 (包含端口选择)
# ==========================================
with st.sidebar:
    st.header("⚙️ 配置中心")
    
    # 代理设置
    proxy_port = st.text_input("Clash 端口", value="7890")
    clash_proxy = f"http://127.0.0.1:{proxy_port}"
    
    # 环境检测：设置系统环境变量，确保 CCXT 内部请求识别代理
    os.environ['http_proxy'] = clash_proxy
    os.environ['https_proxy'] = clash_proxy
    
    st.divider()
    
    timeframe = st.selectbox("K线周期", ["1m", "5m", "15m", "1h"], index=1)
    vol_mul = st.slider("放量阈值 (x)", 1.0, 5.0, 2.2)
    refresh_rate = st.slider("UI 刷新频率 (秒)", 2, 30, 5)
    
    raw_symbols = st.text_area("监控列表 (空格/逗号/换行隔开)", 
                              "BTC/USDT,ETH/USDT,SOL/USDT,ORDI/USDT,SUI/USDT,TIA/USDT")
    symbols = [s.strip().upper() for s in raw_symbols.replace('\n', ',').replace(' ', ',').split(',') if s.strip()]
    
    if st.button("🧹 清空缓存并重启"):
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
        # 必须至少有 22 根 K 线才能计算 20 周期均量
        if df is None or len(df) < 22:
            continue
        
        arr = df.to_numpy(dtype=np.float64)
        close_prices = arr[:, 4]
        open_prices = arr[:, 1]
        volumes = arr[:, 5]

        curr_c, prev_c = close_prices[-1], close_prices[-2]
        curr_o, curr_v = open_prices[-1], volumes[-1]
        
        # 向量化计算均量 (过去 20 根)
        avg_v = np.mean(volumes[-21:-1])
        vol_ratio = curr_v / avg_v if avg_v > 0 else 0
        change_pct = ((curr_c - prev_c) / prev_c) * 100

        # 信号定义
        sig1 = (curr_c > curr_o) and (vol_ratio > vol_multiplier) # 阳线放量
        sig2 = (vol_ratio > 1.2) and (change_pct > 0.6)          # 动能突发
        
        active_sigs = [str(i) for i, s in enumerate([sig1, sig2], 1) if s]
        
        processed_data.append({
            "交易对": symbol,
            "现价": f"{curr_c:.4f}",
            "单根涨跌": f"{change_pct:+.2f}%",
            "放量比": f"{vol_ratio:.2f}x",
            "信号": ",".join(active_sigs),
            "警报": "⚠️" if active_sigs else "",
            "sort_key": vol_ratio
        })

    if not processed_data: return pd.DataFrame()
    
    res_df = pd.DataFrame(processed_data)
    return res_df.sort_values("sort_key", ascending=False).drop(columns=["sort_key"])

# ==========================================
# 4. 后台 WS + REST 混合抓取线程
# ==========================================
async def market_worker(symbols, timeframe, proxy_url):
    exchange = ccxt_pro.binance({
        'enableRateLimit': True,
        'proxies': {'http': proxy_url, 'https': proxy_url},
        'options': {'defaultType': 'spot'}
    })

    async def single_symbol_handler(symbol):
        # --- 步骤 A: REST 快速冷启动 ---
        try:
            # 瞬间抓取 60 根历史 K 线，让 UI 不用等待
            history = await exchange.fetch_ohlcv(symbol, timeframe, limit=60)
            if history:
                st.session_state.data_store[symbol] = pd.DataFrame(
                    history, columns=['t', 'o', 'h', 'l', 'c', 'v']
                )
        except Exception as e:
            print(f"REST 抓取异常 {symbol}: {e}")

        # --- 步骤 B: WebSocket 持续接管 ---
        while True:
            try:
                # watch_ohlcv 会在有新成交时自动更新
                ohlcv = await exchange.watch_ohlcv(symbol, timeframe, limit=100)
                df = pd.DataFrame(ohlcv, columns=['t', 'o', 'h', 'l', 'c', 'v'])
                st.session_state.data_store[symbol] = df
            except Exception as e:
                # 遇到报错（如网络波动）静默等待 10 秒重连
                await asyncio.sleep(10)

    # 并行处理所有币种
    tasks = [single_symbol_handler(s) for s in symbols]
    await asyncio.gather(*tasks)

def start_background_loop(symbols, timeframe, proxy_url):
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_until_complete, 
                         args=(market_worker(symbols, timeframe, proxy_url),))
    add_script_run_ctx(t) 
    t.daemon = True
    t.start()

# ==========================================
# 5. 主界面逻辑
# ==========================================
st.title("🚀 2026 极速量化扫描器 (混合动力版)")

if st.button("🔥 开启实时监控", use_container_width=True):
    if not st.session_state.ws_active:
        start_background_loop(symbols, timeframe, clash_proxy)
        st.session_state.ws_active = True
        st.toast(f"已连接 Clash 端口 {proxy_port}，正在秒速补齐数据...")

placeholder = st.empty()

if st.session_state.ws_active:
    # 模拟 UI 实时刷新循环
    while True:
        df_display = compute_signals_vectorized(symbols, vol_mul)
        
        with placeholder.container():
            st.write(f"📊 监控中: {len(st.session_state.data_store)}/{len(symbols)} | 周期: {timeframe} | 刷新: {time.strftime('%H:%M:%S')}")
            
            if not df_display.empty:
                # 信号高亮
                def highlight_alert(row):
                    return ['background-color: rgba(255, 0, 0, 0.2); color: white;' if row['警报'] == '⚠️' else '' for _ in row]
                
                st.dataframe(
                    df_display.style.apply(highlight_alert, axis=1),
                    use_container_width=True, 
                    height=700
                )
            else:
                st.info("数据抓取中，请稍候 1-2 秒...")
        
        time.sleep(refresh_rate)
else:
    st.warning("👈 请先在左侧侧边栏确认交易对和端口，然后点击『开启实时监控』")
