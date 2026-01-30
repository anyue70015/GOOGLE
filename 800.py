import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="四大交易所资金指挥部", layout="wide")

st.markdown("""
    <style>
    .stDataFrame { opacity: 1.0 !important; }
    .stApp { background-color: white; }
    </style>
    """, unsafe_allow_html=True)

# 币种池
SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "ZEC"]
# 交易所映射
EXCHANGE_IDS = {'OKX': 'okx', 'Gate': 'gateio', 'Huobi': 'htx', 'Bitget': 'bitget'}

if 'signal_memory' not in st.session_state:
    st.session_state.signal_memory = {}

# ==========================================
# 2. 核心抓取引擎 (四大交易所联控)
# ==========================================
def fetch_worker(symbol, threshold):
    pair = f"{symbol}/USDT"
    res = {
        "币种": symbol, "最新价": "NO", "OBV预警": "正常", 
        "OKX": "NO", "Gate": "NO", "Huobi": "NO", "Bitget": "NO",
        "net_flow": 0, "active_count": 0
    }
    tfs_map = {'1m': '1m涨跌', '15m': '15m涨跌', '1h': '1h涨跌', '4h': '4h涨跌', '1d': '24h涨跌', '1w': '7d涨跌'}
    # 初始值设定
    for col in tfs_map.values(): res[col] = -999.0 

    try:
        # 使用 OKX 作为主行情源 (103,500 左右高位震荡行情)
        ex_main = ccxt.okx({'timeout': 3000})
        for tf, col_name in tfs_map.items():
            try:
                ohlcv = ex_main.fetch_ohlcv(pair, tf, limit=2)
                if len(ohlcv) >= 2:
                    res[col_name] = ((ohlcv[-1][4] - ohlcv[-1][1]) / ohlcv[-1][1]) * 100
            except: continue
        res["最新价"] = ex_main.fetch_ticker(pair)['last']
        
        # 遍历四大交易所抓取大单
        for name, eid in EXCHANGE_IDS.items():
            try:
                ex_obj = getattr(ccxt, eid)({'timeout': 2000})
                trades = ex_obj.fetch_trades(pair, limit=30)
                exchange_buy = 0
                for t in trades:
                    val = t['price'] * t['amount']
                    side_sign = 1 if t['side'] == 'buy' else -1
                    res['net_flow'] += val * side_sign
                    if t['side'] == 'buy' and val >= threshold:
                        exchange_buy += val
                if exchange_buy > 0:
                    res['active_count'] += 1
                    res[name] = f"{exchange_buy/10000:.1f}万"
            except: 
                res[name] = "NO"

        # OBV背离逻辑
        if isinstance(res['1h涨跌'], float) and res['1h涨跌'] < -0.5 and res['net_flow'] > 0:
            res['OBV预警'] = "💎底背离"
            
    except: pass
    return res

# ==========================================
# 3. UI 渲染与倒计时
# ==========================================
st.title("🏹 渐进式监控指挥部 (四大交易所联控版)")

with st.sidebar:
    st.header("⚙️ 参数控制")
    big_val = st.number_input("大单阈值 (USDT)", value=20000)
    interval = st.slider("扫描间隔 (秒)", 10, 120, 30)
    st.write("---")
    countdown_placeholder = st.empty()

placeholder = st.empty()

while True:
    # --- 执行并发抓取 ---
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        results = list(executor.map(lambda s: fetch_worker(s, big_val), SYMBOLS))
    
    curr_t = time.time()
    for r in results:
        sym = r['币种']
        if sym not in st.session_state.signal_memory:
            st.session_state.signal_memory[sym] = {"level": 0, "time": 0}
        
        lvl = 0
        raw_1m = r.get('1m涨跌', -999.0)
        if isinstance(raw_1m, float) and raw_1m >= 0.5:
            lvl = 1
            if r['active_count'] >= 2: lvl = 2
            if r['active_count'] >= 3: lvl = 3 # 三个以上交易所同时有大单
        
        # 底背离加权
        if "底背离" in r['OBV预警']: lvl = max(lvl, 2)
        
        if lvl > 0:
            st.session_state.signal_memory[sym] = {"level": lvl, "time": curr_t}
        r['预警等级'] = st.session_state.signal_memory[sym]['level'] if curr_t - st.session_state.signal_memory[sym]['time'] < 900 else 0

    # --- 排序与显示 ---
    df = pd.DataFrame(results).sort_values(by="1m涨跌", ascending=False)
    
    # 格式化
    ch_cols = ['1m涨跌', '15m涨跌', '1h涨跌', '4h涨跌', '24h涨跌', '7d涨跌']
    display_df = df.copy()
    for col in ch_cols:
        display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%" if x != -999.0 else "NO")

    with placeholder.container():
        st.write(f"🔄 更新: {time.strftime('%H:%M:%S')} | 动态排序已开启")
        
        def row_style(row):
            if row['预警等级'] == 3: return ['background-color: #FF4500; color: white'] * len(row) # 顶级预警
            if row['预警等级'] == 2: return ['background-color: #FFD700; color: black'] * len(row)
            if "底背离" in str(row['OBV预警']): return ['background-color: #E6F3FF; color: black'] * len(row)
            return [''] * len(row)

        # 包含四大交易所的显示列
        cols = ["币种", "最新价", "OBV预警"] + ch_cols + ["OKX", "Gate", "Huobi", "Bitget", "预警等级"]
        st.dataframe(
            display_df[cols].style.apply(row_style, axis=1),
            use_container_width=True, 
            height=800  
        )

    # --- 倒计时 ---
    for i in range(interval, 0, -1):
        countdown_placeholder.metric("下次刷新倒计时", f"{i} 秒")
        time.sleep(1)
