import streamlit as st
import pandas as pd
import ccxt
import time

# --- 1. 基础配置 ---
st.set_page_config(page_title="全球量化指挥部 - CCXT稳定版", layout="wide")

# 初始化币安合约引擎 (内置高可用接入点)
@st.cache_resource
def get_exchange():
    # 使用 binanceusdm (币安 U 基合约)
    return ccxt.binanceusdm({
        'timeout': 10000,
        'enableRateLimit': True,
    })

exchange = get_exchange()

# 币种名单
SYMBOLS = ["BTC", "RENDER", "SUI", "TAO", "ETH", "SOL", "XRP", "UNI", "BCH", "HYPE", "DOGE", "AAVE", "ZEC", "CHZ"]

# ------------------------------------------------
# 2. 核心诊断逻辑
# ------------------------------------------------
def get_strategy_logic(m1, m5, h1, c24):
    if m1 > 0.15 and m5 > 0.5: return "🎯 战术突击 (强吸筹)"
    if m1 < -0.15 and m5 < -0.5: return "💀 战略撤退 (砸盘)"
    if c24 > 3 and m1 < -0.05: return "🔋 战术回撤 (洗盘)"
    if c24 < -3 and m1 > 0.05: return "🛡️ 战略修复 (抄底)"
    if abs(m1) < 0.05 and abs(m5) < 0.1: return "😴 战略横盘"
    return "⚖️ 中性博弈"

def fetch_data_from_ccxt(symbol):
    try:
        pair = f"{symbol}/USDT"
        
        # 1. 获取 24h 涨幅数据
        ticker = exchange.fetch_ticker(pair)
        price = ticker['last']
        c24 = ticker['percentage'] # 24h 涨跌幅百分比
        vol = ticker['quoteVolume'] # 24h 成交额

        # 2. 获取 K 线数据 (获取最近 100 根 1m 线)
        # 内部自动处理了分页和频率限制
        ohlcv = exchange.fetch_ohlcv(pair, timeframe='1m', limit=61)
        df_k = pd.DataFrame(ohlcv, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        
        # 计算 1m 涨幅
        m1 = (df_k['c'].iloc[-1] - df_k['o'].iloc[-1]) / df_k['o'].iloc[-1] * 100
        # 计算 5m 涨幅 (最近 5 根线的合集)
        m5 = (df_k['c'].iloc[-1] - df_k['o'].iloc[-5]) / df_k['o'].iloc[-5] * 100
        # 计算 1h 涨幅
        h1 = (df_k['c'].iloc[-1] - df_k['o'].iloc[-60]) / df_k['o'].iloc[-60] * 100

        return {
            "币种": symbol,
            "最新价": round(price, 4) if price < 10 else round(price, 2),
            "1m%": m1, 
            "5m%": m5, 
            "1h%": h1, 
            "24h%": c24,
            "净流入(万)": round((c24 * vol / 100000000), 1), # 估算净流入
            "战术/战略诊断": get_strategy_logic(m1, m5, h1, c24),
            "来源": "CCXT聚合"
        }
    except Exception as e:
        return None

# ------------------------------------------------
# 3. 界面渲染
# ------------------------------------------------
st.title("🛰️ 全球量化指挥部 - 实时战略中心")
st.caption(f"底层引擎: CCXT (自动路由) | 刷新间隔: 5s")

placeholder = st.empty()

while True:
    rows = []
    # 使用 Streamlit 进度条显示加载状态，防止白屏
    for s in SYMBOLS:
        res = fetch_data_row = fetch_data_from_ccxt(s)
        if res:
            rows.append(res)
    
    if rows:
        df = pd.DataFrame(rows)
        with placeholder.container():
            st.dataframe(
                df.style.format({
                    "1m%": "{:+,.2f}%", "5m%": "{:+,.2f}%", 
                    "1h%": "{:+,.2f}%", "24h%": "{:+,.2f}%",
                    "最新价": "{:,}"
                }).background_gradient(subset=["1m%", "24h%"], cmap="RdYlGn", vmin=-1.0, vmax=1.0),
                use_container_width=True,
                height=(len(SYMBOLS) + 1) * 38,
                hide_index=True
            )
            st.caption(f"📊 数据源同步正常 | 刷新时间: {time.strftime('%H:%M:%S')}")
    else:
        st.error("⚠️ 云端链路被拦截，请尝试在本地运行或更换部署区域。")

    time.sleep(5)
