import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="资金指挥部-稳定版", layout="wide")

st.markdown("""
    <style>
    .stDataFrame { opacity: 1.0 !important; }
    .stApp { background-color: white; }
    </style>
    """, unsafe_allow_html=True)

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX"]
EXCHANGE_IDS = {'OKX': 'okx', 'Gate': 'gateio', 'Huobi': 'htx', 'Bitget': 'bitget'}

# 在主线程初始化
if 'last_valid_data' not in st.session_state:
    st.session_state.last_valid_data = {}
if 'signal_memory' not in st.session_state:
    st.session_state.signal_memory = {}

# ==========================================
# 2. 线程安全抓取引擎 (不访问 session_state)
# ==========================================
def fetch_worker(symbol, threshold, history_cache):
    pair = f"{symbol}/USDT"
    
    # 使用从主线程传进来的缓存参数，若无则初始化
    res = history_cache if history_cache else {
        "币种": symbol, "最新价": "NO", "OBV预警": "正常", 
        "OKX": "·", "Gate": "·", "Huobi": "·", "Bitget": "·",
        "1m涨跌": -999.0, "15m涨跌": -999.0, "1h涨跌": -999.0, 
        "4h涨跌": -999.0, "24h涨跌": -999.0, "7d涨跌": -999.0,
        "net_flow": 0, "active_count": 0
    }

    # 行情优先级逻辑：OKX > Gate
    priority_list = ['OKX', 'Gate']
    tfs_map = {'1m': '1m涨跌', '15m': '15m涨跌', '1h': '1h涨跌', '4h': '4h涨跌', '1d': '24h涨跌', '1w': '7d涨跌'}
    
    success_flag = False
    for ex_id in priority_list:
        if success_flag: break
        try:
            ex_obj = getattr(ccxt, EXCHANGE_IDS[ex_id])({'timeout': 3000, 'enableRateLimit': True})
            ticker = ex_obj.fetch_ticker(pair)
            res["最新价"] = ticker['last']
            
            for tf, col_name in tfs_map.items():
                ohlcv = ex_obj.fetch_ohlcv(pair, tf, limit=2)
                if len(ohlcv) >= 2:
                    res[col_name] = ((ohlcv[-1][4] - ohlcv[-1][1]) / ohlcv[-1][1]) * 100
            success_flag = True
        except:
            continue

    # 扫描四大所大单流向
    res['active_count'] = 0
    res['net_flow'] = 0
    for name, eid in EXCHANGE_IDS.items():
        try:
            ex_trade = getattr(ccxt, eid)({'timeout': 1500, 'enableRateLimit': True})
            trades = ex_trade.fetch_trades(pair, limit=20)
            buy_sum = 0
            for t in trades:
                val = t['price'] * t['amount']
                res['net_flow'] += val if t['side'] == 'buy' else -val
                if t['side'] == 'buy' and val >= threshold: buy_sum += val
            
            if buy_sum > 0:
                res['active_count'] += 1
                res[name] = f"{buy_sum/10000:.1f}万"
            else:
                res[name] = "·"
        except:
            res[name] = "NO"

    # 背离逻辑
    if isinstance(res.get('1h涨跌'), float) and res['1h涨跌'] < -0.5 and res['net_flow'] > 0:
        res['OBV预警'] = "💎底背离"
    else:
        res['OBV预警'] = "正常"

    return res

# ==========================================
# 3. 渲染主循环
# ==========================================
st.title("🏹 资金指挥部 (线程安全稳定版)")

with st.sidebar:
    st.header("⚙️ 控制面板")
    big_val = st.number_input("大单阈值 (USDT)", value=20000)
    interval = st.slider("扫描间隔 (秒)", 10, 60, 30)
    countdown_area = st.empty()

placeholder = st.empty()

while True:
    # --- 关键修复：在主线程提取缓存，通过传参进入子线程 ---
    current_cache = {s: st.session_state.last_valid_data.get(s) for s in SYMBOLS}
    
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        # 将当前币种的缓存作为第三个参数传递给 fetch_worker
        results = list(executor.map(lambda s: fetch_worker(s, big_val, current_cache[s]), SYMBOLS))
    
    now = time.time()
    # 所有对 session_state 的修改均回到主线程执行
    for r in results:
        sym = r['币种']
        st.session_state.last_valid_data[sym] = r 
        
        if sym not in st.session_state.signal_memory:
            st.session_state.signal_memory[sym] = {"level": 0, "time": 0}
        
        lvl = 0
        if isinstance(r.get('1m涨跌'), float) and r['1m涨跌'] >= 0.5:
            lvl = 1
            if r['active_count'] >= 2: lvl = 2
        if "底背离" in r['OBV预警']: lvl = max(lvl, 2)
        
        if lvl > 0:
            st.session_state.signal_memory[sym] = {"level": lvl, "time": now}
        
        # 15分钟有效预警
        r['预警等级'] = st.session_state.signal_memory[sym]['level'] if now - st.session_state.signal_memory[sym]['time'] < 900 else 0

    # --- 动态排序与显示 ---
    df = pd.DataFrame(results).sort_values(by="1m涨跌", ascending=False)
    
    ch_cols = ['1m涨跌', '15m涨跌', '1h涨跌', '4h涨跌', '24h涨跌', '7d涨跌']
    display_df = df.copy()
    for col in ch_cols:
        display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%" if x != -999.0 else "NO")

    with placeholder.container():
        st.write(f"🔄 更新时间: {time.strftime('%H:%M:%S')} | 优先级: OKX > Gate")
        
        def row_style(row):
            if row['预警等级'] >= 2: return ['background-color: #FFD700; color: black'] * len(row)
            if "底背离" in str(row['OBV预警']): return ['background-color: #E6F3FF; color: black'] * len(row)
            return [''] * len(row)

        cols = ["币种", "最新价", "OBV预警"] + ch_cols + ["OKX", "Gate", "Huobi", "Bitget"]
        st.dataframe(display_df[cols].style.apply(row_style, axis=1), use_container_width=True, height=800)

    # --- 异步倒计时 ---
    for i in range(interval, 0, -1):
        countdown_area.metric("⏰ 下轮扫描倒计时", f"{i} 秒")
        time.sleep(1)
