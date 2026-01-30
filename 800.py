import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="指挥部-数据校准版", layout="wide")

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "ZEC", "ASTER"]
EXCHANGES = {'OKX': 'okx', 'Bitget': 'bitget'}

def fetch_calibrated_data(symbol):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol}
    main_ex = ccxt.okx() if symbol not in ['TAO', 'HYPE'] else ccxt.bitget()
    
    try:
        # 1. 实时价格
        tk = main_ex.fetch_ticker(pair)
        curr_p = tk['last']
        res["最新价"] = curr_p
        res["24h"] = tk['percentage']

        # 2. 修正后的多周期滚动 (通过回溯不同的 limit 确保数据不重复)
        # 1m 用倒数第2根，15m 用倒数第2根，以此类推
        for label, tf, count in [("1m","1m",2), ("5m","5m",2), ("15m","15m",2), ("1h","1h",2)]:
            k = main_ex.fetch_ohlcv(pair, tf, limit=count)
            if len(k) >= count:
                base_p = k[0][4] # 取该周期前一根的收盘价
                res[label] = ((curr_p - base_p) / base_p) * 100
            else: res[label] = 0.0

        # 3. 技术指标 (RSI/MACD)
        ohlcv_raw = main_ex.fetch_ohlcv(pair, '1h', limit=50)
        df_ta = pd.DataFrame(ohlcv_raw, columns=['t','o','h','l','c','v'])
        res["RSI"] = round(ta.rsi(df_ta['c'], length=14).iloc[-1], 1)
        
        # 4. 净流计算
        trades = main_ex.fetch_trades(pair, limit=40)
        res["净流(万)"] = round(sum([(t['price']*t['amount']) if t['side']=='buy' else -(t['price']*t['amount']) for t in trades]) / 10000, 2)

        # 诊断逻辑优化
        if res["RSI"] < 20: res["战术诊断"] = "🔥 极度超卖"
        elif res["RSI"] > 80: res["战术诊断"] = "⚠️ 严重超买"
        elif res["1m"] > 0.3 and res["净流(万)"] > 10: res["战术诊断"] = "🚀 瞬时抢筹"
        else: res["战术诊断"] = "🔎 观望"
        
    except: return None
    return res

# ----------------- UI 渲染 -----------------
placeholder = st.empty()
while True:
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(fetch_calibrated_data, SYMBOLS))
    
    df = pd.DataFrame([r for r in results if r is not None])
    df = df.sort_values(by="1m", ascending=False)

    with placeholder.container():
        st.write(f"🔄 刷新时间: {time.strftime('%H:%M:%S')} | **修正说明：已强制区分 K 线偏移量**")
        
        # 视觉高亮函数
        def color_rsi(val):
            color = 'red' if val < 25 else 'green' if val > 75 else 'white'
            return f'color: {color}; font-weight: bold'

        st.dataframe(df.style.applymap(color_rsi, subset=['RSI']), use_container_width=True, height=660)
    
    time.sleep(40)
