import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="指挥部-40s全指标稳健版", layout="wide")

# 监控币种清单
SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "ZEC", "ASTER"]
# 聚合交易所
EXCHANGES = {'OKX': 'okx', 'Bitget': 'bitget', 'Gate': 'gateio', 'Huobi': 'htx'}

# ==========================================
# 2. 技术指标计算 (基于 Rolling 1h)
# ==========================================
def compute_tech_indicators(ex, pair, curr_p):
    try:
        # 获取 50 根 1h 线以计算 MACD/RSI/ATR
        ohlcv = ex.fetch_ohlcv(pair, '1h', limit=50)
        df = pd.DataFrame(ohlcv, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        
        # RSI 14
        rsi = ta.rsi(df['c'], length=14).iloc[-1]
        
        # MACD (12, 26, 9)
        macd_df = ta.macd(df['c'])
        m_val = macd_df['MACD_12_26_9'].iloc[-1]
        m_sig = macd_df['MACDs_12_26_9'].iloc[-1]
        
        # ATR 14
        atr_val = ta.atr(df['h'], df['l'], df['c'], length=14).iloc[-1]
        atr_pct = (atr_val / curr_p) * 100
        
        # OBV 判定
        obv_status = "💎流入" if curr_p > df['c'].iloc[-2] else "💀流出"
        
        return {
            "RSI": round(rsi, 1),
            "MACD": "金叉" if m_val > m_sig else "死叉",
            "ATR%": round(atr_pct, 2),
            "OBV": obv_status
        }
    except:
        return {"RSI": 50.0, "MACD": "·", "ATR%": 0.0, "OBV": "·"}

# ==========================================
# 3. 核心数据抓取与诊断
# ==========================================
def fetch_full_commander(symbol):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol}
    
    # 确定主交易所：TAO/HYPE 这种币锁定 Bitget，其他常用 OKX
    main_ex_id = 'bitget' if symbol in ['TAO', 'HYPE', 'ASTER', 'ZEC'] else 'okx'
    main_ex = getattr(ccxt, main_ex_id)({'timeout': 5000})
    
    try:
        # 1. 24h 滚动数据
        tk = main_ex.fetch_ticker(pair)
        curr_p = tk['last']
        res["最新价"] = curr_p
        res["24h"] = tk['percentage']
        
        # 2. 核心时间窗滚动 (1m, 15m, 1h)
        now_ms = main_ex.milliseconds()
        for label, ms in {"1m": 60000, "15m": 900000, "1h": 3600000}.items():
            k = main_ex.fetch_ohlcv(pair, '1m', since=now_ms - ms - 2000, limit=1)
            res[label] = ((curr_p - k[0][4]) / k[0][4] * 100) if k else 0.0

        # 3. 全网聚合净流 (跨四所最近成交)
        total_flow = 0.0
        for eid in EXCHANGES.values():
            try:
                ex = getattr(ccxt, eid)({'timeout': 2000})
                trades = ex.fetch_trades(pair, limit=40) # 聚合 40 笔
                total_flow += sum([(t['price'] * t['amount']) if t['side'] == 'buy' else -(t['price'] * t['amount']) for t in trades])
            except: continue
        res["净流(万)"] = round(total_flow / 10000, 2)

        # 4. 技术指标集成
        tech = compute_tech_indicators(main_ex, pair, curr_p)
        res.update(tech)

        # 5. 综合战术诊断
        diag = "🔎 观望"
        if res["1h"] < -4 and res["RSI"] < 25:
            diag = "🛒 底部超卖(抄底)"
        elif res["MACD"] == "死叉" and res["净流(万)"] < -30:
            diag = "💀 破位加速"
        elif res["OBV"] == "💎流入" and res["1h"] < 0:
            diag = "💎 缩量吸筹"
        elif res["ATR%"] > 5.0:
            diag = "⚡ 极端插针"
        elif res["RSI"] > 75 and res["净流(万)"] < 0:
            diag = "⚠️ 顶部诱多"
            
        res["战术诊断"] = diag
        
    except: return None
    return res

# ==========================================
# 4. UI 界面与自动循环
# ==========================================
st.title("🛰️ 全球资产五维战术指挥部 (40s稳健版)")
placeholder = st.empty()

while True:
    # 全量币种并发请求
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        results = list(executor.map(fetch_full_commander, SYMBOLS))
    
    # 清洗数据并排序 (按 1 分钟强弱排序)
    df = pd.DataFrame([r for r in results if r is not None])
    if not df.empty:
        df = df.sort_values(by="1m", ascending=False)

    display_df = df.copy()
    # 格式化百分比显示
    for c in ["1m", "15m", "1h", "24h"]:
        display_df[c] = display_df[c].apply(lambda x: f"{x:+.2f}%")

    with placeholder.container():
        st.write(f"📊 **数据周期性更新** | 刷新频率: 40s | 时间: {time.strftime('%H:%M:%S')} | **模式：全指标滚动**")
        
        # 整理表格列顺序
        order = ["币种", "最新价", "战术诊断", "1m", "15m", "1h", "24h", "净流(万)", "RSI", "MACD", "ATR%", "OBV"]
        st.dataframe(
            display_df[order],
            use_container_width=True,
            height=660
        )
        
        # 针对 1 月 30 日暴跌的底部预警
        critical_alerts = df[df['战术诊断'].isin(["💀 破位加速", "⚡ 极端插针"])]
        if not critical_alerts.empty:
            st.warning(f"🚨 高风险目标：{', '.join(critical_alerts['币种'].tolist())} 指标出现危险异常。")

    # 按照你的要求，设置 40 秒刷新一次
    time.sleep(40)
