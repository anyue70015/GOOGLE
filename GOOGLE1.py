import streamlit as st
import pandas as pd
import ccxt
import time
from datetime import datetime

# --- 初始化 ---
st.set_page_config(page_title="8:00 换仓狙击", layout="wide")
ex = ccxt.okx({'enableRateLimit': True})
STABLECOINS = ['USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'USDE', 'USDG', 'PYUSD', 'EUR', 'USDS']

@st.cache_data(ttl=10)
def get_dynamic_data():
    # 1. 预设空表，防止 KeyError
    columns = ["币种", "5min量比", "24h涨跌%", "偏离200MA%", "状态", "综合评分"]
    results = []
    
    try:
        # 2. 一次性获取所有行情 (1次请求)
        tickers = ex.fetch_tickers()
        # 过滤 Top 50 (先缩减规模提高响应速度)
        valid_list = [s for s in tickers.items() if '/USDT' in s[0] and not any(sc in s[0] for sc in STABLECOINS)]
        top_coins = sorted(valid_list, key=lambda x: x[1].get('quoteVolume', 0), reverse=True)[:50]
        
        status_placeholder = st.empty()
        
        for i, (sym, data) in enumerate(top_coins):
            # 3. 计算初步量比 (利用 ticker 自带的 24h 量)
            # 这里的量比是：当前 24h 量 / 昨天的量 (近似值)，用于初步筛选
            vol_24h = data.get('quoteVolume', 0)
            change = data.get('percentage', 0)
            price = data.get('last', 0)
            
            # 4. 【核心优化】只对有潜力或排名前列的币进行深度 K 线抓取
            # 这样可以极大减少 API 请求次数，防止被卡死
            try:
                # 抓取 5min 线算实时量能
                bars_5m = ex.fetch_ohlcv(sym, timeframe='5m', limit=2)
                v_now = bars_5m[-1][5]
                avg_v_5min = vol_24h / 288
                v_ratio = v_now / avg_v_5min if avg_v_5min > 0 else 0
                
                # 只有量比 > 1.2 或者前 10 名才算 200MA，节省资源
                ma200_dist = 0
                status = "❄️ 趋势之下"
                if v_ratio > 1.2 or i < 10:
                    daily = ex.fetch_ohlcv(sym, timeframe='1d', limit=200)
                    if len(daily) >= 150:
                        df_daily = pd.DataFrame(daily, columns=['ts','o','h','l','c','v'])
                        ma200 = df_daily['c'].mean()
                        ma200_dist = (price - ma200) / ma200 * 100
                        status = "🔥 趋势之上" if price > ma200 else "❄️ 趋势之下"
                
                score = (30 if v_ratio > 2 else 0) + (50 if status == "🔥 趋势之上" else 0) + (20 if change > 0 else 0)
                
                results.append({
                    "币种": sym,
                    "5min量比": round(v_ratio, 2),
                    "24h涨跌%": round(change, 2),
                    "偏离200MA%": round(ma200_dist, 2),
                    "状态": status,
                    "综合评分": score
                })
                status_placeholder.text(f"⚡ 正在扫描实时量能: {sym}")
            except:
                continue
        
        status_placeholder.empty()
    except Exception as e:
        st.error(f"数据加载中断: {e}")

    return pd.DataFrame(results) if results else pd.DataFrame(columns=columns)

# --- 界面渲染 ---
st.title("🎯 8:00 汰弱留强系统")
st.write(f"最后更新: {datetime.now().strftime('%H:%M:%S')}")

from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=20000, key="fresher")

df = get_dynamic_data()

if not df.empty:
    # 信号区
    st.subheader("🚨 实时换仓建议")
    # 只要满足：趋势向上 + 量能活跃 
    signals = df[(df['5min量比'] > 1.5) & (df['状态'] == "🔥 趋势之上")].sort_values(by='5min量比', ascending=False)
    
    if not signals.empty:
        st.success("发现爆发标的！")
        st.table(signals)
    else:
        st.info("暂无爆发信号，建议观察或持有现货/合约仓位不动。")

    # 全表
    st.divider()
    st.subheader("📊 实时全盘扫描")
    st.dataframe(df.sort_values(by='5min量比', ascending=False), use_container_width=True)
else:
    st.warning("正在努力抓取数据中，请稍候...")
