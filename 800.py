import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="指挥部-全量功能终极版", layout="wide")

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "ZEC", "ASTER"]
EXCHANGES = {'OKX': 'okx', 'Bitget': 'bitget', 'Gate': 'gateio', 'Huobi': 'htx'}

# ==========================================
# 2. 核心抓取：使用物理偏移隔离数据
# ==========================================
def fetch_commander_final(symbol):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol}
    main_ex_id = 'bitget' if symbol in ['TAO', 'HYPE', 'ASTER'] else 'okx'
    main_ex = getattr(ccxt, main_ex_id)({'timeout': 5000})
    
    try:
        # A. 获取实时价格
        tk = main_ex.fetch_ticker(pair)
        curr_p = tk['last']
        res["最新价"] = curr_p
        res["24h"] = tk['percentage']

        # B. 强制物理隔离逻辑：确保每一列抓的基准点都不同
        now = main_ex.milliseconds()
        # 1m: 对比 1分钟前
        # 5m: 对比 5分钟前...以此类推
        offsets = {
            "1m": 60 * 1000,
            "5m": 5 * 60 * 1000,
            "15m": 15 * 60 * 1000,
            "1h": 60 * 60 * 1000
        }

        for label, ms in offsets.items():
            # 关键：指定 since 强制抓取对应时间点的那一根 K 线
            k = main_ex.fetch_ohlcv(pair, '1m', since=now - ms - 2000, limit=1)
            if k:
                base_p = k[0][4] # 取那分钟的收盘价
                res[label] = ((curr_p - base_p) / base_p) * 100
            else:
                res[label] = 0.0

        # C. 全网净流入 (聚合四所)
        total_flow = 0.0
        for eid in EXCHANGES.values():
            try:
                ex = getattr(ccxt, eid)({'timeout': 1500})
                trades = ex.fetch_trades(pair, limit=50)
                total_flow += sum([(t['price'] * t['amount']) if t['side'] == 'buy' else -(t['price'] * t['amount']) for t in trades])
            except: continue
        res["净流入(万)"] = round(total_flow / 10000, 2)

        # D. RSI 计算 (基于 1h)
        ohlcv_1h = main_ex.fetch_ohlcv(pair, '1h', limit=30)
        df_ta = pd.DataFrame(ohlcv_1h, columns=['t','o','h','l','c','v'])
        res["RSI"] = round(ta.rsi(df_ta['c'], length=14).iloc[-1], 1)
        
        # E. 诊断
        diag = "🔎 观望"
        if res["RSI"] < 25: diag = "🛒 底部确认"
        elif res["1h"] < -2 and res["净流入(万)"] > 20: diag = "💎 强力吸筹"
        elif res["1m"] > 0.4 and res["净流入(万)"] < -10: diag = "⚠️ 诱多虚涨"
        res["战术诊断"] = diag
        
    except:
        return None
    return res

# ==========================================
# 3. UI 渲染 (严格列顺序)
# ==========================================
st.title("🛰️ 全球资产指挥部 (全功能/排序校准版)")
placeholder = st.empty()

while True:
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        results = list(executor.map(fetch_commander_final, SYMBOLS))
    
    df = pd.DataFrame([r for r in results if r is not None])
    if not df.empty:
        df = df.sort_values(by="1m", ascending=False)

    display_df = df.copy()
    
    # 严格按照你要求的顺序排列
    order = ["币种", "最新价", "战术诊断", "1m", "5m", "15m", "1h", "24h", "净流入(万)", "RSI"]
    
    # 格式化百分比
    pct_cols = ["1m", "5m", "15m", "1h", "24h"]
    for col in pct_cols:
        display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%")

    with placeholder.container():
        st.write(f"🕒 更新时间: {time.strftime('%H:%M:%S')} | **模式：物理偏移去重版**")
        
        # 样式渲染
        def style_diag(val):
            if val == "🛒 底部确认": return 'background-color: #7d0000; color: white'
            if val == "💎 强力吸筹": return 'background-color: #00005a; color: white'
            return ''

        st.dataframe(
            display_df[order].style.applymap(style_diag, subset=['战术诊断']),
            use_container_width=True, 
            height=660
        )

    time.sleep(40)
