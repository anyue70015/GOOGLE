import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置与缓存初始化
# ==========================================
st.set_page_config(page_title="指挥部-稳定版", layout="wide")

# 必须在主线程初始化的缓存
if 'data_store' not in st.session_state:
    st.session_state.data_store = {}
if 'last_slow_update' not in st.session_state:
    st.session_state.last_slow_update = 0

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "ZEC", "ASTER"]
EXCHANGES = ['okx', 'gateio', 'bitget']
CH_COLS = ['1m涨跌', '5m涨跌', '15m涨跌', '1h涨跌', '4h涨跌', '24h涨跌', '7d涨跌']

# ==========================================
# 2. 核心抓取函数 (增加超时控制)
# ==========================================
def get_rolling_change(ex, pair, now_ms, timeframe, offset_ms):
    """精准滚动涨幅计算"""
    try:
        # since 必须精准对齐，limit=1 减少传输量
        k = ex.fetch_ohlcv(pair, timeframe, since=now_ms - offset_ms, limit=1)
        return k[0][4] if k else None
    except:
        return None

def fetch_symbol_data(symbol, base_threshold, slow_mode):
    pair = f"{symbol}/USDT"
    # 获取历史数据作为基准
    res = st.session_state.data_store.get(symbol, {
        "币种": symbol, "最新价": "加载中", "OBV预警": "初始化",
        "OKX": "·", "Gate": "·", "Huobi": "·", "Bitget": "·",
        "net_flow": 0, "active_count": 0
    })
    for col in CH_COLS: 
        if col not in res: res[col] = -999.0

    # 优先取数逻辑
    success_ex_name = None
    for eid in EXCHANGES:
        try:
            ex = getattr(ccxt, eid)({'timeout': 1200, 'enableRateLimit': True})
            tk = ex.fetch_ticker(pair)
            curr_p = tk['last']
            res["最新价"] = curr_p
            now_ms = ex.milliseconds()
            
            # 短周期：每一轮都刷
            k1m = ex.fetch_ohlcv(pair, '1m', limit=2)
            if k1m: res['1m涨跌'] = ((curr_p - k1m[0][4]) / k1m[0][4]) * 100
            
            k5m = ex.fetch_ohlcv(pair, '5m', limit=2)
            if k5m: res['5m涨跌'] = ((curr_p - k5m[0][4]) / k5m[0][4]) * 100

            # 长周期：仅在 slow_mode 开启时刷新 (减少 API 压力)
            if slow_mode:
                # 近1h (1m周期)
                p_1h = get_rolling_change(ex, pair, now_ms, '1m', 3600000)
                if p_1h: res['1h涨跌'] = ((curr_p - p_1h) / p_1h) * 100
                
                # 近24h (1h周期) - 彻底解决8点问题
                p_24h = get_rolling_change(ex, pair, now_ms, '1h', 86400000)
                if p_24h: res['24h涨跌'] = ((curr_p - p_24h) / p_24h) * 100
                
                # 近7d (4h周期)
                p_7d = get_rolling_change(ex, pair, now_ms, '4h', 604800000)
                if p_7d: res['7d涨跌'] = ((curr_p - p_7d) / p_7d) * 100

            success_ex_name = eid.replace('io','')
            break
        except: continue

    # 大单流向扫描
    res['net_flow'] = 0
    res['active_count'] = 0
    th = base_threshold if symbol in ['BTC', 'ETH'] else base_threshold / 5
    
    for name, eid in {'OKX':'okx', 'Gate':'gateio', 'Huobi':'htx', 'Bitget':'bitget'}.items():
        try:
            ex_t = getattr(ccxt, eid)({'timeout': 800})
            trades = ex_t.fetch_trades(pair, limit=20)
            buy_v = 0
            for t in trades:
                v = t['price'] * t['amount']
                res['net_flow'] += v if t['side'] == 'buy' else -v
                if t['side'] == 'buy' and v >= th: buy_v += v
            res[name] = f"{buy_v/10000:.1f}万" if buy_v > 0 else "·"
            if buy_v > 0: res['active_count'] += 1
        except: res[name] = "·"

    res['OBV预警'] = f"💎底背离({success_ex_name})" if (isinstance(res.get('1h涨跌'), float) and res['1h涨跌'] < -0.3 and res['net_flow'] > 0) else f"正常({success_ex_name})"
    
    return res

# ==========================================
# 3. UI 渲染逻辑
# ==========================================
st.title("🏹 资金指挥部 - 零延迟版")

with st.sidebar:
    st_val = st.number_input("大单阈值", value=20000)
    interval = st.slider("刷新频率 (秒)", 5, 60, 15)
    st.write("注：长周期数据(24h/7d)每10分钟同步一次")
    countdown = st.empty()

placeholder = st.empty()

while True:
    now = time.time()
    # 判定是否需要更新 24h/7d 等慢速数据 (每 600 秒一次)
    is_slow = False
    if now - st.session_state.last_slow_update > 600:
        is_slow = True
        st.session_state.last_slow_update = now

    # 使用多线程执行，max_workers 限制在 10 以内防止被封 IP
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(fetch_symbol_data, s, st_val, is_slow) for s in SYMBOLS]
        results = [f.result() for f in futures]

    # 更新全局缓存
    for r in results:
        st.session_state.data_store[r['币种']] = r

    # 数据处理
    df = pd.DataFrame(results)
    df['sort_key'] = df['1m涨跌'].apply(lambda x: x if isinstance(x, float) else -999.0)
    df = df.sort_values(by="sort_key", ascending=False)
    
    # 格式化
    display_df = df.copy()
    for col in CH_COLS:
        display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%" if isinstance(x, float) and x != -999.0 else "·")

    with placeholder.container():
        st.write(f"🔄 刷新时间: {time.strftime('%H:%M:%S')} | 状态: {'[全量同步]' if is_slow else '[极速模式]'}")
        cols_to_show = ["币种", "最新价", "OBV预警"] + CH_COLS + ["OKX", "Gate", "Huobi", "Bitget"]
        st.dataframe(display_df[cols_to_show], use_container_width=True, height=700)

    for i in range(interval, 0, -1):
        countdown.metric("下次刷新", f"{i}s")
        time.sleep(1)
