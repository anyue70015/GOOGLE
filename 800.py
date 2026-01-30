import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="指挥部-终极整合版", layout="wide")

# 确保 18 个币种定义完整
SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "ZEC", "ASTER"]
EXCHANGES = {'OKX': 'okx', 'Bitget': 'bitget', 'Gate': 'gateio', 'Huobi': 'htx'}

# ==========================================
# 2. 诊断引擎：OBV/ATR/RSI/MACD 逻辑合成
# ==========================================
def get_tactical_logic(df, curr_p, flow, rsi):
    # 计算 ATR (14)
    atr_series = ta.atr(df['h'], df['l'], df['c'], length=14)
    atr_val = atr_series.iloc[-1] if atr_series is not None else 0
    atr_pct = (atr_val / curr_p) * 100 if curr_p != 0 else 0
    
    # 计算 OBV
    obv_series = ta.obv(df['c'], df['v'])
    obv_trend = "UP" if obv_series.iloc[-1] > obv_series.iloc[-2] else "DOWN"
    
    # 计算 MACD
    macd = ta.macd(df['c'])
    macd_status = "金叉" if macd['MACDh_12_26_9'].iloc[-1] > 0 else "死叉"
    
    # 诊断核心
    diag = "🔎 观望"
    
    # 1. 抄底条件：超卖 + OBV 资金流入确认 + 1m不阴跌
    if rsi < 25 and obv_trend == "UP":
        diag = "🛒 底部吸筹"
    
    # 2. 跑路条件：ATR 暴增(变盘) + MACD死叉 + 大幅流出
    elif atr_pct > 5.0 and macd_status == "死叉" and flow < -50:
        diag = "💀 确认破位"
    
    # 3. 诱多跑路：价格高位但 OBV 持续背离下跌
    elif obv_trend == "DOWN" and rsi > 70:
        diag = "⚠️ 诱多虚涨"
        
    return diag, round(atr_pct, 2), "💎流入" if obv_trend == "UP" else "💀流出"

# ==========================================
# 3. 核心抓取：物理隔离 + 净流聚合
# ==========================================
def fetch_commander_data(symbol):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol}
    main_ex_id = 'bitget' if symbol in ['TAO', 'HYPE', 'ASTER', 'ZEC'] else 'okx'
    main_ex = getattr(ccxt, main_ex_id)({'timeout': 5000})
    
    try:
        # A. 实时价格与 24h 基础
        tk = main_ex.fetch_ticker(pair)
        curr_p = tk['last']
        res["最新价"] = curr_p
        res["24h"] = tk['percentage']

        # B. 物理偏移抓取 (1m, 5m, 15m, 1h) - 解决数据重复/0的问题
        now = main_ex.milliseconds()
        offsets = {"1m": 60*1000, "5m": 300*1000, "15m": 900*1000, "1h": 3600*1000}
        for label, ms in offsets.items():
            k = main_ex.fetch_ohlcv(pair, '1m', since=now - ms - 2000, limit=1)
            if k:
                base_p = k[0][4]
                res[label] = ((curr_p - base_p) / base_p) * 100
            else:
                res[label] = 0.0

        # C. 全网净流入 (聚合四所)
        total_flow = 0.0
        for eid in EXCHANGES.values():
            try:
                ex = getattr(ccxt, eid)({'timeout': 1500})
                trades = ex.fetch_trades(pair, limit=50)
                total_flow += sum([(t['price']*t['amount']) if t['side']=='buy' else -(t['price']*t['amount']) for t in trades])
            except: continue
        res["净流入(万)"] = round(total_flow / 10000, 2)

        # D. 合成指标诊断
        ohlcv_raw = main_ex.fetch_ohlcv(pair, '1h', limit=40)
        df = pd.DataFrame(ohlcv_raw, columns=['t','o','h','l','c','v'])
        rsi_val = ta.rsi(df['c'], length=14).iloc[-1]
        res["RSI"] = round(rsi_val, 1)
        
        diag, atr_p, obv_s = get_tactical_logic(df, curr_p, res["净流入(万)"], rsi_val)
        res["战术诊断"] = diag
        res["ATR%"] = atr_p
        res["OBV"] = obv_s
        
    except Exception as e:
        return None
    return res

# ==========================================
# 4. 界面渲染
# ==========================================
st.title("🛰️ 全球资产指挥部 (全周期/全功能/校准版)")
placeholder = st.empty()



while True:
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        results = list(executor.map(fetch_commander_data, SYMBOLS))
    
    df = pd.DataFrame([r for r in results if r is not None])
    if not df.empty:
        df = df.sort_values(by="1m", ascending=False)

    display_df = df.copy()
    # 严格按照要求的顺序排列
    order = ["币种", "最新价", "战术诊断", "1m", "5m", "15m", "1h", "24h", "净流入(万)", "RSI", "ATR%", "OBV"]
    
    # 百分比美化
    for col in ["1m", "5m", "15m", "1h", "24h"]:
        display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%")

    with placeholder.container():
        st.write(f"📊 **策略监控中** | 频率: 40s | 时间: {time.strftime('%H:%M:%S')} | **诊断：RSI+OBV+ATR+MACD**")
        
        def style_logic(val):
            if val == "🛒 底部吸筹": return 'background-color: #700; color: white'
            if val == "💀 确认破位": return 'background-color: #ff0000; color: white'
            if val == "💎流入": return 'color: #00ff00'
            return ''

        st.dataframe(
            display_df[order].style.applymap(style_logic), 
            use_container_width=True, 
            height=660
        )

    time.sleep(40)
