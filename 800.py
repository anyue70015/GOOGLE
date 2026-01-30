import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置与全局持久化
# ==========================================
st.set_page_config(page_title="指挥部-全数据对齐版", layout="wide")

if 'GLOBAL_DATA' not in globals():
    globals()['GLOBAL_DATA'] = {}
if 'batch_index' not in st.session_state:
    st.session_state.batch_index = 0

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "ZEC", "ASTER"]
CH_COLS = ['1m涨跌', '5m涨跌', '15m涨跌', '1h涨跌', '4h涨跌', '24h涨跌', '7d涨跌']

# ==========================================
# 2. 核心抓取函数 (多源全自动适配)
# ==========================================
def fetch_worker(symbol, threshold):
    pair = f"{symbol}/USDT"
    master_store = globals().get('GLOBAL_DATA', {})
    res = master_store.get(symbol, {"币种": symbol, "最新价": "---", "OBV预警": "待更新"})

    # 依次尝试：OKX -> Gate -> Bitget
    # 只要在其中一家找到币，该币的所有指标都由这家提供
    found_source = False
    for eid in ['okx', 'gateio', 'bitget']:
        if found_source: break
        try:
            ex = getattr(ccxt, eid)({'timeout': 3000, 'enableRateLimit': True})
            # 1. 先验证是否有该币对
            tk = ex.fetch_ticker(pair)
            curr_p = tk['last']
            res["最新价"] = curr_p
            now_ms = ex.milliseconds()
            
            # 2. 如果验证成功，统一抓取该源的所有周期
            configs = [
                (60000, '1m涨跌', '1m'),
                (300000, '5m涨跌', '1m'),
                (900000, '15m涨跌', '5m'),
                (3600000, '1h涨跌', '1m'),
                (14400000, '4h涨跌', '15m'),
                (86400000, '24h涨跌', '1h'),
                (604800000, '7d涨跌', '4h')
            ]
            
            for offset, col, k_tf in configs:
                # 强制使用 since 对齐“此时此刻”
                k = ex.fetch_ohlcv(pair, k_tf, since=now_ms - offset, limit=1)
                if k and len(k) > 0:
                    res[col] = ((curr_p - k[0][4]) / k[0][4]) * 100
                else:
                    res[col] = -999.0 # 数据缺失标记

            source_tag = eid.replace('io','').upper()
            res['OBV预警'] = "正常" # 初始状态
            found_source = True
        except:
            continue # 如果这家没有该币，尝试下一家

    # 3. 跨交易所大单扫描 (不受主源限制)
    if found_source:
        res['net_flow'] = 0
        res['active_count'] = 0
        th = threshold if symbol in ['BTC', 'ETH'] else threshold / 5
        for name, tid in {'OKX':'okx', 'Gate':'gateio', 'Huobi':'htx', 'Bitget':'bitget'}.items():
            try:
                ex_t = getattr(ccxt, tid)({'timeout': 1000})
                trades = ex_t.fetch_trades(pair, limit=20)
                buy_v = 0
                for t in trades:
                    v = t['price'] * t['amount']
                    res['net_flow'] += v if t['side'] == 'buy' else -v
                    if t['side'] == 'buy' and v >= th: buy_v += v
                res[name] = f"{buy_v/10000:.1f}万" if buy_v > 0 else "·"
                if buy_v > 0: res['active_count'] += 1
            except:
                res[name] = "·"

        # 底背离判断逻辑
        if isinstance(res.get('1h涨跌'), float) and res['1h涨跌'] < -0.3 and res['net_flow'] > 0:
            res['OBV预警'] = f"💎底背离({source_tag})"
        else:
            res['OBV预警'] = f"正常({source_tag})"
            
    return res

# ==========================================
# 3. 分步渲染逻辑
# ==========================================
st.markdown("<style>.stDataFrame { opacity: 1.0 !important; }</style>", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ 监控配置")
    st_val = st.number_input("大单阈值 (USDT)", value=20000)
    interval = st.number_input("轮询频率 (秒)", value=40)
    countdown = st.empty()

placeholder = st.empty()

while True:
    # 每一轮处理 3 个币种
    idx = st.session_state.batch_index
    current_batch = SYMBOLS[idx : idx + 3]
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        batch_results = list(executor.map(lambda s: fetch_worker(s, st_val), current_batch))

    # 更新全局数据字典
    for r in batch_results:
        globals()['GLOBAL_DATA'][r['币种']] = r

    # 步进 batch 索引
    st.session_state.batch_index = (st.session_state.batch_index + 3) % len(SYMBOLS)

    # 汇总显示
    all_rows = [globals()['GLOBAL_DATA'].get(s, {"币种": s, "最新价": "同步中..."}) for s in SYMBOLS]
    df = pd.DataFrame(all_rows)
    
    # 排序处理
    if '1m涨跌' in df.columns:
        df['sort_val'] = df['1m涨跌'].apply(lambda x: x if isinstance(x, (int, float)) else -999)
        df = df.sort_values(by="sort_val", ascending=False).drop(columns=['sort_val'])
    
    display_df = df.copy()
    # 统一格式化
    for col in CH_COLS:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%" if isinstance(x, (int, float)) and x != -999.0 else "·")

    with placeholder.container():
        st.write(f"🔄 刷新时间: {time.strftime('%H:%M:%S')} | 正在同步: {', '.join(current_batch)}")
        # 确保列齐全
        for c in ["OKX", "Gate", "Huobi", "Bitget"] + CH_COLS:
            if c not in display_df.columns: display_df[c] = "·"
            
        final_cols = ["币种", "最新价", "OBV预警"] + CH_COLS + ["OKX", "Gate", "Huobi", "Bitget"]
        st.dataframe(display_df[final_cols], use_container_width=True, height=750)

    for i in range(interval, 0, -1):
        countdown.metric("下一组同步倒计时", f"{i}s")
        time.sleep(1)
