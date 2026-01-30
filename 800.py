import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置与全局持久化
# ==========================================
st.set_page_config(page_title="指挥部-分批轮询版", layout="wide")

# 全局存储，用于合并分批抓取的结果
if 'GLOBAL_DATA' not in globals():
    globals()['GLOBAL_DATA'] = {}
# 记录当前轮询到第几组了
if 'batch_index' not in st.session_state:
    st.session_state.batch_index = 0

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "ZEC", "ASTER"]
CH_COLS = ['1m涨跌', '5m涨跌', '15m涨跌', '1h涨跌', '4h涨跌', '24h涨跌', '7d涨跌']

# ==========================================
# 2. 核心抓取函数 (完全滚动对齐)
# ==========================================
def fetch_worker(symbol, threshold):
    pair = f"{symbol}/USDT"
    # 获取此币种之前的旧数据（如有）
    master_store = globals().get('GLOBAL_DATA', {})
    res = master_store.get(symbol, {
        "币种": symbol, "最新价": "---", "OBV预警": "待更新",
        "OKX": "·", "Gate": "·", "Huobi": "·", "Bitget": "·",
        "net_flow": 0, "active_count": 0
    })

    for eid in ['okx', 'gateio', 'bitget']:
        try:
            ex = getattr(ccxt, eid)({'timeout': 2500, 'enableRateLimit': True})
            tk = ex.fetch_ticker(pair)
            curr_p = tk['last']
            res["最新价"] = curr_p
            now_ms = ex.milliseconds()
            
            # 精准计算所有滚动周期 (不再受8点收盘限制)
            # 配置：(周期, 回溯毫秒, 对应列名, 使用K线级别)
            configs = [
                ('1m', 60000, '1m涨跌', '1m'),
                ('5m', 300000, '5m涨跌', '1m'),
                ('15m', 900000, '15m涨跌', '5m'),
                ('1h', 3600000, '1h涨跌', '1m'),
                ('4h', 14400000, '4h涨跌', '15m'),
                ('24h', 86400000, '24h涨跌', '1h'),
                ('7d', 604800000, '7d涨跌', '4h')
            ]
            
            for tf_param, offset, col, k_tf in configs:
                k = ex.fetch_ohlcv(pair, k_tf, since=now_ms - offset, limit=1)
                if k: res[col] = ((curr_p - k[0][4]) / k[0][4]) * 100
            
            # 大单扫描
            res['active_count'] = 0
            res['net_flow'] = 0
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
                except: res[name] = "·"

            res['OBV预警'] = f"💎底背离" if (isinstance(res.get('1h涨跌'), float) and res['1h涨跌'] < -0.3 and res['net_flow'] > 0) else "正常"
            break # 只要一个交易所成功就停止
        except: continue
    
    return res

# ==========================================
# 3. 分批调度逻辑
# ==========================================
st.markdown("<style>.stDataFrame { opacity: 1.0 !important; }</style>", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ 监控配置")
    st_val = st.number_input("大单阈值 (USDT)", value=20000)
    interval = st.number_input("轮询频率 (秒)", value=40)
    st.info("💡 模式：每轮精细化抓取 3 个币种，6 轮完成全币种覆盖。")
    countdown = st.empty()

placeholder = st.empty()

while True:
    # 1. 计算本轮要抓取的 3 个币种
    start = st.session_state.batch_index
    end = start + 3
    current_batch = SYMBOLS[start:end]
    
    # 2. 执行本轮抓取
    with ThreadPoolExecutor(max_workers=3) as executor:
        batch_results = list(executor.map(lambda s: fetch_worker(s, st_val), current_batch))

    # 3. 将结果合并回全局存储
    for r in batch_results:
        globals()['GLOBAL_DATA'][r['币种']] = r

    # 4. 更新下一轮的起始索引
    st.session_state.batch_index = (st.session_state.batch_index + 3) % len(SYMBOLS)

    # 5. 准备显示：从全局存储中取出所有币种的数据
    all_results = [globals()['GLOBAL_DATA'].get(s, {"币种": s, "最新价": "等待同步..."}) for s in SYMBOLS]
    df = pd.DataFrame(all_results)
    
    # 排序：按 1m 涨幅（如果有数据的话）
    if '1m涨跌' in df.columns:
        df['sk'] = df['1m涨跌'].apply(lambda x: x if isinstance(x, float) else -999)
        df = df.sort_values(by="sk", ascending=False).drop(columns=['sk'])
    
    # 格式化显示
    display_df = df.copy()
    for col in CH_COLS:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%" if isinstance(x, float) and x != -999.0 else "·")

    with placeholder.container():
        st.write(f"🔄 刷新时间: {time.strftime('%H:%M:%S')} | 本轮同步: {', '.join(current_batch)}")
        # 补齐可能缺失的列以防报错
        for c in ["OKX", "Gate", "Huobi", "Bitget"] + CH_COLS:
            if c not in display_df.columns: display_df[c] = "·"
        
        st.dataframe(display_df[["币种", "最新价", "OBV预警"] + CH_COLS + ["OKX", "Gate", "Huobi", "Bitget"]], 
                     use_container_width=True, height=750)

    # 倒计时
    for i in range(interval, 0, -1):
        countdown.metric("下次同步 (3个新币)", f"{i}s")
        time.sleep(1)
