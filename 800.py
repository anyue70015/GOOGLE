import streamlit as st
import pandas as pd
import ccxt
import time
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="指挥部-全量深度监控", layout="wide")

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "ZEC", "ASTER"]

# ==========================================
# 2. 技术指标计算工具
# ==========================================
def calculate_metrics(ohlcv):
    """计算 OBV 和 ATR (基于最近 14-20 根 K 线)"""
    if len(ohlcv) < 15:
        return "·", 0.0
    
    closes = np.array([x[4] for x in ohlcv])
    volumes = np.array([x[5] for x in ohlcv])
    highs = np.array([x[2] for x in ohlcv])
    lows = np.array([x[3] for x in ohlcv])
    
    # --- OBV 计算 ---
    obv = [0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i-1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    obv_trend = "🔥流入" if obv[-1] > obv[-2] else "❄️流出"
    
    # --- ATR 计算 (简易版) ---
    tr = np.maximum(highs[1:] - lows[1:], 
                    np.maximum(abs(highs[1:] - closes[:-1]), 
                               abs(lows[1:] - closes[:-1])))
    atr = np.mean(tr[-14:])
    
    return obv_trend, atr

# ==========================================
# 3. 核心抓取函数
# ==========================================
def fetch_commander_data(symbol):
    pair = f"{symbol}/USDT"
    # Bitget 优先策略 (针对 TAO)
    e_ids = ['bitget', 'okx'] if symbol in ['TAO', 'HYPE', 'ASTER', 'ZEC'] else ['okx', 'bitget']
    
    res = {"币种": symbol}
    
    for eid in e_ids:
        try:
            ex = getattr(ccxt, eid)({'timeout': 5000, 'enableRateLimit': True})
            
            # 1. 基础行情 & 24h 涨跌
            tk = ex.fetch_ticker(pair)
            curr_p = tk['last']
            res["最新价"] = curr_p
            res["24h"] = tk.get('percentage', 0.0)
            
            # 2. 吃单量 (Net Flow) - 扫描最近 50 笔成交
            trades = ex.fetch_trades(pair, limit=50)
            net_flow = sum([(t['price'] * t['amount']) if t['side'] == 'buy' else -(t['price'] * t['amount']) for t in trades])
            res["吃单量(万)"] = round(net_flow / 10000, 2)
            
            # 3. 多周期涨跌 & 技术指标
            # 抓取 1h K 线来计算 OBV 和 ATR
            ohlcv_1h = ex.fetch_ohlcv(pair, '1h', limit=20)
            res["OBV"], res["ATR"] = calculate_metrics(ohlcv_1h)
            
            # 各分钟周期涨跌
            for label, tf in {'1m': '1m', '5m': '5m', '15m': '15m', '1h': '1h'}.items():
                k = ex.fetch_ohlcv(pair, tf, limit=2)
                if len(k) >= 2:
                    base_p = k[0][4]
                    res[label] = ((curr_p - base_p) / base_p) * 100
                else:
                    res[label] = 0.0
            
            res["来源"] = eid.upper()
            return res
        except:
            continue
    return {**{"币种": symbol, "最新价": 0.0, "24h": 0.0, "吃单量(万)": 0.0, "OBV": "·", "ATR": 0.0}, 
            **{tf: 0.0 for tf in ['1m', '5m', '15m', '1h']}, "来源": "失败"}

# ==========================================
# 4. UI 调度与实时显示
# ==========================================
st.title("🚨 2026.01.30 指挥部全能版 (Bitget/OKX)")

placeholder = st.empty()

while True:
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        results = list(executor.map(fetch_commander_data, SYMBOLS))
    
    df = pd.DataFrame(results)
    
    # 按照你的要求排序列：1m 放在最前面
    order = ["币种", "最新价", "1m", "5m", "15m", "1h", "24h", "吃单量(万)", "OBV", "ATR", "来源"]
    df = df[order]
    
    # 自动排序：按 1m 跌幅排最前 (监控插针)
    df = df.sort_values(by="1m", ascending=True)

    # 格式化
    display_df = df.copy()
    pct_cols = ["1m", "5m", "15m", "1h", "24h"]
    for col in pct_cols:
        display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%")

    with placeholder.container():
        st.write(f"🔄 **实时监控中** | 更新时间: {time.strftime('%H:%M:%S')} | TAO 优先 Bitget 节点")
        
        # 异常指标警报
        tao_row = df[df['币种'] == 'TAO'].iloc[0] if not df[df['币种'] == 'TAO'].empty else None
        if tao_row is not None:
            if tao_row['吃单量(万)'] < -10: # 大于 10 万美金的净流出
                st.error(f"☢️ **TAO 现货遭大额抛售**: 净流出 {abs(tao_row['吃单量(万)'])} 万 USDT！")
            if tao_row['ATR'] > (tao_row['最新价'] * 0.01): # 波动率超过 1%
                st.warning(f"⚠️ **TAO 波动剧增**: ATR 指标显示当前正处于极端变盘期！")

        st.dataframe(display_df, use_container_width=True, height=650)

    time.sleep(10)
