import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="资金预警指挥部-修复版", layout="wide")

st.markdown("""
    <style>
    .stDataFrame { opacity: 1.0 !important; }
    .stApp { background-color: white; }
    </style>
    """, unsafe_allow_html=True)

# 确保包含你要看的全部币种
SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "ZEC"]

if 'signal_memory' not in st.session_state:
    st.session_state.signal_memory = {}

# ==========================================
# 2. 数据抓取（确保周期完整）
# ==========================================
def fetch_worker(symbol, threshold):
    pair = f"{symbol}/USDT"
    res = {
        "币种": symbol, "最新价": "NO", "OBV预警": "正常", 
        "OKX": "NO", "Gate": "NO", "Bitget": "NO",
        "net_flow": 0, "active_count": 0
    }
    # 预设所有周期为 NO
    tfs_map = {'1m': '1m涨跌', '15m': '15m涨跌', '1h': '1h涨跌', '4h': '4h涨跌', '1d': '24h涨跌', '1w': '7d涨跌'}
    for col in tfs_map.values(): res[col] = 0.0

    try:
        ex = ccxt.okx({'timeout': 3000})
        # 抓取所有请求的周期
        for tf, col_name in tfs_map.items():
            try:
                ohlcv = ex.fetch_ohlcv(pair, tf, limit=2)
                if len(ohlcv) >= 2:
                    res[col_name] = ((ohlcv[-1][4] - ohlcv[-1][1]) / ohlcv[-1][1]) * 100
            except: continue
        res["最新价"] = ex.fetch_ticker(pair)['last']
        
        # 大单扫描
        ex_gate = ccxt.gateio({'timeout': 2000})
        trades = ex_gate.fetch_trades(pair, limit=30)
        buy_sum = 0
        for t in trades:
            val = t['price'] * t['amount']
            res['net_flow'] += val if t['side'] == 'buy' else -val
            if t['side'] == 'buy' and val >= threshold: buy_sum += val
        if buy_sum > 0:
            res['active_count'] += 1
            res['Gate'] = f"{buy_sum/10000:.1f}万"
            
        # OBV背离判断
        if res['1h涨跌'] < -0.5 and res['net_flow'] > 0:
            res['OBV预警'] = "💎底背离"
    except: pass
    return res

# ==========================================
# 3. 主界面渲染
# ==========================================
st.title("🏹 资金预警指挥部 (全周期修复版)")

with st.sidebar:
    big_val = st.number_input("大单阈值", value=20000)
    interval = st.slider("扫描间隔", 10, 60, 30)

placeholder = st.empty()

while True:
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        results = list(executor.map(lambda s: fetch_worker(s, big_val), SYMBOLS))
    
    curr_t = time.time()
    for r in results:
        sym = r['币种']
        if sym not in st.session_state.signal_memory:
            st.session_state.signal_memory[sym] = {"level": 0, "time": 0}
        
        lvl = 0
        if isinstance(r['1m涨跌'], float) and r['1m涨跌'] >= 0.5:
            lvl = 1
            if r['active_count'] >= 1: lvl = 2
        
        if lvl > 0:
            st.session_state.signal_memory[sym] = {"level": lvl, "time": curr_t}
        r['预警等级'] = st.session_state.signal_memory[sym]['level'] if curr_t - st.session_state.signal_memory[sym]['time'] < 900 else 0

    # 渲染 DataFrame
    df = pd.DataFrame(results)
    
    # 格式化百分比显示
    ch_cols = ['1m涨跌', '15m涨跌', '1h涨跌', '4h涨跌', '24h涨跌', '7d涨跌']
    for col in ch_cols:
        df[col] = df[col].apply(lambda x: f"{x:+.2f}%" if isinstance(x, float) else x)

    with placeholder.container():
        st.write(f"🔄 更新: {time.strftime('%H:%M:%S')}")
        
        def row_style(row):
            if row['预警等级'] >= 2: return ['background-color: #FFD700; color: black'] * len(row)
            if "底背离" in str(row['OBV预警']): return ['background-color: #E6F3FF; color: black'] * len(row)
            return [''] * len(row)

        # 这里的 cols 顺序决定了你看到的格子
        cols = ["币种", "最新价", "OBV预警"] + ch_cols + ["Gate", "OKX", "预警等级"]
        
        # 💡 关键修复：height=800 确保容纳 20 行以上
        st.dataframe(
            df[cols].style.apply(row_style, axis=1),
            use_container_width=True, 
            height=800  
        )

    time.sleep(interval)
