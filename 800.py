import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="2026 全球交易所实时监控", layout="wide")

# 动态获取可用的交易所类，防止 AttributeError
def get_safe_exchanges():
    # 核心监控列表 (删除了不稳定的 CoinW)
    target_ids = {
        'OKX': 'okx',
        'Gate.io': 'gateio',
        'HTX': 'htx',
        'Bitget': 'bitget',
        'MEXC': 'mexc',
        'KuCoin': 'kucoin',
        'Bybit': 'bybit'
    }
    available = {}
    for name, _id in target_ids.items():
        if hasattr(ccxt, _id):
            available[name] = getattr(ccxt, _id)
    return available

SUPPORTED_EXCHANGES = get_safe_exchanges()

# 初始化状态记录
if 'status_log' not in st.session_state:
    st.session_state.status_log = {}

# ==========================================
# 2. 核心数据抓取逻辑
# ==========================================
def fetch_ex_data(ex_name, symbol, timeframes, big_val):
    try:
        ex_class = SUPPORTED_EXCHANGES[ex_name]
        # 设置超时为 10 秒，防止垃圾节点卡死整体进度
        ex = ex_class({'enableRateLimit': True, 'timeout': 10000})
        
        row_data = {"交易所": ex_name, "交易对": symbol}
        
        # 1. 抓取多周期涨幅 (1m, 5m, 15m, 1h)
        for tf in timeframes:
            ohlcv = ex.fetch_ohlcv(symbol, tf, limit=2)
            if len(ohlcv) >= 2:
                change = ((ohlcv[-1][4] - ohlcv[-1][1]) / ohlcv[-1][1]) * 100
                row_data[f"{tf} 涨幅"] = f"{change:+.2f}%"
            else:
                row_data[f"{tf} 涨幅"] = "0.00%"
        
        # 2. 探测大吃单
        trades = ex.fetch_trades(symbol, limit=20)
        big_buys = [t for t in trades if t['side'] == 'buy' and (t['price'] * t['amount']) >= big_val]
        row_data["大单警报"] = "🔥" * min(len(big_buys), 5) if big_buys else ""
        row_data["最新价"] = trades[-1]['price'] if trades else "N/A"
        
        st.session_state.status_log[ex_name] = "✅ OK"
        return row_data
    
    except Exception as e:
        st.session_state.status_log[ex_name] = "❌ 网络/IP受限"
        return None

# ==========================================
# 3. UI 界面渲染
# ==========================================
st.title("🛡️ 2026 全网大单实时扫描器")

with st.sidebar:
    st.header("⚙️ 监控设置")
    
    # 动态生成可选列表
    selected_exs = st.multiselect(
        "选择监控交易所", 
        options=list(SUPPORTED_EXCHANGES.keys()),
        default=list(SUPPORTED_EXCHANGES.keys())
    )
    
    input_syms = st.text_area("监控币种 (如 BTC,ETH,SOL)", "BTC,ETH,SOL,ORDI,SUI")
    symbols = [s.strip().upper() + "/USDT" for s in input_syms.replace('\n', ',').split(',') if s.strip()]
    
    big_val = st.number_input("大吃单阈值 (USDT)", value=20000)
    refresh_rate = st.slider("刷新频率 (秒)", 5, 60, 10)

# 显示各交易所连通状态
if selected_exs:
    status_cols = st.columns(len(selected_exs))
    for i, ex_name in enumerate(selected_exs):
        stat = st.session_state.status_log.get(ex_name, "⏳ 等待数据")
        color = "green" if "OK" in stat else "red" if "❌" in stat else "gray"
        status_cols[i].markdown(f"**{ex_name}**\n:{color}[{stat}]")

placeholder = st.empty()
timeframes = ['1m', '5m', '15m', '1h']

while True:
    if not selected_exs:
        st.warning("请至少选择一个交易所进行监控")
        break
        
    final_results = []
    
    # 使用 ThreadPoolExecutor 并发请求，极大提升刷新速度
    with ThreadPoolExecutor(max_workers=len(selected_exs) * 2) as executor:
        futures = []
        for ex_name in selected_exs:
            for sym in symbols:
                futures.append(executor.submit(fetch_ex_data, ex_name, sym, timeframes, big_val))
        
        for f in futures:
            res = f.result()
            if res: final_results.append(res)

    if final_results:
        df = pd.DataFrame(final_results)
        with placeholder.container():
            st.write(f"⏱️ 全网同步时间: {time.strftime('%H:%M:%S')}")
            
            # 文字上色函数
            def color_text(val):
                if isinstance(val, str):
                    if '+' in val: return 'color: #00ff00; font-weight: bold'
                    if '-' in val: return 'color: #ff4b4b'
                return ''

            st.dataframe(
                df.style.applymap(color_text, subset=[f"{tf} 涨幅" for tf in timeframes]),
                use_container_width=True,
                height=600
            )
    
    time.sleep(refresh_rate)
