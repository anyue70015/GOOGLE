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
st.set_page_config(page_title="2026量化神兵-终极稳定版", layout="wide")

if 'data_store' not in st.session_state:
    st.session_state.data_store = {}
if 'ws_active' not in st.session_state:
    st.session_state.ws_active = False

# ==========================================
# 2. 侧边栏：核心配置
# ==========================================
with st.sidebar:
    st.header("⚙️ 监控配置")
    
    # 允许自定义 Clash 端口
    proxy_port = st.text_input("Clash HTTP端口", value="7890")
    clash_proxy = f"http://127.0.0.1:{proxy_port}"
    
    # 注入环境变量（双保险）
    os.environ['http_proxy'] = clash_proxy
    os.environ['https_proxy'] = clash_proxy
    
    st.divider()
    
    timeframe = st.selectbox("K线周期", ["1m", "5m", "15m", "1h"], index=1)
    vol_mul = st.slider("放量阈值 (x)", 1.0, 5.0, 2.2)
    refresh_rate = st.slider("UI 刷新频率 (秒)", 2, 30, 5)
    
    raw_symbols = st.text_area("监控列表 (支持空格/逗号/换行)", 
                              "BTC/USDT,ETH/USDT,SOL/USDT,ORDI/USDT,SUI/USDT,TIA/USDT")
    symbols = [s.strip().upper() for s in raw_symbols.replace('\n', ',').replace(' ', ',').split(',') if s.strip()]
    
    if st.button("🧹 重置并清空缓存"):
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
        if df is None or len(df) < 22: # 确保至少有 22 根 K 线计算均量
            continue
        
        # 提取 NumPy 数组加速计算
        arr = df.to_numpy(dtype=np.float64)
        close_prices = arr[:, 4]
        open_prices = arr[:, 1]
        volumes = arr[:, 5]

        curr_c, prev_c = close_prices[-1], close_prices[-2]
        curr_o, curr_v = open_prices[-1], volumes[-1]
        
        # 向量化计算过去 20 根 K 线的平均成交量
        avg_v = np.mean(volumes[-21:-1])
        vol_ratio = curr_v / avg_v if avg_v > 0 else 0
        change_pct = ((curr_c - prev_c) / prev_c) * 100

        # 信号判定逻辑
        sig1 = (curr_c > curr_o) and (vol_ratio > vol_multiplier) # 阳线 + 爆量
        sig2 = (vol_ratio > 1.3) and (change_pct > 0.7)          # 动能突发
        
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
# 4. 混合数据抓取线程 (REST + WS)
# ==========================================
async def market_worker(symbols, timeframe, proxy_url):
    # 强力代理注入配置
    exchange = ccxt_pro.binance({
        'enableRateLimit': True,
        'proxy': proxy_url,
        'http_proxy': proxy_url,
        'https_proxy': proxy_url,
        'options': {'defaultType': 'spot'}
    })

    async def single_symbol_handler(symbol):
        # --- A: 强制冷启动 (解决卡死关键) ---
        retry_count = 0
        while retry_count < 3:
            try:
                # 瞬间抓取历史数据填充缓存
                history = await exchange.fetch_ohlcv(symbol, timeframe, limit=60)
                if history:
                    st.session_state.data_store[symbol] = pd.DataFrame(
                        history, columns=['t', 'o', 'h', 'l', 'c', 'v']
                    )
                    break
            except Exception as e:
                retry_count += 1
                print(f"[{symbol}] 历史抓取重试 {retry_count}: {e}")
                await asyncio.sleep(2)

        # --- B: WebSocket 实时接管 ---
        while True:
            try:
                ohlcv = await exchange.watch_ohlcv(symbol, timeframe, limit=100)
                if ohlcv:
                    st.session_state.data_store[symbol] = pd.DataFrame(
                        ohlcv, columns=['t', 'o', 'h', 'l', 'c', 'v']
                    )
            except Exception as e:
                # 遇到连接波动，静默重连
                await asyncio.sleep(10)

    # 并发执行
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
st.title("🚀 2026 混合动力扫描器")

if st.button("🔥 启动实时监控", use_container_width=True):
    if not st.session_state.ws_active:
        start_background_loop(symbols, timeframe, clash_proxy)
        st.session_state.ws_active = True
        st.toast(f"正在通过端口 {proxy_port} 建立连接...")

# 状态面板
placeholder = st.empty()

if st.session_state.ws_active:
    # 检查连接是否真的获取到了数据
    while True:
        df_display = compute_signals_vectorized(symbols, vol_mul)
        
        with placeholder.container():
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"📊 监控规模: {len(st.session_state.data_store)}/{len(symbols)} 币种")
            with col2:
                st.write(f"⏱️ 刷新: {time.strftime('%H:%M:%S')}")
            
            if not df_display.empty:
                # 信号样式美化
                def highlight_row(row):
                    if row['警报'] == '⚠️':
                        return ['background-color: rgba(255, 75, 75, 0.15); color: #FF4B4B; font-weight: bold'] * len(row)
                    return [''] * len(row)
                
                st.dataframe(
                    df_display.style.apply(highlight_row, axis=1),
                    use_container_width=True, 
                    height=750
                )
            else:
                st.info("💡 正在尝试穿透代理并同步历史 K 线，请观察 5-10 秒...")
                # 调试提示：如果超过 20 秒还是这样，通常是代理端口不对或节点不支持
                if len(st.session_state.data_store) == 0:
                    st.warning("⚠️ 检测到连接延迟。请确保 Clash 开启了 **TUN 模式** 或端口 **7890** 已放行 HTTP 流量。")
        
        time.sleep(refresh_rate)
else:
    st.info("👈 请在左侧配置交易对和端口，然后点击启动按钮。")
