import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="资金预警-云端稳定版", layout="wide")

# 修复 Streamlit Cloud 上的 Key 丢失问题
if 'signal_memory' not in st.session_state:
    st.session_state.signal_memory = {}

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "SUI", "XRP", "RENDER", "TAO", "HYPE", "UNI", "ZEC"] # 建议先减少币种测试稳定性
EXCHANGE_IDS = {'OKX': 'okx', 'Gate': 'gateio', 'Bitget': 'bitget'} # 剔除响应慢的交易所

# ==========================================
# 2. 核心逻辑：数据与 UI 分离
# ==========================================
def safe_fetch(symbol, threshold):
    """纯数据函数，不包含任何 st. 语句"""
    pair = f"{symbol}/USDT"
    data = {
        "币种": symbol, "最新价": "NO", "OBV预警": "正常", 
        "1m涨跌": 0.0, "1h涨跌": 0.0, "active_count": 0, "net_flow": 0,
        "OKX": "NO", "Gate": "NO", "Bitget": "NO"
    }
    
    try:
        # 1. 行情抓取
        ex = ccxt.okx({'timeout': 5000, 'enableRateLimit': True})
        # 只取必要的周期
        for tf in ['1m', '1h']:
            ohlcv = ex.fetch_ohlcv(pair, tf, limit=2)
            if ohlcv: data[f"{tf}涨跌"] = ((ohlcv[-1][4] - ohlcv[-1][1]) / ohlcv[-1][1]) * 100
        data["最新价"] = ex.fetch_ticker(pair)['last']
        
        # 2. 大单扫描 (仅核心交易所)
        for name in ['OKX', 'Gate']:
            try:
                ex_obj = getattr(ccxt, EXCHANGE_IDS[name])({'timeout': 3000})
                trades = ex_obj.fetch_trades(pair, limit=20)
                buy_vol = 0
                for t in trades:
                    val = t['price'] * t['amount']
                    data['net_flow'] += val if t['side'] == 'buy' else -val
                    if t['side'] == 'buy' and val >= threshold: buy_vol += val
                if buy_vol > 0:
                    data['active_count'] += 1
                    data[name] = f"{buy_vol/10000:.1f}万"
            except: continue
            
        # 3. 计算背离
        if data['1h涨跌'] < -0.5 and data['net_flow'] > 0: data['OBV预警'] = "💎底背离"
    except:
        pass
    return data

# ==========================================
# 3. 主界面
# ==========================================
st.title("🏹 渐进式监控指挥部")

with st.sidebar:
    big_val = st.number_input("大单阈值", value=20000)
    interval = st.slider("间隔", 10, 60, 30)

placeholder = st.empty()

while True:
    # --- 执行并发抓取 ---
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(lambda s: safe_fetch(s, big_val), SYMBOLS))
    
    curr_t = time.time()
    
    # --- 在主线程处理 Session State 和 UI ---
    for r in results:
        sym = r['币种']
        if sym not in st.session_state.signal_memory:
            st.session_state.signal_memory[sym] = {"level": 0, "time": 0}
            
        lvl = 0
        if r['1m涨跌'] >= 0.5:
            lvl = 1
            if r['active_count'] >= 2: lvl = 2
        
        if lvl > 0:
            st.session_state.signal_memory[sym] = {"level": lvl, "time": curr_t}
        
        r['预警等级'] = st.session_state.signal_memory[sym]['level'] if curr_t - st.session_state.signal_memory[sym]['time'] < 900 else 0

    # --- 渲染 ---
    df = pd.DataFrame(results)
    df['1m涨跌'] = df['1m涨跌'].apply(lambda x: f"{x:+.2f}%")
    
    with placeholder.container():
        st.write(f"🔄 上次更新: {time.strftime('%H:%M:%S')}")
        
        def row_style(row):
            if row['预警等级'] == 2: return ['background-color: #FFD700'] * len(row)
            if "底背离" in str(row['OBV预警']): return ['background-color: #E6F3FF'] * len(row)
            return [''] * len(row)

        st.dataframe(df.style.apply(row_style, axis=1), use_container_width=True)

    time.sleep(interval)

