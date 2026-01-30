import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置与全局存储
# ==========================================
st.set_page_config(page_title="指挥部-Bitget强化版", layout="wide")

if 'GLOBAL_DATA' not in globals():
    globals()['GLOBAL_DATA'] = {}
if 'batch_index' not in st.session_state:
    st.session_state.batch_index = 0

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "ZEC", "ASTER"]
CH_COLS = ['1m涨跌', '5m涨跌', '15m涨跌', '1h涨跌', '4h涨跌', '24h涨跌', '7d涨跌']

# ==========================================
# 2. 增强型抓取 (Bitget 优先逻辑)
# ==========================================
def fetch_worker(symbol, threshold):
    pair = f"{symbol}/USDT"
    master_store = globals().get('GLOBAL_DATA', {})
    res = master_store.get(symbol, {"币种": symbol, "最新价": "---", "OBV预警": "同步中"})

    found_source = False
    # 调整优先级：OKX -> Bitget (针对 TAO/ZEC 更稳) -> Gate
    for eid in ['okx', 'bitget', 'gateio']:
        if found_source: break
        try:
            ex = getattr(ccxt, eid)({'timeout': 3000, 'enableRateLimit': True})
            tk = ex.fetch_ticker(pair)
            curr_p = tk['last']
            res["最新价"] = curr_p
            now_ms = ex.milliseconds()
            
            # 滚动周期配置 (修正：如果 since 失败，自动使用 limit 回溯)
            configs = [
                (60000, '1m涨跌', '1m', 2),
                (300000, '5m涨跌', '5m', 2),
                (900000, '15m涨跌', '15m', 2),
                (3600000, '1h涨跌', '1h', 2),
                (14400000, '4h涨跌', '4h', 2),
                (86400000, '24h涨跌', '1h', 26), # 24h 前
                (604800000, '7d涨跌', '4h', 45)  # 7d 前
            ]
            
            for offset, col, k_tf, k_limit in configs:
                try:
                    # 尝试精准时间回溯
                    k = ex.fetch_ohlcv(pair, k_tf, since=now_ms - offset - 10000, limit=1)
                    if not k or len(k) == 0:
                        # 备选：靠根数回溯
                        k = ex.fetch_ohlcv(pair, k_tf, limit=k_limit)
                    
                    if k:
                        base_p = k[0][4]
                        res[col] = ((curr_p - base_p) / base_p) * 100
                    else:
                        res[col] = -999.0
                except:
                    res[col] = -999.0

            res['OBV预警'] = f"正常({eid.replace('io','').upper()})"
            found_source = True
        except:
            continue

    # 3. 大单扫描
    if found_source:
        res['net_flow'] = 0
        th = threshold if symbol in ['BTC', 'ETH'] else threshold / 5
        for name, tid in {'OKX':'okx', 'Gate':'gateio', 'Huobi':'htx', 'Bitget':'bitget'}.items():
            try:
                ex_t = getattr(ccxt, tid)({'timeout': 1000})
                trades = ex_t.fetch_trades(pair, limit=15)
                buy_v = 0
                for t in trades:
                    v = t['price'] * t['amount']
                    res['net_flow'] += v if t['side'] == 'buy' else -v
                    if t['side'] == 'buy' and v >= th: buy_v += v
                res[name] = f"{buy_v/10000:.1f}万" if buy_v > 0 else "·"
            except:
                res[name] = "·"
                
    return res

# ==========================================
# 3. UI 调度
# ==========================================
st.markdown("<style>.stDataFrame { opacity: 1.0 !important; }</style>", unsafe_allow_html=True)

with st.sidebar:
    st_val = st.number_input("大单阈值", value=20000)
    interval = st.number_input("轮询频率(秒)", value=40)
    countdown = st.empty()

placeholder = st.empty()

while True:
    idx = st.session_state.batch_index
    current_batch = SYMBOLS[idx : idx + 3]
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        batch_results = list(executor.map(lambda s: fetch_worker(s, st_val), current_batch))

    for r in batch_results:
        globals()['GLOBAL_DATA'][r['币种']] = r

    st.session_state.batch_index = (st.session_state.batch_index + 3) % len(SYMBOLS)

    all_rows = [globals()['GLOBAL_DATA'].get(s, {"币种": s, "最新价": "同步中..."}) for s in SYMBOLS]
    df = pd.DataFrame(all_rows)
    
    if '1m涨跌' in df.columns:
        df['sort_val'] = df['1m涨跌'].apply(lambda x: x if isinstance(x, (int, float)) else -999)
        df = df.sort_values(by="sort_val", ascending=False).drop(columns=['sort_val'])
    
    display_df = df.copy()
    for col in CH_COLS:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%" if isinstance(x, (int, float)) and x != -999.0 else "·")

    with placeholder.container():
        st.write(f"🔄 刷新时间: {time.strftime('%H:%M:%S')} | 同步: {', '.join(current_batch)}")
        final_cols = ["币种", "最新价", "OBV预警"] + CH_COLS + ["OKX", "Gate", "Huobi", "Bitget"]
        for c in final_cols:
            if c not in display_df.columns: display_df[c] = "·"
        st.dataframe(display_df[final_cols], use_container_width=True, height=750)

    for i in range(interval, 0, -1):
        countdown.metric("下次同步", f"{i}s")
        time.sleep(1)
