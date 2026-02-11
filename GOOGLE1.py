import streamlit as st
import pandas as pd
import ccxt
import time

# 设置 Streamlit 页面配置
st.set_page_config(page_title="Top 80 汰弱留强监控", layout="wide")

st.title("🚀 Top 80 币种：200日均线 (200MA) 实时强度扫描")
st.write("如果你要回本，必须把钱从【❄️ 趋势之下】换到【🔥 趋势之上】。")

# 初始化交易所
ex = ccxt.okx()

@st.cache_data(ttl=300) # 缓存5分钟，避免频繁请求被封IP
def get_market_data():
    # 1. 获取前80名成交量的币种
    tickers = ex.fetch_tickers()
    top_80 = sorted(tickers.items(), key=lambda x: x[1].get('quoteVolume', 0), reverse=True)[:80]
    
    results = []
    bar = st.progress(0)
    for i, (sym_pair, data) in enumerate(top_80):
        if '/USDT' not in sym_pair: continue
        try:
            # 2. 获取日线算 200MA
            daily = ex.fetch_ohlcv(sym_pair, timeframe='1d', limit=205)
            df_daily = pd.DataFrame(daily, columns=['ts','o','h','l','c','v'])
            ma200 = df_daily['c'].rolling(window=200).mean().iloc[-1]
            current_price = df_daily['c'].iloc[-1]
            
            # 3. 计算偏离度和涨跌幅
            dist_ma200 = (current_price - ma200) / ma200 * 100
            change_24h = data.get('percentage', 0)
            
            results.append({
                "币种": sym_pair,
                "当前价格": current_price,
                "200MA": round(ma200, 4),
                "偏离200MA (%)": round(dist_ma200, 2),
                "24h涨跌 (%)": round(change_24h, 2),
                "状态": "🔥 趋势之上" if current_price > ma200 else "❄️ 趋势之下"
            })
            bar.progress((i + 1) / len(top_80))
        except:
            continue
    return pd.DataFrame(results)

# 运行扫描
if st.button('🔄 立即刷新数据'):
    st.cache_data.clear()

try:
    df = get_market_data()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("💎 真命天子 (200MA 之上)")
        st.info("这些是真正的强势趋势币，回本的希望在这里。")
        strong_df = df[df['状态'] == "🔥 趋势之上"].sort_values(by="偏离200MA (%)", ascending=False)
        st.dataframe(strong_df.style.applymap(lambda x: 'color: #00ff00' if isinstance(x, float) and x > 0 else '', subset=['24h涨跌 (%)']))

    with col2:
        st.subheader("💀 僵尸资产 (200MA 之下)")
        st.warning("如果你的币在这里，且正在阴跌，说明它没有主力维护。")
        weak_df = df[df['状态'] == "❄️ 趋势之下"].sort_values(by="24h涨跌 (%)", ascending=False)
        st.dataframe(weak_df)

    st.markdown("---")
    st.write("### 💡 换仓策略说明")
    st.markdown("""
    1. **汰弱**：检查你手上的币是否在右侧【僵尸资产】列表中，且偏离 200MA 极远（比如 -30% 以下）。
    2. **留强**：在 08:00 - 08:30，如果左侧【真命天子】列表中的某个币突然出现**巨量拉升**，那就是最佳换仓机会。
    3. **纪律**：只在 200MA 之上的币种里寻找动量，不要试图去左侧接飞刀。
    """)

except Exception as e:
    st.error(f"获取数据失败，请稍后再试或检查网络。错误详情: {e}")
