import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="指挥部-OBV+ATR终极版", layout="wide")

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "ZEC", "ASTER"]
EXCHANGES = {'OKX': 'okx', 'Bitget': 'bitget', 'Gate': 'gateio', 'Huobi': 'htx'}

# ==========================================
# 2. 诊断引擎：OBV/ATR/RSI 逻辑合成
# ==========================================
def get_tactical_logic(df, curr_p, flow, rsi):
    # 计算 ATR (14)
    atr_series = ta.atr(df['h'], df['l'], df['c'], length=14)
    atr_val = atr_series.iloc[-1]
    atr_pct = (atr_val / curr_p) * 100
    
    # 计算 OBV
    obv_series = ta.obv(df['c'], df['v'])
    # OBV 趋势：最近 3 根 K 线的斜率
    obv_trend = "UP" if obv_series.iloc[-1] > obv_series.iloc[-2] else "DOWN"
    
    # 诊断核心
    diag = "🔎 观望"
    
    # 1. 抄底条件：超卖 + OBV 资金流入确认
    if rsi < 25 and obv_trend == "UP":
        diag = "🛒 底部吸筹(分批)"
    
    # 2. 跑路条件：ATR 暴增(变盘) + 净流出大幅破位
    elif atr_pct > 5.0 and flow < -50:
        diag = "💀 危险！放量破位"
    
    # 3. 诱多跑路：价格微涨但 OBV 持续背离下跌
    elif obv_trend == "DOWN" and rsi > 70:
        diag = "⚠️ 诱多(快闪)"
        
    # 4. 极端暴震：ATR 极高
    elif atr_pct > 7.0:
        diag = "⚡ 极端插针"
        
    return diag, round(atr_pct, 2), obv_trend

# ==========================================
# 3. 数据抓取与时间偏移校准
# ==========================================
def fetch_full_commander(symbol):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol}
    main_ex_id = 'bitget' if symbol in ['TAO', 'HYPE', 'ASTER'] else 'okx'
    main_ex = getattr(ccxt, main_ex_id)({'timeout': 5000})
    
    try:
        tk = main_ex.fetch_ticker(pair)
        curr_p = tk['last']
        res["最新价"] = curr_p
        res["24h"] = tk['percentage']

        # A. 物理隔离周期 (1m, 5m, 15m, 1h)
        now = main_ex.milliseconds()
        offsets = {"1m": 60*1000, "5m": 300*1000, "15m": 900*1000, "1h": 3600*1000}
        for label, ms in offsets.items():
            k = main_ex.fetch_ohlcv(pair, '1m', since=now - ms - 2000, limit=1)
            res[label] = ((curr_p - k[0][4]) / k[0][4] * 100) if k else 0.0

        # B. 全网净流入 (聚合)
        total_flow = 0.0
        for eid in EXCHANGES.values():
            try:
                ex = getattr(ccxt, eid)({'timeout': 1500})
                trades = ex.fetch_trades(pair, limit=50)
                total_flow += sum([(t['price']*t['amount']) if t['side']=='buy' else -(t['price']*t['amount']) for t in trades])
            except: continue
        res["净流入(万)"] = round(total_flow / 10000, 2)

        # C. 指标合成诊断
        ohlcv_raw = main_ex.fetch_ohlcv(pair, '1h', limit=40)
        df = pd.DataFrame(ohlcv_raw, columns=['t','o','h','l','c','v'])
        rsi_val = ta.rsi(df['c'], length=14).iloc[-1]
        res["RSI"] = round(rsi_val, 1)
        
        # 整合 OBV/ATR 诊断
        diag, atr_p, obv_t = get_tactical_logic(df, curr_p, res["净流入(万)"], rsi_val)
        res["战术诊断"] = diag
        res["ATR%"] = atr_p
        res["OBV"] = "💎流入" if obv_t == "UP" else "💀流出"
        
    except: return None
    return res

# ==========================================
# 4. 自动排序与渲染
# ==========================================
st.title("🛰️ 全球资产实战指挥部 (OBV+ATR 决策版)")
placeholder = st.empty()

while True:
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        results = list(executor.map(fetch_full_commander, SYMBOLS))
    
    df = pd.DataFrame([r for r in results if r is not None])
    if not df.empty:
        df = df.sort_values(by="1m", ascending=False)

    display_df = df.copy()
    # 严格按照你要求的顺序排列
    order = ["币种", "最新价", "战术诊断", "1m", "5m", "15m", "1h", "24h", "净流入(万)", "RSI", "ATR%", "OBV"]
    for col in ["1m", "5m", "15m", "1h", "24h"]:
        display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%")

    with placeholder.container():
        st.write(f"📊 **策略全开** | 刷新: 40s | **诊断逻辑：RSI+OBV+ATR 综合决策**")
        
        def color_rule(val):
            if val == "🛒 底部吸筹(分批)": return 'background-color: #900; color: white'
            if val == "💀 危险！放量破位": return 'background-color: #ff4b4b; color: black'
            if val == "💎流入": return 'color: #00ff00'
            return ''

        st.dataframe(display_df[order].style.applymap(color_rule), use_container_width=True, height=660)

    time.sleep(40)
