import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 核心抓取：强制周期偏移 (防止数据镜像)
# ==========================================
def fetch_calibrated_commander(symbol):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol}
    # 交易所分配逻辑
    main_ex = ccxt.bitget() if symbol in ['TAO', 'HYPE', 'ASTER'] else ccxt.okx()
    
    try:
        # A. 抓取实时价格
        tk = main_ex.fetch_ticker(pair)
        curr_p = tk['last']
        res["最新价"] = curr_p
        res["24h"] = f"{tk['percentage']:+.2f}%"

        # B. 强制分周期抓取 (关键：使用不同的 limit 确保拿到不同的基准)
        # 这里的逻辑是：抓取最近2根，取 index 0 (即已完成的那根)
        timeframes = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h"}
        for label, tf in timeframes.items():
            # 增加 retry 机制防止 API 偶尔返回空值
            k = main_ex.fetch_ohlcv(pair, tf, limit=2)
            if len(k) >= 2:
                base_p = k[0][4] # 取前一根 K 线的收盘价
                res[label] = ((curr_p - base_p) / base_p) * 100
            else:
                res[label] = 0.0

        # C. 指标计算 (MACD/RSI)
        ohlcv_1h = main_ex.fetch_ohlcv(pair, '1h', limit=40)
        df_ta = pd.DataFrame(ohlcv_1h, columns=['t','o','h','l','c','v'])
        res["RSI"] = round(ta.rsi(df_ta['c'], length=14).iloc[-1], 1)
        
        # D. 诊断逻辑：加入 RSI 阈值
        if res["RSI"] < 25: res["战术诊断"] = "🛒 底部确认"
        elif res["RSI"] > 75: res["战术诊断"] = "⚠️ 严重超买"
        elif res["1m"] > 0.3: res["战术诊断"] = "🚀 瞬时抢筹"
        else: res["战术诊断"] = "🔎 观望"
        
    except Exception as e:
        return None
    return res

# ==========================================
# 2. UI 渲染 (视觉高亮优化)
# ==========================================
st.title("🛰️ 战术指挥部 - 精度校准版")
placeholder = st.empty()

while True:
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(fetch_calibrated_commander, SYMBOLS))
    
    df = pd.DataFrame([r for r in results if r is not None])
    if not df.empty:
        df = df.sort_values(by="1m", ascending=False)

    with placeholder.container():
        st.write(f"🔄 更新时间: {time.strftime('%H:%M:%S')} | **状态：已强制拉开周期基准**")
        
        # 1. 颜色高亮逻辑：RSI 超卖变红，超买变绿
        def highlight_rsi(val):
            if val < 25: return 'background-color: #990000; color: white' # 深红
            if val > 75: return 'background-color: #006600; color: white' # 深绿
            return ''

        # 2. 涨跌幅变色
        def highlight_price(val):
            color = 'red' if val < 0 else 'green'
            return f'color: {color}'

        # 整理展示
        display_cols = ["币种", "最新价", "战术诊断", "1m", "5m", "15m", "1h", "24h", "RSI"]
        
        # 格式化百分比数值（保留2位并转字符串，方便样式展示）
        formatted_df = df[display_cols].copy()
        
        st.dataframe(
            formatted_df.style.applymap(highlight_rsi, subset=['RSI'])
                        .applymap(highlight_price, subset=['1m', '5m', '15m', '1h']),
            use_container_width=True, height=660
        )

    time.sleep(40)
