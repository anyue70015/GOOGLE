import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="2026 全球交易所直连监控", layout="wide")

# 定义支持的交易所列表及其初始化函数
SUPPORTED_EXCHANGES = {
    'OKX': ccxt.okx,
    'Gate.io': ccxt.gateio,
    'HTX': ccxt.htx,
    'Bitget': ccxt.bitget,
    'MEXC': ccxt.mexc,
    'KuCoin': ccxt.kucoin,
    'Bybit': ccxt.bybit,
    'CoinW': ccxt.coinw
}

# 状态记录器：记录哪些交易所连通，哪些失败
if 'status_log' not in st.session_state:
    st.session_state.status_log = {}

# ==========================================
# 2. 核心抓取逻辑 (带状态检测)
# ==========================================
def fetch_ex_data(ex_id, symbol, timeframes, big_val):
    try:
        # 初始化交易所对象
        ex_class = SUPPORTED_EXCHANGES[ex_id]
        ex = ex_class({'enableRateLimit': True, 'timeout': 10000})
        
        row_data = {"交易所": ex_id, "交易对": symbol}
        
        # 1. 抓取多周期 K 线
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
        
        # 更新状态：成功
        st.session_state.status_log[ex_id] = "✅ OK"
        return row_data
    
    except Exception as e:
        # 更新状态：失败
        st.session_state.status_log[ex_id] = f"❌ Error"
        return None

# ==========================================
# 3. UI 界面与控制台
# ==========================================
st.title("🛡️ 2026 全网大单实时扫描器 (聚合直连)")

with st.sidebar:
    st.header("⚙️ 监控配置")
    
    # 交易所多选（默认全选）
    selected_exs = st.multiselect(
        "选择监控交易所", 
        options=list(SUPPORTED_EXCHANGES.keys()),
        default=list(SUPPORTED_EXCHANGES.keys())
    )
    
    input_syms = st.text_area("监控币种 (USDT对, 如BTC,ETH)", "BTC,ETH,SOL,ORDI,SUI")
    symbols = [s.strip().upper() + "/USDT" for s in input_syms.replace('\n', ',').split(',') if s.strip()]
    
    big_val = st.number_input("大吃单阈值 (USDT)", value=20000, step=5000)
    refresh_rate = st.slider("刷新频率 (秒)", 5, 60, 10)

# 实时状态显示栏
if st.session_state.status_log:
    cols = st.columns(len(selected_exs))
    for i, ex_id in enumerate(selected_exs):
        status = st.session_state.status_log.get(ex_id, "⏳ 待连接")
        color = "green" if "OK" in status else "red" if "Error" in status else "gray"
        cols[i].markdown(f"**{ex_id}**: :{color}[{status}]")

# 主展示区
placeholder = st.empty()
timeframes = ['1m', '5m', '15m', '1h']

while True:
    if not selected_exs:
        st.warning("请在左侧至少选择一个交易所")
        break
        
    final_results = []
    
    # 并发抓取提高效率
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = []
        for ex_id in selected_exs:
            for sym in symbols:
                futures.append(executor.submit(fetch_ex_data, ex_id, sym, timeframes, big_val))
        
        for f in futures:
            res = f.result()
            if res: final_results.append(res)

    if final_results:
        df = pd.DataFrame(final_results)
        with placeholder.container():
            st.write(f"⏱️ 聚合刷新时间: {time.strftime('%H:%M:%S')}")
            
            def style_cells(val):
                if isinstance(val, str):
                    if '+' in val: return 'color: #00ff00; font-weight: bold'
                    if '-' in val: return 'color: #ff4b4b'
                return ''

            st.dataframe(
                df.style.applymap(style_cells, subset=[f"{tf} 涨幅" for tf in timeframes]),
                use_container_width=True,
                height=650
            )
    else:
        st.info("数据加载中或所有选定交易所暂不可达...")
    
    time.sleep(refresh_rate)
