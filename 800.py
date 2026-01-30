import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="指挥部-终极回溯版", layout="wide")

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "ZEC", "ASTER"]
EXCHANGES = {'OKX': 'okx', 'Bitget': 'bitget', 'Gate': 'gateio', 'Huobi': 'htx'}

# ==========================================
# 2. 核心技术指标计算 (增加稳定性过滤)
# ==========================================
def get_stable_indicators(ex, pair, curr_p):
    try:
        # 抓取 60 根 1h K线
        ohlcv = ex.fetch_ohlcv(pair, '1h', limit=60)
        df = pd.DataFrame(ohlcv, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        
        # RSI
        rsi = ta.rsi(df['c'], length=14).iloc[-1]
        
        # MACD 平滑判定
        macd_df = ta.macd(df['c'])
        m_val = macd_df['MACD_12_26_9'].iloc[-1]
        m_sig = macd_df['MACDs_12_26_9'].iloc[-1]
        
        # 动态阈值 (万分之五) 防止跳变
        diff = m_val - m_sig
        threshold = curr_p * 0.0005
        if diff > threshold: macd_status = "金叉趋势"
        elif diff < -threshold: macd_status = "死叉趋势"
        else: macd_status = "缠绕震荡"
        
        # ATR 波动率
        atr = ta.atr(df['h'], df['l'], df['c'], length=14).iloc[-1]
        atr_pct = (atr / curr_p) * 100
        
        # OBV 简单方向
        obv_trend = "流入" if df['c'].iloc[-1] > df['c'].iloc[-2] else "流出"
        
        return {"RSI": round(rsi, 1), "MACD": macd_status, "ATR%": round(atr_pct, 2), "OBV": obv_trend}
    except:
        return {"RSI": 50, "MACD": "·", "ATR%": 0.0, "OBV": "·"}

# ==========================================
# 3. 核心抓取：修复 0 的核心逻辑
# ==========================================
def fetch_commander_final(symbol):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol}
    main_ex_id = 'bitget' if symbol in ['TAO', 'HYPE', 'ASTER', 'ZEC'] else 'okx'
    main_ex = getattr(ccxt, main_ex_id)({'timeout': 5000})
    
    try:
        # A. 获取最新实时成交价
        tk = main_ex.fetch_ticker(pair)
        curr_p = tk['last']
        res["最新价"] = curr_p
        res["24h"] = tk['percentage']
        
        # B. 双重回溯获取各周期涨跌 (使用 limit=2)
        # 核心：取 index 0 的收盘价作为对比基准，因为它已经“定死”了
        for label, tf in {"1m":"1m", "5m":"5m", "15m":"15m", "1h":"1h"}.items():
            k = main_ex.fetch_ohlcv(pair, tf, limit=2)
            if len(k) >= 2:
                base_p = k[0][4] # 前一根已结束的 K 线收盘价
                res[label] = ((curr_p - base_p) / base_p) * 100
            else:
                res[label] = 0.0

        # C. 聚合四所全网净流
        total_flow = 0.0
        for eid in EXCHANGES.values():
            try:
                ex = getattr(ccxt, eid)({'timeout': 2000})
                trades = ex.fetch_trades(pair, limit=50)
                total_flow += sum([(t['price'] * t['amount']) if t['side'] == 'buy' else -(t['price'] * t['amount']) for t in trades])
            except: continue
        res["净流(万)"] = round(total_flow / 10000, 2)

        # D. 获取指标并诊断
        tech = get_stable_indicators(main_ex, pair, curr_p)
        res.update(tech)
        
        # 战术指令
        diag = "🔎 观望"
        if res["RSI"] < 25 and res["1m"] > -0.05 and res["净流(万)"] > 5:
            diag = "🛒 底部确认"
        elif res["MACD"] == "死叉趋势" and res["1h"] < -2 and res["净流(万)"] < -30:
            diag = "💀 确认破位"
        elif res["1h"] < -1 and res["OBV"] == "流入" and res["净流(万)"] > 15:
            diag = "💎 强力吸筹"
        elif res["1m"] > 0.5 and res["净流(万)"] < -10:
            diag = "⚠️ 诱多虚涨"
        elif res["ATR%"] > 6.0:
            diag = "⚡ 极端暴震"
            
        res["战术诊断"] = diag
        
    except: return None
    return res

# ==========================================
# 4. UI 渲染与自动刷新 (40秒)
# ==========================================
st.title("🛰️ 全球资产实战指挥部 (终极双重回溯版)")
placeholder = st.empty()



while True:
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        results = list(executor.map(fetch_commander_final, SYMBOLS))
    
    df = pd.DataFrame([r for r in results if r is not None])
    if not df.empty:
        # 按 1m 表现排序
        df = df.sort_values(by="1m", ascending=False)

    display_df = df.copy()
    # 格式化百分比
    pct_cols = ["1m", "5m", "15m", "1h", "24h"]
    for c in pct_cols:
        display_df[c] = display_df[c].apply(lambda x: f"{x:+.2f}%" if isinstance(x, (int, float)) else "·")

    with placeholder.container():
        st.write(f"🔄 **数据全量同步完成** | 频率: 40s | 刷新时间: {time.strftime('%H:%M:%S')} | **模式：双重回溯无死角监控**")
        
        # 定义最终展示顺序
        order = ["币种", "最新价", "战术诊断", "1m", "5m", "15m", "1h", "24h", "净流(万)", "RSI", "MACD", "ATR%", "OBV"]
        st.dataframe(display_df[order], use_container_width=True, height=660)
        
        # 特别状态快速提醒
        alerts = df[df['战术诊断'].isin(["🛒 底部确认", "💎 强力吸筹"])]
        if not alerts.empty:
            st.success(f"🌟 **机会点扫描**: {', '.join(alerts['币种'].tolist())} 出现多维吸筹信号！")

    time.sleep(40)
