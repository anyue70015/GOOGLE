import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 初始化 (安全加载交易所)
# ==========================================
st.set_page_config(page_title="2026 全球直连监控-究极版", layout="wide")

def get_exchange_map():
    target_ids = {
        'OKX': 'okx', 'Gate.io': 'gateio', 'HTX': 'htx', 
        'Bitget': 'bitget', 'MEXC': 'mexc', 'KuCoin': 'kucoin', 'Bybit': 'bybit'
    }
    available = {}
    for name, _id in target_ids.items():
        if hasattr(ccxt, _id):
            available[name] = getattr(ccxt, _id)
    return available

SUPPORTED_EXCHANGES = get_exchange_map()

# 初始化状态记录 (主线程专用)
if 'status_log' not in st.session_state:
    st.session_state.status_log = {name: "⏳ 准备中" for name in SUPPORTED_EXCHANGES.keys()}

# ==========================================
# 2. 核心数据抓取 (子线程严禁访问 st)
# ==========================================
def fetch_worker(ex_name, symbol, timeframes, big_val):
    try:
        ex_class = SUPPORTED_EXCHANGES[ex_name]
        # 直连优化：国内环境建议 timeout 稍长
        ex = ex_class({'enableRateLimit': True, 'timeout': 15000})
        
        row_data = {"交易所": ex_name, "交易对": symbol}
        
        # 1. 抓取多周期涨幅 (1, 5, 15, 60分钟)
        for tf in timeframes:
            # 统一转换周期标识
            api_tf = '1h' if tf == '60m' else tf 
            ohlcv = ex.fetch_ohlcv(symbol, api_tf, limit=2)
            if len(ohlcv) >= 2:
                # 涨幅 = (现价 - 周期开盘价) / 周期开盘价
                change = ((ohlcv[-1][4] - ohlcv[-1][1]) / ohlcv[-1][1]) * 100
                row_data[f"{tf}涨幅"] = f"{change:+.2f}%"
            else:
                row_data[f"{tf}涨幅"] = "0.00%"
        
        # 2. 探测大吃单
        trades = ex.fetch_trades(symbol, limit=20)
        # 筛选单笔买入金额 > 阈值
        big_buys = [t for t in trades if t['side'] == 'buy' and (t['price'] * t['amount']) >= big_val]
        row_data["大单警报"] = "🔥" * min(len(big_buys), 5) if big_buys else ""
        row_data["最新价"] = trades[-1]['price'] if trades else "N/A"
        
        return row_data, "✅ OK"
    except Exception as e:
        return None, "❌ 连接失败"

# ==========================================
# 3. 界面逻辑
# ==========================================
st.title("🛡️ 2026 全球多交易所聚合监控")

with st.sidebar:
    st.header("⚙️ 监控配置")
    selected_exs = st.multiselect("交易所", options=list(SUPPORTED_EXCHANGES.keys()), default=['OKX', 'Gate.io', 'HTX'])
    input_syms = st.text_area("币种", "BTC,ETH,SOL,ORDI")
    symbols = [s.strip().upper() + "/USDT" for s in input_syms.replace('\n', ',').split(',') if s.strip()]
    big_val = st.number_input("大单定义(USDT)", value=20000)
    refresh_rate = st.slider("刷新率(秒)", 5, 60, 10)

# 显示状态栏
status_cols = st.columns(len(selected_exs))
for i, name in enumerate(selected_exs):
    status = st.session_state.status_log.get(name, "⏳")
    status_cols[i].metric(name, status)

placeholder = st.empty()
tfs = ['1m', '5m', '15m', '60m']

# 主循环
while True:
    if not selected_exs:
        st.warning("👈 请在侧边栏选择交易所")
        break
    
    final_results = []
    # 并发抓取
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_worker, ex, sym, tfs, big_val): ex 
                   for ex in selected_exs for sym in symbols}
        
        for f in futures:
            ex_name = futures[f]
            try:
                res, status = f.result()
                st.session_state.status_log[ex_name] = status # 在主线程更新状态
                if res: final_results.append(res)
            except:
                st.session_state.status_log[ex_name] = "❌ 系统错误"

    if final_results:
        df = pd.DataFrame(final_results)
        with placeholder.container():
            st.write(f"📊 聚合数据点: {len(df)} | 更新: {time.strftime('%H:%M:%S')}")
            
            # 上色逻辑
            def style_df(val):
                if isinstance(val, str) and '+' in val: return 'color: #00ff00; font-weight: bold'
                if isinstance(val, str) and '-' in val: return 'color: #ff4b4b'
                return ''

            st.dataframe(
                df.style.applymap(style_df, subset=[f"{tf}涨幅" for tf in tfs]),
                use_container_width=True, height=600
            )
    
    time.sleep(refresh_rate)
