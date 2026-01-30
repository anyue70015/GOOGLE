import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置与全局变量 (核心修复：存入普通字典而非 session_state)
# ==========================================
st.set_page_config(page_title="指挥部-安全版", layout="wide")

# 全局内存字典，不受 Streamlit 线程限制
if 'GLOBAL_DATA' not in globals():
    globals()['GLOBAL_DATA'] = {}

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "ZEC", "ASTER"]
CH_COLS = ['1m涨跌', '5m涨跌', '15m涨跌', '1h涨跌', '4h涨跌', '24h涨跌', '7d涨跌']

# ==========================================
# 2. 线程安全抓取函数
# ==========================================
def fetch_worker(symbol, threshold, is_slow_update):
    pair = f"{symbol}/USDT"
    
    # 核心修复点：从全局变量 globals() 读取，不再访问 st.session_state
    master_store = globals().get('GLOBAL_DATA', {})
    res = master_store.get(symbol, {
        "币种": symbol, "最新价": "Loading", "OBV预警": "待扫描",
        "OKX": "·", "Gate": "·", "Huobi": "·", "Bitget": "·",
        "net_flow": 0, "active_count": 0
    })
    
    # 初始化字段
    for col in CH_COLS: 
        if col not in res: res[col] = -999.0

    success_ex = None
    # 优先级：OKX -> Gate -> Bitget
    for eid in ['okx', 'gateio', 'bitget']:
        try:
            ex = getattr(ccxt, eid)({'timeout': 1000, 'enableRateLimit': True})
            tk = ex.fetch_ticker(pair)
            curr_p = tk['last']
            res["最新价"] = curr_p
            now_ms = ex.milliseconds()
            
            # --- 快数据：滚动涨幅 ---
            for tf, col in zip(['1m', '5m'], ['1m涨跌', '5m涨跌']):
                k = ex.fetch_ohlcv(pair, tf, limit=2)
                if k: res[col] = ((curr_p - k[0][4]) / k[0][4]) * 100

            # --- 慢数据：滚动窗口 (10分钟同步一次) ---
            if is_slow_update:
                # 15m
                k15 = ex.fetch_ohlcv(pair, '15m', limit=2)
                if k15: res['15m涨跌'] = ((curr_p - k15[0][4]) / k15[0][4]) * 100
                # 1h, 24h, 7d 精准滚动
                for tf_ms, col in zip([3600000, 86400000, 604800000], ['1h涨跌', '24h涨跌', '7d涨跌']):
                    tf_name = '1m' if tf_ms == 3600000 else ('1h' if tf_ms == 86400000 else '4h')
                    kh = ex.fetch_ohlcv(pair, tf_name, since=now_ms - tf_ms, limit=1)
                    if kh: res[col] = ((curr_p - kh[0][4]) / kh[0][4]) * 100
            
            success_ex = eid.split('io')[0].upper()
            break
        except: continue

    # --- 大单扫描 ---
    res['net_flow'] = 0
    res['active_count'] = 0
    th = threshold if symbol in ['BTC', 'ETH'] else threshold / 5
    for name, eid in {'OKX':'okx', 'Gate':'gateio', 'Huobi':'htx', 'Bitget':'bitget'}.items():
        try:
            ex_t = getattr(ccxt, eid)({'timeout': 600})
            trades = ex_t.fetch_trades(pair, limit=15)
            buy_v = 0
            for t in trades:
                v = t['price'] * t['amount']
                res['net_flow'] += v if t['side'] == 'buy' else -v
                if t['side'] == 'buy' and v >= th: buy_v += v
            res[name] = f"{buy_v/10000:.1f}万" if buy_v > 0 else "·"
            if buy_v > 0: res['active_count'] += 1
        except: res[name] = "·"

    res['OBV预警'] = f"💎底背离({success_ex})" if (isinstance(res.get('1h涨跌'), float) and res['1h涨跌'] < -0.3 and res['net_flow'] > 0) else f"正常({success_ex})"
    return res

# ==========================================
# 3. 主界面逻辑
# ==========================================
st.markdown("<style>.stDataFrame { opacity: 1.0 !important; }</style>", unsafe_allow_html=True)

with st.sidebar:
    st_val = st.number_input("大单阈值", value=20000)
    interval = st.slider("刷新频率", 5, 30, 10)
    countdown = st.empty()

placeholder = st.empty()

# 记录慢速更新时间
if 'last_slow' not in st.session_state: st.session_state.last_slow = 0

while True:
    now = time.time()
    is_slow = False
    if now - st.session_state.last_slow > 600:
        is_slow = True
        st.session_state.last_slow = now

    # 多线程并行
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda s: fetch_worker(s, st_val, is_slow), SYMBOLS))

    # 更新全局内存
    for r in results:
        globals()['GLOBAL_DATA'][r['币种']] = r

    # 排序与展示
    df = pd.DataFrame(results)
    df['sk'] = df['1m涨跌'].apply(lambda x: x if isinstance(x, float) else -999)
    df = df.sort_values(by="sk", ascending=False)
    
    display_df = df.copy()
    for col in CH_COLS:
        display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%" if isinstance(x, float) and x != -999.0 else "·")

    with placeholder.container():
        st.write(f"🔄 刷新: {time.strftime('%H:%M:%S')} | 模式: {'[全周期]' if is_slow else '[快照]'}")
        cols_to_show = ["币种", "最新价", "OBV预警"] + CH_COLS + ["OKX", "Gate", "Huobi", "Bitget"]
        st.dataframe(display_df[cols_to_show], use_container_width=True, height=750)

    for i in range(interval, 0, -1):
        countdown.metric("下次刷新", f"{i}s")
        time.sleep(1)
