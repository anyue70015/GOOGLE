import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import time

# ==========================================
# 1. 核心引擎 (OKX 直连)
# ==========================================
st.set_page_config(page_title="2026 监控神兵-多周期版", layout="wide")

@st.cache_resource
def get_ex():
    return ccxt.okx({'enableRateLimit': True})

def get_change_and_volume(symbol, timeframe):
    """抓取指定周期的涨幅和当前成交额"""
    ex = get_ex()
    try:
        # 获取最近 2 根 K 线计算当前周期涨幅
        ohlcv = ex.fetch_ohlcv(symbol, timeframe, limit=2)
        if len(ohlcv) < 2: return 0, 0
        
        open_p = ohlcv[-1][1]
        close_p = ohlcv[-1][4]
        vol_usd = ohlcv[-1][5] * close_p # 近似成交额
        change = ((close_p - open_p) / open_p) * 100
        return change, vol_usd
    except:
        return 0, 0

def detect_big_orders(symbol, threshold_usd=50000):
    """抓取最近成交，筛选大吃单"""
    ex = get_ex()
    try:
        trades = ex.fetch_trades(symbol, limit=20)
        # 筛选单笔金额超过阈值的买单
        big_buys = [t for t in trades if t['side'] == 'buy' and (t['price'] * t['amount']) >= threshold_usd]
        return "🔥" * len(big_buys) if big_buys else ""
    except:
        return ""

# ==========================================
# 2. UI 界面
# ==========================================
st.title("🛡️ 多周期异动扫描 + 大吃单监控")

with st.sidebar:
    st.header("监控设置")
    raw_symbols = st.text_area("监控列表", "BTC/USDT,ETH/USDT,SOL/USDT,ORDI/USDT,SUI/USDT")
    symbols = [s.strip().upper() for s in raw_symbols.replace('\n', ',').split(',') if s.strip()]
    big_order_val = st.number_input("大吃单定义 (USDT)", value=50000)
    refresh_rate = st.slider("刷新频率 (秒)", 5, 60, 10)

placeholder = st.empty()

while True:
    results = []
    for sym in symbols:
        # 并行抓取各周期数据
        ch1, v1 = get_change_and_volume(sym, '1m')
        ch5, v5 = get_change_and_volume(sym, '5m')
        ch15, v15 = get_change_and_volume(sym, '15m')
        
        # 探测大吃单
        big_orders = detect_big_orders(sym, big_order_val)
        
        results.append({
            "交易对": sym,
            "1m 涨跌": f"{ch1:+.2f}%",
            "5m 涨跌": f"{ch5:+.2f}%",
            "15m 涨跌": f"{ch15:+.2f}%",
            "大吃单警报": big_orders,
            "活跃度": "⭐" if v1 > 100000 else "" # 如果1分钟成交过10万刀
        })
    
    df = pd.DataFrame(results)
    
    with placeholder.container():
        st.write(f"📊 实时监控中... 最后更新: {time.strftime('%H:%M:%S')}")
        
        # 样式渲染：如果是涨的，给文字上色
        def color_change(val):
            if '+' in str(val) and float(val.strip('%')) > 0: color = '#00ff00' 
            elif '-' in str(val): color = '#ff4b4b'
            else: color = 'white'
            return f'color: {color}'

        st.dataframe(
            df.style.applymap(color_change, subset=["1m 涨跌", "5m 涨跌", "15m 涨跌"]),
            use_container_width=True,
            height=600
        )
        
    time.sleep(refresh_rate)
