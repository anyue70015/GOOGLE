import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import time
import base64
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 配置中心与音效组件
# ==========================================
st.set_page_config(page_title="2026 全网资金共振指挥部", layout="wide")

# 默认监控列表
SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP"]
EXCHANGE_IDS = {'OKX': 'okx', 'Gate': 'gateio', 'Huobi': 'htx', 'Bitget': 'bitget'}
SUPPORTED_EX = {name: getattr(ccxt, eid) for name, eid in EXCHANGE_IDS.items() if hasattr(ccxt, eid)}

# 注入音频播放组件 (HTML/JS)
def play_sound():
    # 使用一段简短的系统提示音 Base64
    sound_html = """
    <audio autoplay><source src="https://actions.google.com/sounds/v1/alarms/beep_short.ogg" type="audio/ogg"></audio>
    """
    st.components.v1.html(sound_html, height=0)

# ==========================================
# 2. 核心抓取与能量算法
# ==========================================
def fetch_symbol_data(symbol, big_val):
    symbol_pair = f"{symbol}/USDT"
    res = {"币种": symbol}
    total_net_flow = 0
    active_ex_count = 0  # 记录出现大单的交易所数量

    # --- A. 获取基础行情 (OKX) ---
    try:
        okx = SUPPORTED_EX['OKX']({'enableRateLimit': True, 'timeout': 5000})
        ticker = okx.fetch_ticker(symbol_pair)
        res["OKX涨跌"] = f"{ticker['percentage']:+.2f}%"
        res["raw_change"] = ticker['percentage']
    except:
        res["OKX涨跌"], res["raw_change"] = "0.00%", 0

    # --- B. 扫描四个交易所的能量与净流入 ---
    def get_ex_details(ex_name):
        nonlocal total_net_flow, active_ex_count
        try:
            ex = SUPPORTED_EX[ex_name]({'enableRateLimit': True, 'timeout': 5000})
            trades = ex.fetch_trades(symbol_pair, limit=50)
            
            # 计算能量等级
            big_icons = []
            ex_net_flow = 0
            has_big_order = False
            
            for t in trades:
                val = t['price'] * t['amount']
                side_mul = 1 if t['side'] == 'buy' else -1
                ex_net_flow += val * side_mul # 累计净流入
                
                if t['side'] == 'buy':
                    if val >= 500000: big_icons.append("💣")
                    elif val >= 100000: big_icons.append("🧨")
                    elif val >= big_val: big_icons.append("🔥")
            
            if big_icons:
                active_ex_count += 1
                return "".join(big_icons[:3]) # 最多显示3个图标
            return "·"
        except:
            return "❌"

    for name in SUPPORTED_EX.keys():
        res[name] = get_ex_details(name)

    res["净流入(万)"] = round(total_net_flow / 10000, 2)
    res["共振状态"] = "🚨 共振" if active_ex_count >= 3 else ""
    
    return res

# ==========================================
# 3. UI 界面
# ==========================================
st.title("🏹 全网资金流向 & 共振扫描器")

with st.sidebar:
    st.header("⚡ 实时参数")
    big_val = st.number_input("基础大单 (🔥) 阈值", value=20000)
    st.markdown("""
    - 🔥 > 基础阈值
    - 🧨 > 10万 USDT
    - 💣 > 50万 USDT
    """)
    refresh_rate = st.slider("扫描频率 (秒)", 5, 60, 10)
    enable_audio = st.toggle("开启共振音效报警", value=True)

placeholder = st.empty()

while True:
    final_data = []
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        futures = [executor.submit(fetch_symbol_data, sym, big_val) for sym in SYMBOLS]
        for f in futures:
            final_data.append(f.result())

    df = pd.DataFrame(final_data).sort_values("raw_change", ascending=False).drop(columns="raw_change")

    # 检查是否触发全局音效
    if enable_audio and not df[df["共振状态"] == "🚨 共振"].empty:
        play_sound()

    with placeholder.container():
        st.write(f"⏱️ 刷新: {time.strftime('%H:%M:%S')} | 10秒内 50笔成交深度分析")
        
        # 表格渲染样式
        def style_rows(row):
            styles = [''] * len(row)
            if row['共振状态'] == '🚨 共振':
                styles = ['background-color: rgba(255, 75, 75, 0.25); font-weight: bold'] * len(row)
            return styles

        def color_change(val):
            if isinstance(val, str) and '+' in val: return 'color: #00ff00'
            if isinstance(val, str) and '-' in val: return 'color: #ff4b4b'
            return ''

        st.dataframe(
            df.style.apply(style_rows, axis=1)
                    .applymap(color_change, subset=["OKX涨跌"])
                    .set_properties(**{'text-align': 'center'}, subset=['OKX', 'Gate', 'Huobi', 'Bitget']),
            use_container_width=True,
            height=600
        )
    
    time.sleep(refresh_rate)
