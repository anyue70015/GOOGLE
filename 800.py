import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="资金指挥部-多源修复版", layout="wide")

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "ASTER", "ZEC"]
EXCHANGE_IDS = {'OKX': 'okx', 'Gate': 'gateio', 'Huobi': 'htx', 'Bitget': 'bitget'}
ALL_CH_COLS = ['1m涨跌', '5m涨跌', '15m涨跌', '1h涨跌', '4h涨跌', '24h涨跌', '7d涨跌']

if 'last_valid_data' not in st.session_state:
    st.session_state.last_valid_data = {}
if 'last_slow_fetch_time' not in st.session_state:
    st.session_state.last_slow_fetch_time = 0

# ==========================================
# 2. 核心抓取引擎 (优先级回退逻辑)
# ==========================================
def fetch_worker(symbol, base_threshold, history_cache, fetch_slow_data=False):
    pair = f"{symbol}/USDT"
    local_threshold = base_threshold if symbol in ['BTC', 'ETH'] else base_threshold / 4
    
    res = {
        "币种": symbol, "最新价": "NO", "OBV预警": "正常", 
        "OKX": "·", "Gate": "·", "Huobi": "·", "Bitget": "·",
        "net_flow": 0, "active_count": 0, "预警等级": 0
    }
    for col in ALL_CH_COLS: res[col] = -999.0
    if history_cache: res.update(history_cache)

    # --- 1. 价格与涨幅抓取 (OKX 为主，Gate 为备) ---
    success_fetcher = None
    for ex_id in ['OKX', 'Gate']:  # 优先级列表
        try:
            ex_obj = getattr(ccxt, EXCHANGE_IDS[ex_id])({'timeout': 2000, 'enableRateLimit': True})
            tk = ex_obj.fetch_ticker(pair)
            res["最新价"] = tk['last']
            
            # 抓取短线滚动涨幅
            for tf in ['1m', '5m', '15m']:
                ohlcv = ex_obj.fetch_ohlcv(pair, tf, limit=2)
                if len(ohlcv) >= 2:
                    res[f"{tf}涨跌"] = ((tk['last'] - ohlcv[0][4]) / ohlcv[0][4]) * 100
            
            # 如果需要慢速数据，也从当前这个成功的交易所抓
            if fetch_slow_data:
                h1 = ex_obj.fetch_ohlcv(pair, '1m', limit=61)
                if len(h1) >= 61: res["1h涨跌"] = ((tk['last'] - h1[0][4]) / h1[0][4]) * 100
                d1 = ex_obj.fetch_ohlcv(pair, '1h', limit=25)
                if len(d1) >= 25: res["24h涨跌"] = ((tk['last'] - d1[0][4]) / d1[0][4]) * 100
                w1 = ex_obj.fetch_ohlcv(pair, '4h', limit=43)
                if len(w1) >= 43: res["7d涨跌"] = ((tk['last'] - w1[0][4]) / w1[0][4]) * 100
            
            success_fetcher = ex_id
            break # 只要抓到一个成功的，就不再尝试下一个交易所
        except:
            continue

    # --- 2. 大单扫描 (依然全量扫描，不受上述优先级限制) ---
    for name, eid in EXCHANGE_IDS.items():
        try:
            ex_trade = getattr(ccxt, eid)({'timeout': 1200, 'enableRateLimit': True})
            trades = ex_trade.fetch_trades(pair, limit=50)
            buy_sum = 0
            for t in trades:
                val = t['price'] * t['amount']
                res['net_flow'] += val if t['side'] == 'buy' else -val
                if t['side'] == 'buy' and val >= local_threshold: buy_sum += val
            res[name] = f"{buy_sum/10000:.1f}万" if buy_sum > 0 else "·"
            if buy_sum > 0: res['active_count'] += 1
        except:
            pass

    # 1h 滚动底背离
    if isinstance(res.get('1h涨跌'), float) and res['1h涨跌'] < -0.3 and res['net_flow'] > 0:
        res['OBV预警'] = f"💎底背离({success_fetcher})"
    else:
        res['OBV预警'] = f"正常({success_fetcher})" if success_fetcher else "无源"

    return res

# ==========================================
# 3. 渲染逻辑 (保持极速版优化)
# ==========================================
st.title("🏹 资金指挥部 - 多源智能补全版")

with st.sidebar:
    st_val = st.number_input("大单阈值", value=20000)
    interval = st.slider("刷新间隔", 10, 60, 20)
    countdown_area = st.empty()

placeholder = st.empty()

while True:
    now_t = time.time()
    should_fetch_slow = False
    if now_t - st.session_state.last_slow_fetch_time > 300:
        should_fetch_slow = True
        st.session_state.last_slow_fetch_time = now_t

    current_cache = {s: st.session_state.last_valid_data.get(s) for s in SYMBOLS}
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda s: fetch_worker(s, st_val, current_cache[s], should_fetch_slow), SYMBOLS))
    
    for r in results:
        sym = r['币种']
        st.session_state.last_valid_data[sym] = r 
    
    df = pd.DataFrame(results)
    final_cols = ["币种", "最新价", "OBV预警"] + ALL_CH_COLS + ["OKX", "Gate", "Huobi", "Bitget"]
    for c in final_cols:
        if c not in df.columns: df[c] = "NO"
    
    # 排序与显示
    df['sort_key'] = df['1m涨跌'].apply(lambda x: x if isinstance(x, float) else -999.0)
    df = df.sort_values(by="sort_key", ascending=False).drop(columns=['sort_key'])
    display_df = df.copy()
    for col in ALL_CH_COLS:
        display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%" if isinstance(x, float) and x != -999.0 else "NO")

    with placeholder.container():
        st.write(f"🔄 刷新时间: {time.strftime('%H:%M:%S')} | TAO/HYPE 等已自动适配 Gate 行情")
        st.dataframe(display_df[final_cols], use_container_width=True, height=800)

    for i in range(interval, 0, -1):
        countdown_area.metric("⏰ 刷新倒计时", f"{i} 秒")
        time.sleep(1)
