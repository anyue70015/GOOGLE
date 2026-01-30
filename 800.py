import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="指挥部-全量功能版", layout="wide")

# 确保 18 个币种定义完整
SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "ZEC", "ASTER"]
EXCHANGES = {'OKX': 'okx', 'Bitget': 'bitget', 'Gate': 'gateio', 'Huobi': 'htx'}

# ==========================================
# 2. 核心抓取：物理隔离周期 + 全网净流
# ==========================================
def fetch_commander_full(symbol):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol}
    # 针对特定币种切换主交易所节点
    main_ex_id = 'bitget' if symbol in ['TAO', 'HYPE', 'ASTER', 'ZEC'] else 'okx'
    main_ex = getattr(ccxt, main_ex_id)({'timeout': 5000})
    
    try:
        # A. 抓取实时价格与24h滚动(Ticker)
        tk = main_ex.fetch_ticker(pair)
        curr_p = tk['last']
        res["最新价"] = curr_p
        res["24h"] = tk['percentage'] # 数值型，方便后续排序和格式化

        # B. 物理隔离抓取：解决“后三列一模一样”
        # 逻辑：每个周期取 limit=2，用 k[0] (上一根已收盘的线) 作为基准对比当前价
        for label, tf in {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h"}.items():
            k = main_ex.fetch_ohlcv(pair, tf, limit=2)
            if len(k) >= 2:
                base_p = k[0][4] 
                res[label] = ((curr_p - base_p) / base_p) * 100
            else:
                res[label] = 0.0

        # C. 全网净流入 (聚合四所最近 50 笔成交)
        total_flow = 0.0
        for eid in EXCHANGES.values():
            try:
                ex = getattr(ccxt, eid)({'timeout': 2000})
                trades = ex.fetch_trades(pair, limit=50)
                total_flow += sum([(t['price'] * t['amount']) if t['side'] == 'buy' else -(t['price'] * t['amount']) for t in trades])
            except: continue
        res["净流入(万)"] = round(total_flow / 10000, 2)

        # D. 技术指标 (RSI)
        ohlcv_1h = main_ex.fetch_ohlcv(pair, '1h', limit=40)
        df_ta = pd.DataFrame(ohlcv_1h, columns=['t','o','h','l','c','v'])
        res["RSI"] = round(ta.rsi(df_ta['c'], length=14).iloc[-1], 1)
        
        # E. 综合战术诊断
        diag = "🔎 观望"
        if res["RSI"] < 25 and res["1m"] > -0.05: diag = "🛒 底部确认"
        elif res["1h"] < -2 and res["净流入(万)"] > 20: diag = "💎 强力吸筹"
        elif res["1m"] > 0.5 and res["净流入(万)"] < -10: diag = "⚠️ 诱多虚涨"
        elif res["RSI"] > 75: diag = "💀 严重超买"
        res["战术诊断"] = diag
        
    except:
        return None
    return res

# ==========================================
# 3. UI 渲染与排序
# ==========================================
st.title("🛰️ 全球资产实战指挥部 (全功能/全周期/精度版)")
placeholder = st.empty()

while True:
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        results = list(executor.map(fetch_commander_full, SYMBOLS))
    
    df = pd.DataFrame([r for r in results if r is not None])
    if not df.empty:
        # 默认按 1 分钟表现排序
        df = df.sort_values(by="1m", ascending=False)

    display_df = df.copy()
    
    # 按照你要求的顺序排列列
    order = ["币种", "最新价", "战术诊断", "1m", "5m", "15m", "1h", "24h", "净流入(万)", "RSI"]
    
    # 格式化百分比列（保留两位小数，带符号）
    for col in ["1m", "5m", "15m", "1h", "24h"]:
        display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%")

    with placeholder.container():
        st.write(f"🕒 **实时数据流** | 频率: 40s | 刷新时间: {time.strftime('%H:%M:%S')} | **模式：双重回溯全维度监控**")
        
        # 使用 Styler 增加视觉辅助
        def color_diagnosis(val):
            if val == "🛒 底部确认": return 'background-color: #990000; color: white'
            if val == "💎 强力吸筹": return 'background-color: #000066; color: white'
            if val == "💀 严重超买": return 'background-color: #004400; color: white'
            return ''

        st.dataframe(
            display_df[order].style.applymap(color_diagnosis, subset=['战术诊断']),
            use_container_width=True, 
            height=660
        )
        
        # 底部跑马灯预警
        critical = df[df['RSI'] < 25]
        if not critical.empty:
            st.error(f"🚨 极度超卖预警: {', '.join(critical['币种'].tolist())}，请注意反弹机会！")

    time.sleep(40)
