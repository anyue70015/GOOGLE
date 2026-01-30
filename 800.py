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
# 定义标准的显示列顺序，确保 fetch_worker 也能识别
ALL_CH_COLS = ['1m涨跌', '15m涨跌', '1h涨跌', '4h涨跌', '24h涨跌', '7d涨跌']

if 'last_valid_data' not in st.session_state:
    st.session_state.last_valid_data = {}
if 'signal_memory' not in st.session_state:
    st.session_state.signal_memory = {}

# ==========================================
# 2. 线程安全抓取引擎
# ==========================================
def fetch_worker(symbol, threshold, history_cache):
    pair = f"{symbol}/USDT"
    
    # 基础结构初始化，确保所有列都有默认值
    res = {
        "币种": symbol, "最新价": "NO", "OBV预警": "正常", 
        "OKX": "·", "Gate": "·", "Huobi": "·", "Bitget": "·",
        "net_flow": 0, "active_count": 0, "预警等级": 0
    }
    for col in ALL_CH_COLS: res[col] = -999.0 # 默认标志值

    # 如果有历史成功数据，先用历史数据覆盖
    if history_cache:
        res.update(history_cache)

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
        except: continue

    # 扫描四大所大单
    for name, eid in EXCHANGE_IDS.items():
        try:
            ex_trade = getattr(ccxt, eid)({'timeout': 1500, 'enableRateLimit': True})
            trades = ex_trade.fetch_trades(pair, limit=20)
            buy_sum = 0
            for t in trades:
                val = t['price'] * t['amount']
                res['net_flow'] += val if t['side'] == 'buy' else -val
                if t['side'] == 'buy' and val >= threshold: buy_sum += val
            res[name] = f"{buy_sum/10000:.1f}万" if buy_sum > 0 else "·"
            if buy_sum > 0: res['active_count'] += 1
        except: res[name] = "NO"

    if isinstance(res.get('1h涨跌'), float) and res['1h涨跌'] < -0.5 and res['net_flow'] > 0:
        res['OBV预警'] = "💎底背离"
    else: res['OBV预警'] = "正常"

    return res

# ==========================================
# 3. 渲染主循环
# ==========================================
st.title("🏹 资金指挥部 (KeyError 修复终结版)")

with st.sidebar:
    big_val = st.number_input("大单阈值 (USDT)", value=20000)
    interval = st.slider("扫描间隔 (秒)", 10, 60, 30)
    countdown_area = st.empty()

placeholder = st.empty()

while True:
    # 提取缓存传递给子线程
    current_cache = {s: st.session_state.last_valid_data.get(s) for s in SYMBOLS}
    
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        results = list(executor.map(lambda s: fetch_worker(s, big_val, current_cache[s]), SYMBOLS))
    
    now = time.time()
    for r in results:
        sym = r['币种']
        st.session_state.last_valid_data[sym] = r 
        if sym not in st.session_state.signal_memory:
            st.session_state.signal_memory[sym] = {"level": 0, "time": 0}
        
        lvl = 0
        if isinstance(r.get('1m涨跌'), float) and r['1m涨跌'] >= 0.5:
            lvl = 1
            if r.get('active_count', 0) >= 2: lvl = 2
        if "底背离" in r['OBV预警']: lvl = max(lvl, 2)
        
        if lvl > 0: st.session_state.signal_memory[sym] = {"level": lvl, "time": now}
        r['预警等级'] = st.session_state.signal_memory[sym]['level'] if now - st.session_state.signal_memory[sym]['time'] < 900 else 0

    # --- 关键修复：强制补齐缺失列，防止过滤时抛出 KeyError ---
    df = pd.DataFrame(results)
    final_cols = ["币种", "最新价", "OBV预警"] + ALL_CH_COLS + ["OKX", "Gate", "Huobi", "Bitget", "预警等级"]
    for c in final_cols:
        if c not in df.columns: df[c] = "NO"

    # 按 1m 涨幅排序 (处理 NO 值排序)
    df['sort_key'] = df['1m涨跌'].apply(lambda x: x if isinstance(x, float) else -999.0)
    df = df.sort_values(by="sort_key", ascending=False).drop(columns=['sort_key'])

    # 格式化显示
    display_df = df.copy()
    for col in ALL_CH_COLS:
        display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%" if isinstance(x, float) and x != -999.0 else "NO")

    with placeholder.container():
        st.write(f"🔄 更新时间: {time.strftime('%H:%M:%S')} | 已修复列对齐")
        
        def row_style(row):
            if row.get('预警等级', 0) >= 2: return ['background-color: #FFD700; color: black'] * len(row)
            if "底背离" in str(row.get('OBV预警', '')): return ['background-color: #E6F3FF; color: black'] * len(row)
            return [''] * len(row)

        # 渲染
        st.dataframe(
            display_df[final_cols].style.apply(row_style, axis=1), 
            use_container_width=True, 
            height=800
        )

    for i in range(interval, 0, -1):
        countdown_area.metric("⏰ 下轮刷新倒计时", f"{i} 秒")
        time.sleep(1)
