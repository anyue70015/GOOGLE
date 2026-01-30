import streamlit as st
import pandas as pd
import ccxt
import time
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="指挥部-全时段逻辑版", layout="wide")

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "ZEC", "ASTER"]
EXCHANGES = {'OKX': 'okx', 'Bitget': 'bitget', 'Gate': 'gateio', 'Huobi': 'htx'}

# ==========================================
# 2. 技术指标：1h/15m 深度计算
# ==========================================
def get_advanced_indicators(ex, pair, curr_p):
    try:
        # 获取 1h 数据做大趋势参考
        ohlcv_1h = ex.fetch_ohlcv(pair, '1h', limit=30)
        if len(ohlcv_1h) < 20: return "·", "0%", 0.0
        
        closes = np.array([x[4] for x in ohlcv_1h])
        highs = np.array([x[2] for x in ohlcv_1h])
        lows = np.array([x[3] for x in ohlcv_1h])
        
        # OBV (1h 级别趋势)：判断主力资金底色
        obv_status = "💎流入" if curr_p > closes[-1] else "💀流出"
        
        # ATR (1h 级别波动率)：多大算大？(计算 ATR/Price 比例)
        tr = np.maximum(highs[1:] - lows[1:], np.maximum(abs(highs[1:] - closes[:-1]), abs(lows[1:] - closes[:-1])))
        atr_val = np.mean(tr[-14:])
        atr_pct = (atr_val / curr_p) * 100
        
        return obv_status, f"{atr_pct:.2f}%", atr_pct
    except:
        return "·", "0%", 0.0

# ==========================================
# 3. 核心抓取函数
# ==========================================
def fetch_commander_data(symbol):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol}
    
    # 四所资金流聚合
    total_flow = 0.0
    prices = []
    
    # TAO/HYPE 这种币，OBV 和 ATR 必须看 Bitget
    main_ex_id = 'bitget' if symbol in ['TAO', 'HYPE', 'ASTER', 'ZEC'] else 'okx'
    main_ex = getattr(ccxt, main_ex_id)({'timeout': 3000})

    for name, eid in EXCHANGES.items():
        try:
            ex = getattr(ccxt, eid)({'timeout': 2000})
            tk = ex.fetch_ticker(pair)
            prices.append(tk['last'])
            # 实时吃单聚合 (多所联动)
            trades = ex.fetch_trades(pair, limit=20)
            total_flow += sum([(t['price'] * t['amount']) if t['side'] == 'buy' else -(t['price'] * t['amount']) for t in trades])
        except: continue

    if not prices: return None
    
    avg_price = sum(prices) / len(prices)
    res["最新价"] = avg_price
    res["聚合净流(万)"] = round(total_flow / 10000, 2)
    
    # 写入你要求的 1h OBV 和 1h ATR 逻辑
    res["OBV(1h)"], res["ATR波幅(1h)"], raw_atr = get_advanced_indicators(main_ex, pair, avg_price)
    
    # 写入多周期涨跌 (1m, 5m, 15m, 1h, 24h)
    for label, tf in {'1m':'1m', '5m':'5m', '15m':'15m', '1h':'1h', '24h':'1d'}.items():
        try:
            k = main_ex.fetch_ohlcv(pair, tf, limit=2)
            res[label] = ((avg_price - k[0][4]) / k[0][4] * 100) if len(k)>=2 else 0.0
        except: res[label] = 0.0
        
    return res

# ==========================================
# 4. 实时指挥部页面
# ==========================================
st.title("🛰️ 全网聚合监测站 (1h逻辑/1m排序版)")

placeholder = st.empty()

while True:
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        results = list(executor.map(fetch_commander_data, SYMBOLS))
    
    df = pd.DataFrame([r for r in results if r is not None])
    
    # --- 核心要求：按 1分钟 涨幅排最前面 ---
    df = df.sort_values(by="1m", ascending=False)

    display_df = df.copy()
    pct_cols = ["1m", "5m", "15m", "1h", "24h"]
    for c in pct_cols:
        display_df[c] = display_df[c].apply(lambda x: f"{x:+.2f}%")

    with placeholder.container():
        st.write(f"🕒 更新: {time.strftime('%H:%M:%S')} | **OBV/ATR 窗口: 1h** | **排序参考: 1m**")
        
        # 18 个币一屏全显
        st.dataframe(
            display_df[["币种", "最新价", "1m", "5m", "15m", "1h", "24h", "聚合净流(万)", "OBV(1h)", "ATR波幅(1h)"]],
            use_container_width=True,
            height=660
        )
        
        # 联动报警逻辑
        if not df.empty:
            top_1m = df.iloc[0]
            if top_1m['1m'] > 0.8:
                st.success(f"⚡ 捕捉到急速反弹: {top_1m['币种']} 1分钟暴涨 {top_1m['1m']:.2f}%！")
            
            # TAO 专项：如果 1m 在跌，且 1h OBV 是流出
            tao_row = df[df['币种'] == 'TAO']
            if not tao_row.empty and tao_row.iloc[0]['1m'] < -0.5 and tao_row.iloc[0]['OBV(1h)'] == "💀流出":
                st.error(f"🚨 TAO 危险信号：1分钟加速下跌，且 1h 主力资金持续流出！")

    time.sleep(10)
