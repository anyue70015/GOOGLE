import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="资金指挥部-双源热备版", layout="wide")

st.markdown("""
    <style>
    .stDataFrame { opacity: 1.0 !important; }
    .stApp { background-color: white; }
    </style>
    """, unsafe_allow_html=True)

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX"]
EXCHANGE_IDS = {'OKX': 'okx', 'Gate': 'gateio', 'Huobi': 'htx', 'Bitget': 'bitget'}

if 'last_valid_data' not in st.session_state:
    st.session_state.last_valid_data = {}
if 'signal_memory' not in st.session_state:
    st.session_state.signal_memory = {}

# ==========================================
# 2. 核心逻辑：主备行情抓取 (OKX -> Gate)
# ==========================================
def fetch_worker(symbol, threshold):
    pair = f"{symbol}/USDT"
    # 继承历史数据，防止跳 NO
    res = st.session_state.last_valid_data.get(symbol, {
        "币种": symbol, "最新价": "NO", "OBV预警": "正常", 
        "OKX": "·", "Gate": "·", "Huobi": "·", "Bitget": "·",
        "1m涨跌": -999.0, "15m涨跌": -999.0, "1h涨跌": -999.0, 
        "4h涨跌": -999.0, "24h涨跌": -999.0, "7d涨跌": -999.0,
        "net_flow": 0, "active_count": 0
    })

    # 定义优先级：OKX 第一，Gate 第二
    priority_exchanges = ['OKX', 'Gate']
    tfs_map = {'1m': '1m涨跌', '15m': '15m涨跌', '1h': '1h涨跌', '4h': '4h涨跌', '1d': '24h涨跌', '1w': '7d涨跌'}
    
    data_fetched = False

    # --- 1. 价格与多周期涨幅抓取 (主备切换) ---
    for ex_id in priority_exchanges:
        if data_fetched: break
        try:
            ex_obj = getattr(ccxt, EXCHANGE_IDS[ex_id])({'timeout': 3000, 'enableRateLimit': True})
            # 抓取价格
            ticker = ex_obj.fetch_ticker(pair)
            res["最新价"] = ticker['last']
            
            # 抓取所有周期涨幅
            for tf, col_name in tfs_map.items():
                ohlcv = ex_obj.fetch_ohlcv(pair, tf, limit=2)
                if len(ohlcv) >= 2:
                    res[col_name] = ((ohlcv[-1][4] - ohlcv[-1][1]) / ohlcv[-1][1]) * 100
            
            data_fetched = True # 如果执行到这里没报错，说明行情源取到了
        except:
            continue # 如果主源失败，尝试下一个

    # --- 2. 大单流向监控 (四大所全量扫描) ---
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

    # --- 3. 背离逻辑更新 ---
    if isinstance(res.get('1h涨跌'), float) and res['1h涨跌'] < -0.5 and res['net_flow'] > 0:
        res['OBV预警'] = "💎底背离"
    else:
        res['OBV预警'] = "正常"

    # 存入缓存
    st.session_state.last_valid_data[symbol] = res
    return res

# ==========================================
# 3. 界面逻辑
# ==========================================
st.title("🏹 资金指挥部 (OKX/Gate 主备行情版)")

with st.sidebar:
    st.header("⚙️ 控制面板")
    big_val = st.number_input("大单阈值 (USDT)", value=20000)
    interval = st.slider("扫描间隔 (秒)", 10, 60, 30)
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
        if isinstance(r.get('1m涨跌'), float) and r['1m涨跌'] >= 0.5:
            lvl = 1
            if r['active_count'] >= 2: lvl = 2
        if "底背离" in r['OBV预警']: lvl = max(lvl, 2)
        
        if lvl > 0:
            st.session_state.signal_memory[sym] = {"level": lvl, "time": curr_t}
        r['预警等级'] = st.session_state.signal_memory[sym]['level'] if curr_t - st.session_state.signal_memory[sym]['time'] < 900 else 0

    # --- 排序与格式化显示 ---
    # 按照 1m 涨幅动态排序
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

    # --- 异步倒计时逻辑 ---
    for i in range(interval, 0, -1):
        countdown_placeholder.metric("⏰ 距离下一次强制刷新", f"{i} 秒")
        time.sleep(1)
