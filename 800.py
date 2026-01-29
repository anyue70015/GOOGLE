import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="2026 资金预警指挥部", layout="wide")

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP"]
EXCHANGE_IDS = {'OKX': 'okx', 'Gate': 'gateio', 'Huobi': 'htx', 'Bitget': 'bitget'}
TFS = ['1m', '5m', '15m', '1h']

# 初始化信号记忆字典 (存储币种触发变色的时间戳)
if 'signal_memory' not in st.session_state:
    st.session_state.signal_memory = {sym: {"level": 0, "time": 0} for sym in SYMBOLS}

# ==========================================
# 2. 核心抓取逻辑
# ==========================================
def fetch_symbol_data(symbol, big_val_threshold):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol, "最新价": "N/A"}
    for tf in TFS: res[f"{tf}涨跌"] = "0.00%"
    res.update({'OKX': '·', 'Gate': '·', 'Huobi': '·', 'Bitget': '·', '净流入(万)': 0.0, 'raw_1m': 0})
    
    total_net_flow = 0
    active_ex_count = 0
    
    # --- A. 获取价格与涨幅 (OKX/Gate) ---
    found_base = False
    for ex_id in ['OKX', 'Gate']:
        if found_base: break
        try:
            ex = getattr(ccxt, EXCHANGE_IDS[ex_id])({'timeout': 6000, 'enableRateLimit': True})
            ticker = ex.fetch_ticker(pair)
            res["最新价"] = f"{ticker['last']}"
            for tf in TFS:
                ohlcv = ex.fetch_ohlcv(pair, tf, limit=2)
                if len(ohlcv) >= 2:
                    ch = ((ohlcv[-1][4] - ohlcv[-1][1]) / ohlcv[-1][1]) * 100
                    res[f"{tf}涨跌"] = f"{ch:+.2f}%"
                    if tf == '1m': res['raw_1m'] = ch
            found_base = True
        except: continue

    # --- B. 扫描各交易所大单 ---
    for name, eid in EXCHANGE_IDS.items():
        try:
            ex = getattr(ccxt, eid)({'timeout': 5000, 'enableRateLimit': True})
            trades = ex.fetch_trades(pair, limit=20)
            big_buy_sum = sum((t['price'] * t['amount']) for t in trades 
                              if t['side'] == 'buy' and (t['price'] * t['amount']) >= big_val_threshold)
            for t in trades:
                total_net_flow += (t['price'] * t['amount']) * (1 if t['side'] == 'buy' else -1)

            if big_buy_sum > 0:
                active_ex_count += 1
                res[name] = f"{big_buy_sum/10000:.1f}万"
        except: res[name] = "⚠️"

    res["净流入(万)"] = round(total_net_flow / 10000, 1)

    # --- C. 变色逻辑判断 ---
    current_time = time.time()
    level = 0
    if res['raw_1m'] >= 0.5:
        level = 1 # 浅黄
        if active_ex_count == 2: level = 2 # 深黄
        if active_ex_count >= 3: level = 3 # 橘黄/最深
    
    # 信号记忆：如果当前级别更高，更新记忆；如果当前级别低，但记忆未过期(15分钟)，保留记忆
    if level > 0:
        st.session_state.signal_memory[symbol] = {"level": level, "time": current_time}
    
    # 检查记忆是否过期 (900秒 = 15分钟)
    mem = st.session_state.signal_memory[symbol]
    if current_time - mem['time'] < 900:
        res["预警等级"] = mem['level']
    else:
        res["预警等级"] = 0
    
    return res

# ==========================================
# 3. 界面逻辑
# ==========================================
st.title("🏹 渐进式资金预警指挥部")

with st.sidebar:
    st.header("⚙️ 配置")
    big_val = st.number_input("大单阈值 (USDT)", value=20000, step=5000)
    interval = st.slider("扫描间隔 (秒)", 10, 120, 40)
    st.divider()
    st.write("🎨 **预警说明 (信号保留15分钟)**：")
    st.write("🟡 浅黄：1m 涨跌 >= 0.5%")
    st.write("🟠 中黄：1m >= 0.5% + 2家大单")
    st.write("🔴 深橘：1m >= 0.5% + 3家及以上大单")

placeholder = st.empty()
countdown_placeholder = st.sidebar.empty()

while True:
    # 1. 执行抓取
    data_list = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(fetch_symbol_data, sym, big_val) for sym in SYMBOLS]
        for f in futures:
            try:
                result = f.result()
                if result: data_list.append(result)
            except: pass

    # 2. 渲染表格
    if data_list:
        df = pd.DataFrame(data_list).sort_values("raw_1m", ascending=False).drop(columns=['raw_1m'])
        with placeholder.container():
            st.write(f"⏱️ 更新于: {time.strftime('%H:%M:%S')} | 绿涨红跌 | 信号锁定期: 15min")
            
            def row_style(row):
                lvl = row['预警等级']
                if lvl == 3: # 最深 (3家以上)
                    return ['background-color: #FF8C00; color: white; font-weight: bold'] * len(row)
                if lvl == 2: # 中等 (2家)
                    return ['background-color: #FFD700; color: black; font-weight: bold'] * len(row)
                if lvl == 1: # 浅 (0.5%)
                    return ['background-color: #FFFACD; color: black'] * len(row)
                return [''] * len(row)

            def color_ch(val):
                if not isinstance(val, str): return ''
                if '+' in val: return 'color: #28a745; font-weight: bold'
                if '-' in val: return 'color: #dc3545; font-weight: bold'
                return ''

            st.dataframe(
                df.style.apply(row_style, axis=1)
                        .applymap(color_ch, subset=[f"{tf}涨跌" for tf in TFS]),
                use_container_width=True, height=600
            )

    # 3. 精确倒计时
    for i in range(interval, 0, -1):
        countdown_placeholder.warning(f"🕒 下次扫描倒计时: {i} 秒")
        time.sleep(1)
