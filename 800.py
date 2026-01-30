import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="OBV背离指挥部", layout="wide")

st.markdown("""
    <style>
    .stDataFrame { opacity: 1.0 !important; }
    .stApp { background-color: white; }
    </style>
    """, unsafe_allow_html=True)

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "ZEC", "ASTER", "CHZ"]
EXCHANGE_IDS = {'OKX': 'okx', 'Gate': 'gateio', 'Huobi': 'htx', 'Bitget': 'bitget'}
TFS = {'1m': 2, '15m': 2, '1h': 2, '4h': 2, '1d': 2, '1w': 2}

if 'signal_memory' not in st.session_state:
    st.session_state.signal_memory = {sym: {"level": 0, "time": 0} for sym in SYMBOLS}

# ==========================================
# 2. 核心抓取与背离计算引擎
# ==========================================
def fetch_worker(symbol, big_val_threshold):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol, "最新价": "N/A", "OKX": "·", "Gate": "·", "Huobi": "·", "Bitget": "·", "OBV预警": "正常"}
    tf_display = ['1m', '15m', '1h', '4h', '24h', '7d']
    res.update({f"{tf}涨跌": 0.0 for tf in tf_display})
    res.update({'active_count': 0, 'net_flow': 0})
    
    try:
        ex = ccxt.okx({'timeout': 3000})
        # 1. 获取多周期涨跌
        for tf in ['1m', '15m', '1h', '4h', '1d', '1w']:
            ohlcv = ex.fetch_ohlcv(pair, tf, limit=2)
            if len(ohlcv) >= 2:
                ch = ((ohlcv[-1][4] - ohlcv[-1][1]) / ohlcv[-1][1]) * 100
                key = f"{tf}涨跌" if tf != '1d' and tf != '1w' else ("24h涨跌" if tf == '1d' else "7d涨跌")
                res[key] = round(ch, 2)
        
        tk = ex.fetch_ticker(pair)
        res["最新价"] = tk['last']
    except: pass

    # 2. 统计各交易所净流向 (简易OBV逻辑)
    for name, eid in EXCHANGE_IDS.items():
        try:
            ex_obj = getattr(ccxt, eid)({'timeout': 2500})
            trades = ex_obj.fetch_trades(pair, limit=50)
            exchange_buy = 0
            for t in trades:
                val = t['price'] * t['amount']
                side_sign = 1 if t['side'] == 'buy' else -1
                res['net_flow'] += val * side_sign # 累加净流向
                if t['side'] == 'buy' and val >= big_val_threshold:
                    exchange_buy += val
            if exchange_buy > 0:
                res['active_count'] += 1
                res[name] = f"{exchange_buy/10000:.1f}万"
        except: res[name] = "⚠️"
    
    # 3. OBV背离逻辑判断 (核心逻辑)
    # 底背离：1小时跌幅 < -0.5% 但 净流向(net_flow) > 0 且有大单活跃
    if res['1h涨跌'] < -0.5 and res['net_flow'] > 0 and res['active_count'] >= 1:
        res['OBV预警'] = "💎底背离(吸筹)"
    # 顶背离：1小时涨幅 > 0.5% 但 净流向(net_flow) < 0
    elif res['1h涨跌'] > 0.5 and res['net_flow'] < 0:
        res['OBV预警'] = "⚠️顶背离(派发)"
    
    return res

# ==========================================
# 3. UI 渲染
# ==========================================
st.title("🏹 渐进式资金预警 + OBV背离系统")

with st.sidebar:
    st.header("⚙️ 参数控制")
    big_val = st.number_input("大单阈值 (USDT)", value=20000, step=5000)
    interval = st.slider("扫描间隔 (秒)", 10, 120, 30)
    st.info("💎底背离：价格在跌但资金净买入，适合抄底。")
    st.info("⚠️顶背离：价格在涨但资金净流出，小心诱多。")

placeholder = st.empty()

while True:
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        results = list(executor.map(lambda s: fetch_worker(s, big_val), SYMBOLS))
    
    curr_t = time.time()
    for r in results:
        lvl = 0
        if r['1m涨跌'] >= 0.5:
            lvl = 1
            if r['active_count'] >= 2: lvl = 2
            if r['active_count'] >= 3: lvl = 3
        # 如果有底背离，强制提升预警优先级
        if "底背离" in r['OBV预警']: lvl = max(lvl, 2) 
        
        if lvl > 0:
            st.session_state.signal_memory[r['币种']] = {"level": lvl, "time": curr_t}
        
        mem = st.session_state.signal_memory[r['币种']]
        r['预警等级'] = mem['level'] if curr_t - mem['time'] < 900 else 0

    df = pd.DataFrame(results).sort_values("1m涨跌", ascending=False)
    
    # 转换百分比显示格式
    for col in [f"{tf}涨跌" for tf in ['1m', '15m', '1h', '4h', '24h', '7d']]:
        df[col] = df[col].apply(lambda x: f"{x:+.2f}%")

    with placeholder.container():
        st.write(f"🔄 更新: {time.strftime('%H:%M:%S')} | 沃什提名震荡监控")
        
        def row_style(row):
            if "底背离" in str(row['OBV预警']):
                return ['background-color: #E6F3FF; color: #004085; font-weight: bold'] * len(row) # 蓝色吸筹
            lvl = row['预警等级']
            if lvl == 3: return ['background-color: #FF4500; color: white'] * len(row)
            if lvl == 2: return ['background-color: #FFD700; color: black'] * len(row)
            return [''] * len(row)

        st.dataframe(
            df.style.apply(row_style, axis=1),
            use_container_width=True, height=650
        )

    time.sleep(interval)
