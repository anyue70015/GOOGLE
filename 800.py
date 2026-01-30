import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="资金指挥部-滚动周期版", layout="wide")

st.markdown("""
    <style>
    .stDataFrame { opacity: 1.0 !important; }
    .stApp { background-color: white; }
    </style>
    """, unsafe_allow_html=True)

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX"]
EXCHANGE_IDS = {'OKX': 'okx', 'Gate': 'gateio', 'Huobi': 'htx', 'Bitget': 'bitget'}
ALL_CH_COLS = ['1m涨跌', '5m涨跌', '15m涨跌', '1h涨跌', '4h涨跌', '24h涨跌', '7d涨跌']

if 'last_valid_data' not in st.session_state:
    st.session_state.last_valid_data = {}
if 'signal_memory' not in st.session_state:
    st.session_state.signal_memory = {}

# ==========================================
# 2. 核心抓取引擎 (滚动时间窗口逻辑)
# ==========================================
def fetch_worker(symbol, base_threshold, history_cache):
    pair = f"{symbol}/USDT"
    local_threshold = base_threshold if symbol in ['BTC', 'ETH'] else base_threshold / 4
    
    res = {
        "币种": symbol, "最新价": "NO", "OBV预警": "正常", 
        "OKX": "·", "Gate": "·", "Huobi": "·", "Bitget": "·",
        "net_flow": 0, "active_count": 0, "预警等级": 0
    }
    for col in ALL_CH_COLS: res[col] = -999.0
    if history_cache: res.update(history_cache)

    try:
        ex_main = ccxt.okx({'timeout': 3000, 'enableRateLimit': True})
        tk = ex_main.fetch_ticker(pair)
        curr_p = tk['last']
        res["最新价"] = curr_p

        # --- “近”周期滚动逻辑 ---
        # 1m, 5m, 15m 
        for tf in ['1m', '5m', '15m']:
            ohlcv = ex_main.fetch_ohlcv(pair, tf, limit=2)
            if len(ohlcv) >= 2:
                res[f"{tf}涨跌"] = ((curr_p - ohlcv[0][4]) / ohlcv[0][4]) * 100

        # 近1h (取1m周期的第60根前)
        h1_data = ex_main.fetch_ohlcv(pair, '1m', limit=61)
        if len(h1_data) >= 61:
            res["1h涨跌"] = ((curr_p - h1_data[0][4]) / h1_data[0][4]) * 100

        # 近4h (取15m周期的第16根前: 15*16=240min)
        h4_data = ex_main.fetch_ohlcv(pair, '15m', limit=17)
        if len(h4_data) >= 17:
            res["4h涨跌"] = ((curr_p - h4_data[0][4]) / h4_data[0][4]) * 100

        # 近24h (取1h周期的第24根前)
        d1_data = ex_main.fetch_ohlcv(pair, '1h', limit=25)
        if len(d1_data) >= 25:
            res["24h涨跌"] = ((curr_p - d1_data[0][4]) / d1_data[0][4]) * 100

        # 近7d (取4h周期的第42根前: 4*42=168h)
        w1_data = ex_main.fetch_ohlcv(pair, '4h', limit=43)
        if len(w1_data) >= 43:
            res["7d涨跌"] = ((curr_p - w1_data[0][4]) / w1_data[0][4]) * 100

        # --- 大单流向 (100笔深度) ---
        for name, eid in EXCHANGE_IDS.items():
            try:
                ex_trade = getattr(ccxt, eid)({'timeout': 2000, 'enableRateLimit': True})
                trades = ex_trade.fetch_trades(pair, limit=100)
                buy_sum = 0
                for t in trades:
                    val = t['price'] * t['amount']
                    res['net_flow'] += val if t['side'] == 'buy' else -val
                    if t['side'] == 'buy' and val >= local_threshold:
                        buy_sum += val
                res[name] = f"{buy_sum/10000:.1f}万" if buy_sum > 0 else "·"
                if buy_sum > 0: res['active_count'] += 1
            except: continue

        # 1h滚动背离判断
        if isinstance(res.get('1h涨跌'), float) and res['1h涨跌'] < -0.3 and res['net_flow'] > 0:
            res['OBV预警'] = "💎底背离"
        else: res['OBV预警'] = "正常"

    except: pass
    return res

# ==========================================
# 3. 渲染主循环 (保持不变)
# ==========================================
st.title("🏹 资金指挥部 - 滚动时间窗口版")

with st.sidebar:
    st.header("⚙️ 配置")
    st_val = st.number_input("大盘大单阈值", value=20000)
    interval = st.slider("刷新间隔", 10, 60, 30)
    countdown_area = st.empty()

placeholder = st.empty()

while True:
    current_cache = {s: st.session_state.last_valid_data.get(s) for s in SYMBOLS}
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        results = list(executor.map(lambda s: fetch_worker(s, st_val, current_cache[s]), SYMBOLS))
    
    now = time.time()
    for r in results:
        sym = r['币种']
        st.session_state.last_valid_data[sym] = r 
        if sym not in st.session_state.signal_memory: st.session_state.signal_memory[sym] = {"level": 0, "time": 0}
        lvl = 1 if (isinstance(r.get('1m涨跌'), float) and r['1m涨跌'] >= 0.4) else 0
        if r.get('active_count', 0) >= 2: lvl = 2
        if "底背离" in r['OBV预警']: lvl = max(lvl, 2)
        if lvl > 0: st.session_state.signal_memory[sym] = {"level": lvl, "time": now}
        r['预警等级'] = st.session_state.signal_memory[sym]['level'] if now - st.session_state.signal_memory[sym]['time'] < 600 else 0

    df = pd.DataFrame(results)
    final_cols = ["币种", "最新价", "OBV预警"] + ALL_CH_COLS + ["OKX", "Gate", "Huobi", "Bitget"]
    for c in final_cols:
        if c not in df.columns: df[c] = "NO"
    
    df['sort_key'] = df['1m涨跌'].apply(lambda x: x if isinstance(x, float) else -999.0)
    df = df.sort_values(by="sort_key", ascending=False).drop(columns=['sort_key'])

    display_df = df.copy()
    for col in ALL_CH_COLS:
        display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%" if isinstance(x, float) and x != -999.0 else "NO")

    with placeholder.container():
        st.write(f"🔄 刷新时间: {time.strftime('%H:%M:%S')} | 模式: 滚动窗口 (Rolling)")
        def row_style(row):
            if row.get('预警等级', 0) >= 2: return ['background-color: #FFD700; color: black'] * len(row)
            if "底背离" in str(row.get('OBV预警', '')): return ['background-color: #E6F3FF; color: black'] * len(row)
            return [''] * len(row)
        st.dataframe(display_df[final_cols].style.apply(row_style, axis=1), use_container_width=True, height=800)

    for i in range(interval, 0, -1):
        countdown_area.metric("⏰ 倒计时", f"{i} 秒")
        time.sleep(1)
