import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="资金预警指挥部-极速版", layout="wide")

# 强制白色主题下文字清晰
st.markdown("""
    <style>
    .stDataFrame { opacity: 1.0 !important; } /* 防止变淡 */
    .stApp { background-color: white; }
    </style>
    """, unsafe_allow_html=True)

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "XMR", "LINK", "XLM", "CC", "ASTER", "ZEC",]
EXCHANGE_IDS = {'OKX': 'okx', 'Gate': 'gateio', 'Huobi': 'htx', 'Bitget': 'bitget'}
TFS = ['1m', '5m', '15m', '1h']

# 初始化信号记忆
if 'signal_memory' not in st.session_state:
    st.session_state.signal_memory = {sym: {"level": 0, "time": 0} for sym in SYMBOLS}

# ==========================================
# 2. 高效抓取引擎 (带单次超时)
# ==========================================
def fetch_worker(symbol, big_val_threshold):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol, "最新价": "N/A", "OKX": "·", "Gate": "·", "Huobi": "·", "Bitget": "·"}
    res.update({f"{tf}涨跌": "0.00%" for tf in TFS})
    res.update({'raw_1m': 0, 'active_count': 0, 'net_flow': 0})
    
    # 获取基础数据 (OKX/Gate)
    for eid in ['OKX', 'Gate']:
        try:
            ex = getattr(ccxt, EXCHANGE_IDS[eid])({'timeout': 3000}) # 极短超时防止卡死
            tk = ex.fetch_ticker(pair)
            res["最新价"] = tk['last']
            for tf in TFS:
                ohlcv = ex.fetch_ohlcv(pair, tf, limit=2)
                if len(ohlcv) >= 2:
                    ch = ((ohlcv[-1][4] - ohlcv[-1][1]) / ohlcv[-1][1]) * 100
                    res[f"{tf}涨跌"] = f"{ch:+.2f}%"
                    if tf == '1m': res['raw_1m'] = ch
            break
        except: continue

    # 获取交易所大单
    for name, eid in EXCHANGE_IDS.items():
        try:
            ex = getattr(ccxt, eid)({'timeout': 3000})
            trades = ex.fetch_trades(pair, limit=20)
            big_buy_sum = 0
            for t in trades:
                val = t['price'] * t['amount']
                res['net_flow'] += val * (1 if t['side'] == 'buy' else -1)
                if t['side'] == 'buy' and val >= big_val_threshold:
                    big_buy_sum += val
            if big_buy_sum > 0:
                res['active_count'] += 1
                res[name] = f"{big_buy_sum/10000:.1f}万"
        except: res[name] = "⚠️"
    
    return res

# ==========================================
# 3. 界面逻辑
# ==========================================
st.title("🏹 渐进式资金预警 (极速稳定版)")

with st.sidebar:
    st.header("⚙️ 参数控制")
    big_val = st.number_input("大单阈值 (USDT)", value=20000, step=5000)
    interval = st.slider("扫描间隔 (秒)", 10, 120, 40)
    st.info("💡 信号触发后将保留15分钟变色")

placeholder = st.empty()
countdown_bar = st.sidebar.progress(0)
countdown_text = st.sidebar.empty()

while True:
    # --- 1. 执行抓取 ---
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        results = list(executor.map(lambda s: fetch_worker(s, big_val), SYMBOLS))
    
    # --- 2. 处理信号记忆 ---
    curr_t = time.time()
    for r in results:
        lvl = 0
        if r['raw_1m'] >= 0.5:
            lvl = 1
            if r['active_count'] == 2: lvl = 2
            if r['active_count'] >= 3: lvl = 3
        
        # 更新记忆
        if lvl > 0:
            st.session_state.signal_memory[r['币种']] = {"level": lvl, "time": curr_t}
        
        # 读取记忆 (15分钟有效)
        mem = st.session_state.signal_memory[r['币种']]
        r['预警等级'] = mem['level'] if curr_t - mem['time'] < 900 else 0

    # --- 3. 渲染数据 ---
    df = pd.DataFrame(results).sort_values("raw_1m", ascending=False)
    
    with placeholder.container():
        st.write(f"🔄 刷新时间: {time.strftime('%H:%M:%S')} | 策略: 极速非阻塞")
        
        def row_style(row):
            lvl = row['预警等级']
            if lvl == 3: return ['background-color: #FF4500; color: white; font-weight: bold'] * len(row) # 深橘红
            if lvl == 2: return ['background-color: #FFD700; color: black; font-weight: bold'] * len(row) # 金黄
            if lvl == 1: return ['background-color: #FFFFE0; color: black'] * len(row) # 浅黄
            return [''] * len(row)

        def color_ch(val):
            if not isinstance(val, str): return ''
            if '+' in val: return 'color: #28a745; font-weight: bold'
            if '-' in val: return 'color: #dc3545; font-weight: bold'
            return ''

        st.dataframe(
            df.drop(columns=['raw_1m', 'active_count', 'net_flow']).style.apply(row_style, axis=1)
                .applymap(color_ch, subset=[f"{tf}涨跌" for tf in TFS]),
            use_container_width=True, height=600
        )

    # --- 4. 实时动态倒计时 (每秒强刷 UI) ---
    for i in range(interval, 0, -1):
        countdown_text.metric("下次扫描倒计时", f"{i} 秒")
        countdown_bar.progress((interval - i) / interval)
        time.sleep(1)


