import streamlit as st
import pandas as pd
import numpy as np
import time
import ccxt

# ==========================================
# 1. 配置 (无需任何代理参数)
# ==========================================
st.set_page_config(page_title="2026全网聚合扫描器", layout="wide")

# ==========================================
# 2. 核心逻辑：获取全网交易量
# ==========================================
@st.cache_resource
def get_exchange():
    # 使用 OKX 或是 币安的加速域名
    # OKX 国内直连通常不需要代理
    return ccxt.okx({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })

def fetch_all_data():
    ex = get_exchange()
    try:
        # 核心：一次性抓取全场所有币种的实时行情 (Tickers)
        # 这是“全网聚合”最省力的方法
        tickers = ex.fetch_tickers()
        data = []
        for sym, t in tickers.items():
            if '/USDT' in sym: # 只看 USDT 交易对
                data.append({
                    "交易对": sym,
                    "现价": t['last'],
                    "24H涨幅%": t['percentage'],
                    "24H成交量": t['quoteVolume'], # USDT 计价的交易量
                    "最高价": t['high'],
                    "最低价": t['low']
                })
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"连接失败（建议检查网络）: {e}")
        return pd.DataFrame()

# ==========================================
# 3. 信号引擎 (向量化)
# ==========================================
def scan_signals(df, vol_threshold):
    if df.empty: return df
    
    # 将成交量转换为数值
    df['24H成交量'] = pd.to_numeric(df['24H成交量'])
    
    # 模拟“异常放量”逻辑：
    # 如果 24H 成交量远大于该市场平均水平，或者涨幅异常
    avg_vol = df['24H成交量'].median()
    df['放量比'] = df['24H成交量'] / avg_vol
    
    # 过滤：放量比 > 阈值 且 涨幅为正
    df['信号'] = np.where((df['放量比'] > vol_threshold) & (df['24H涨幅%'] > 0), "🚀 异动", "")
    
    return df.sort_values("放量比", ascending=False)

# ==========================================
# 4. UI 界面
# ==========================================
st.title("🛡️ 2026 国内直连聚合扫描器")
st.markdown("本工具通过 **OKX 国内节点** 获取全网行情，无需翻墙，支持全量 USDT 币种扫描。")

vol_threshold = st.sidebar.slider("全网平均放量比阈值", 1.0, 10.0, 3.0)
auto_refresh = st.sidebar.toggle("开启自动刷新", value=True)

placeholder = st.empty()

while True:
    raw_df = fetch_all_data()
    if not raw_df.empty:
        final_df = scan_signals(raw_df, vol_threshold)
        
        with placeholder.container():
            st.metric("监控交易对总数", len(final_df))
            
            # 只展示异动的币种，或者排名前 50 的币种
            display_df = final_df.head(50)
            
            def style_df(row):
                return ['background-color: rgba(0, 255, 0, 0.1)'] * len(row) if row['信号'] else [''] * len(row)

            st.dataframe(
                display_df.style.apply(style_df, axis=1),
                use_container_width=True,
                height=800
            )
    
    if not auto_refresh:
        break
    time.sleep(10) # 10秒刷一次，不会被封 IP
