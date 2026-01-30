import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="2026 金融风暴实时监控", layout="wide")

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA","ZEC", "ASTER"]
EXCHANGES = {'OKX': 'okx', 'Bitget': 'bitget', 'Gate': 'gateio'}

# 初始化全局存储
if 'GLOBAL_DATA' not in st.session_state:
    st.session_state.GLOBAL_DATA = {s: {"币种": s, "最新价": 0.0, "24h涨跌": 0.0} for s in SYMBOLS}

# ==========================================
# 2. 核心抓取逻辑 (修正版)
# ==========================================
def fetch_all_data():
    """全量抓取，不再分批，直接获取 24h 真实涨跌"""
    ex = ccxt.okx({'timeout': 5000, 'enableRateLimit': True})
    try:
        # 1. 一次性拿全量行情 (避免分批导致的滞后)
        tickers = ex.fetch_tickers([f"{s}/USDT" for s in SYMBOLS])
        
        for s in SYMBOLS:
            pair = f"{s}/USDT"
            if pair in tickers:
                tk = tickers[pair]
                # 直接使用交易所计算好的 percentage (24h)
                st.session_state.GLOBAL_DATA[s].update({
                    "最新价": tk['last'],
                    "24h涨跌": tk['percentage'] if tk['percentage'] else 0.0,
                    "24h最高": tk['high'],
                    "24h低点": tk['low'],
                    "成交量": tk['quoteVolume']
                })
    except Exception as e:
        st.error(f"API 同步失败: {e}")

# ==========================================
# 3. UI 渲染
# ==========================================
st.title("🚨 全球资产流动性危机 - 实时指挥部")
st.markdown(f"**当前盘面：** 微软暴跌引发 AI 泡沫破裂，黄金与 BTC 触发强平锁死")

col1, col2 = st.columns([3, 1])
placeholder = st.empty()

while True:
    fetch_all_data()
    
    # 转换 DataFrame
    df = pd.DataFrame(st.session_state.GLOBAL_DATA.values())
    
    # 格式化
    display_df = df.copy()
    if not display_df.empty:
        # 增加“距离 24h 高点回撤”字段，这才是暴跌时最该看的
        display_df['距高点回撤'] = ((display_df['最新价'] - display_df['24h最高']) / display_df['24h最高'] * 100).map("{:+.2f}%".format)
        display_df['24h涨跌'] = display_df['24h涨跌'].map("{:+.2f}%".format)
        
        # 排序：按跌幅最狠的排前面
        display_df = display_df.sort_values(by="24h涨跌", ascending=True)

    with placeholder.container():
        st.write(f"🕒 数据最后更新: {time.strftime('%H:%M:%S')} (全量同步模式)")
        st.dataframe(
            display_df[["币种", "最新价", "24h涨跌", "距高点回撤", "24h最高", "24h低点"]],
            use_container_width=True,
            height=600
        )
        
        # 简易风险警报
        btc_drop = df[df['币种'] == 'BTC']['24h涨跌'].values[0]
        if btc_drop < -5:
            st.error(f"⚠️ 警报：比特币日内跌幅超过 {btc_drop:.2f}%，去杠杆踩踏正在发生！")

    time.sleep(10) # 暴跌期间，建议 10 秒刷新一次
