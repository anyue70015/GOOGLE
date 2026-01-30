import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置与全局缓存
# ==========================================
st.set_page_config(page_title="指挥部-零延迟版", layout="wide")

# 核心缓存：存储所有币种的最新状态
if 'master_data' not in st.session_state:
    st.session_state.master_data = {}
if 'last_slow_tick' not in st.session_state:
    st.session_state.last_slow_tick = 0

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "ZEC", "ASTER"]
CH_COLS = ['1m涨跌', '5m涨跌', '15m涨跌', '1h涨跌', '4h涨跌', '24h涨跌', '7d涨跌']

# ==========================================
# 2. 极速抓取引擎
# ==========================================
def fetch_worker(symbol, threshold, is_slow_update):
    pair = f"{symbol}/USDT"
    # 继承旧数据，避免 NO 闪烁
    res = st.session_state.master_data.get(symbol, {
        "币种": symbol, "最新价": "Loading", "OBV预警": "待扫描",
        "OKX": "·", "Gate": "·", "Huobi": "·", "Bitget": "·",
        "net_flow": 0, "active_count": 0
    })
    for col in CH_COLS: 
        if col not in res: res[col] = -999.0

    success_ex = None
    # 优先级：OKX -> Gate -> Bitget (解决 TAO, ZEC 找不到的问题)
    for eid in ['okx', 'gateio', 'bitget']:
        try:
            ex = getattr(ccxt, eid)({'timeout': 1000, 'enableRateLimit': True})
            tk = ex.fetch_ticker(pair)
            res["最新价"] = tk['last']
            now_ms = ex.milliseconds()
            
            # --- 快数据：短线滚动涨幅 ---
            k1 = ex.fetch_ohlcv(pair, '1m', limit=2)
            if k1: res['1m涨跌'] = ((tk['last'] - k1[0][4]) / k1[0][4]) * 100
            
            k5 = ex.fetch_ohlcv(pair, '5m', limit=2)
            if k5: res['5m涨跌'] = ((tk['last'] - k5[0][4]) / k5[0][4]) * 100

            # --- 慢数据：精准 24h/7d 滚动 (仅在特定跳动时更新) ---
            if is_slow_update:
                # 1h
                h1 = ex.fetch_ohlcv(pair, '1m', since=now_ms - 3600000, limit=1)
                if h1: res['1h涨跌'] = ((tk['last'] - h1[0][4]) / h1[0][4]) * 100
                # 24h (滚动窗口)
                d1 = ex.fetch_ohlcv(pair, '1h', since=now_ms - 86400000, limit=1)
                if d1: res['24h涨跌'] = ((tk['last'] - d1[0][4]) / d1[0][4]) * 100
                # 7d
                w1 = ex.fetch_ohlcv(pair, '4h', since=now_ms - 604800000, limit=1)
                if w1: res['7d涨跌'] = ((tk['last'] - w1[0][4]) / w1[0][4]) * 100
            
            success_ex = eid.split('io')[0].upper()
            break
        except: continue

    # --- 大单扫描 (压缩笔数提高速度) ---
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
# 3. 主界面与调度
# ==========================================
with st.sidebar:
    st_val = st.number_input("大单阈值", value=20000)
    interval = st.slider("刷新频率", 5, 30, 10)
    st.info("💡 1h/24h/7d 滚动数据每 10 分钟深层同步一次，其余时间实时监测价格和大单。")
    countdown = st.empty()

placeholder = st.empty()

while True:
    now = time.time()
    # 核心优化：是否进行重型长周期抓取
    is_slow = False
    if now - st.session_state.last_slow_tick > 600:
        is_slow = True
        st.session_state.last_slow_tick = now

    # 并发执行 (限制线程数，防止 API 崩溃)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda s: fetch_worker(s, st_val, is_slow), SYMBOLS))

    # 更新状态
    for r in results: st.session_state.master_data[r['币种']] = r

    # 排序与展示
    df = pd.DataFrame(results)
    df['sk'] = df['1m涨跌'].apply(lambda x: x if isinstance(x, float) else -999)
    df = df.sort_values(by="sk", ascending=False)
    
    display_df = df.copy()
    for col in CH_COLS:
        display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%" if isinstance(x, float) and x != -999.0 else "·")

    with placeholder.container():
        st.write(f"🔄 刷新: {time.strftime('%H:%M:%S')} | 模式: {'[全量对齐]' if is_slow else '[极速监测]'}")
        st.dataframe(display_df[["币种", "最新价", "OBV预警"] + CH_COLS + ["OKX", "Gate", "Huobi", "Bitget"]], 
                     use_container_width=True, height=750)

    for i in range(interval, 0, -1):
        countdown.metric("下次刷新", f"{i}s")
        time.sleep(1)
