import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="资金指挥部-全维度版", layout="wide")

st.markdown("""
    <style>
    .stDataFrame { opacity: 1.0 !important; }
    .stApp { background-color: white; }
    </style>
    """, unsafe_allow_html=True)

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX"]
EXCHANGE_IDS = {'OKX': 'okx', 'Gate': 'gateio', 'Huobi': 'htx', 'Bitget': 'bitget'}
# 严格按照你要求的“近周期”排列
ALL_CH_COLS = ['1m涨跌', '5m涨跌', '15m涨跌', '1h涨跌', '4h涨跌', '24h涨跌', '7d涨跌']

if 'last_valid_data' not in st.session_state:
    st.session_state.last_valid_data = {}
if 'signal_memory' not in st.session_state:
    st.session_state.signal_memory = {}

# ==========================================
# 2. 核心抓取引擎 (增强深度 + 动态阈值)
# ==========================================
def fetch_worker(symbol, base_threshold, history_cache):
    pair = f"{symbol}/USDT"
    # 根据币种自动调整大单门槛：BTC/ETH 高，山寨币低
    local_threshold = base_threshold if symbol in ['BTC', 'ETH'] else base_threshold / 4
    
    res = {
        "币种": symbol, "最新价": "NO", "OBV预警": "正常", 
        "OKX": "·", "Gate": "·", "Huobi": "·", "Bitget": "·",
        "net_flow": 0, "active_count": 0, "预警等级": 0
    }
    for col in ALL_CH_COLS: res[col] = -999.0
    if history_cache: res.update(history_cache)

    tfs_map = {'1m': '1m涨跌', '5m': '5m涨跌', '15m': '15m涨跌', '1h': '1h涨跌', '4h': '4h涨跌', '1d': '24h涨跌', '1w': '7d涨跌'}
    
    # --- 1. “近周期”行情抓取 ---
    success_flag = False
    for ex_id in ['OKX', 'Gate']:
        if success_flag: break
        try:
            ex_obj = getattr(ccxt, EXCHANGE_IDS[ex_id])({'timeout': 3000, 'enableRateLimit': True})
            tk = ex_obj.fetch_ticker(pair)
            res["最新价"] = tk['last']
            
            for tf, col_name in tfs_map.items():
                # 抓取最近 2 根，计算从上一根收盘到现在的“近周期”涨幅
                ohlcv = ex_obj.fetch_ohlcv(pair, tf, limit=2)
                if len(ohlcv) >= 2:
                    res[col_name] = ((tk['last'] - ohlcv[-2][4]) / ohlcv[-2][4]) * 100
            success_flag = True
        except: continue

    # --- 2. 深度大单扫描 (提升至 100 笔) ---
    for name, eid in EXCHANGE_IDS.items():
        try:
            ex_trade = getattr(ccxt, eid)({'timeout': 2000, 'enableRateLimit': True})
            trades = ex_trade.fetch_trades(pair, limit=100) # 扫描深度翻 5 倍
            buy_sum = 0
            for t in trades:
                val = t['price'] * t['amount']
                res['net_flow'] += val if t['side'] == 'buy' else -val
                if t['side'] == 'buy' and val >= local_threshold:
                    buy_sum += val
            res[name] = f"{buy_sum/10000:.1f}万" if buy_sum > 0 else "·"
            if buy_sum > 0: res['active_count'] += 1
        except: res[name] = "NO"

    # 底背离逻辑：价格跌但大单进
    if isinstance(res.get('1h涨跌'), float) and res['1h涨跌'] < -0.3 and res['net_flow'] > 0:
        res['OBV预警'] = "💎底背离"
    else: res['OBV预警'] = "正常"

    return res

# ==========================================
# 3. 渲染主循环
# ==========================================
st.title("🏹 资金指挥部 - 全维度近周期监控")

with st.sidebar:
    st.header("⚙️ 监控配置")
    st_val = st.number_input("大盘大单阈值 (USDT)", value=20000, help="山寨币将自动按 1/4 计算")
    interval = st.slider("数据刷新间隔 (秒)", 10, 60, 30)
    st.info(f"💡 当前山寨币大单门槛: {st_val/4000:.1f}万 USDT")
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
        
        lvl = 0
        if isinstance(r.get('1m涨跌'), float) and r['1m涨跌'] >= 0.4:
            lvl = 1
            if r.get('active_count', 0) >= 2: lvl = 2
        if "底背离" in r['OBV预警']: lvl = max(lvl, 2)
        if lvl > 0: st.session_state.signal_memory[sym] = {"level": lvl, "time": now}
        r['预警等级'] = st.session_state.signal_memory[sym]['level'] if now - st.session_state.signal_memory[sym]['time'] < 600 else 0

    # 排序与强制补齐
    df = pd.DataFrame(results)
    final_cols = ["币种", "最新价", "OBV预警"] + ALL_CH_COLS + ["OKX", "Gate", "Huobi", "Bitget", "预警等级"]
    for c in final_cols:
        if c not in df.columns: df[c] = "NO"
    
    df['sort_key'] = df['1m涨跌'].apply(lambda x: x if isinstance(x, float) else -999.0)
    df = df.sort_values(by="sort_key", ascending=False).drop(columns=['sort_key'])

    display_df = df.copy()
    for col in ALL_CH_COLS:
        display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%" if isinstance(x, float) and x != -999.0 else "NO")

    with placeholder.container():
        st.write(f"🔄 实时行情: {time.strftime('%H:%M:%S')} | 山寨币已增强扫描")
        
        def row_style(row):
            if row.get('预警等级', 0) >= 2: return ['background-color: #FFD700; color: black'] * len(row)
            if "底背离" in str(row.get('OBV预警', '')): return ['background-color: #E6F3FF; color: black'] * len(row)
            return [''] * len(row)

        st.dataframe(display_df[final_cols].style.apply(row_style, axis=1), use_container_width=True, height=800)

    for i in range(interval, 0, -1):
        countdown_area.metric("⏰ 倒计时", f"{i} 秒")
        time.sleep(1)
