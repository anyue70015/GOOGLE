import streamlit as st
import pandas as pd
import ccxt
from datetime import datetime
import time

# --- 页面配置 ---
st.set_page_config(page_title="8:00 换仓决策系统 (稳定版)", layout="wide")

# 1. 黑名单：彻底过滤掉稳定币，不浪费屏幕空间
STABLECOINS = ['USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'USDE', 'USDG', 'PYUSD', 'EUR', 'USDS', 'USDM', 'BUSD']

# 2. 初始化交易所 (增加配置以提高稳定性)
ex = ccxt.okx({
    'enableRateLimit': True, # 自动处理频率限制
    'timeout': 30000,
})

@st.cache_data(ttl=20) # 20秒缓存，防止云端频繁请求被封IP
def get_data():
    # 预定义完整的列名，防止 KeyError
    columns = ["币种", "5min量比", "24h涨跌%", "偏离200MA%", "价格", "状态", "综合评分"]
    
    try:
        tickers = ex.fetch_tickers()
    except Exception as e:
        st.error(f"无法获取行情数据: {e}")
        return pd.DataFrame(columns=columns)

    # 筛选 Top 80 非稳定币
    valid_list = [s for s in tickers.items() if '/USDT' in s[0] and not any(sc in s[0] for sc in STABLECOINS)]
    top_80 = sorted(valid_list, key=lambda x: x[1].get('quoteVolume', 0), reverse=True)[:80]

    results = []
    # 模拟一个静态进度条，或者简单的处理提示
    status_text = st.empty()
    
    for i, (sym, data) in enumerate(top_80):
        try:
            # 减少每分钟请求次数，如果是云端运行，增加一个小延时很有必要
            time.sleep(0.05) 
            
            # 获取日线 (算 200MA) 和 5分钟线
            bars_5m = ex.fetch_ohlcv(sym, timeframe='5m', limit=2)
            daily = ex.fetch_ohlcv(sym, timeframe='1d', limit=200)
            
            if len(bars_5m) < 1 or len(daily) < 1:
                continue

            # --- 逻辑 A：5 分钟平滑量能 ---
            v_5m_now = bars_5m[-1][5] # 最近一个 5min 成交量
            avg_v_5m = (data.get('quoteVolume', 0)) / 288
            v_ratio = v_5m_now / avg_v_5m if avg_v_5m > 0 else 0
            
            # --- 逻辑 B：200MA 趋势 ---
            df_daily = pd.DataFrame(daily, columns=['ts','o','h','l','c','v'])
            ma200 = df_daily['c'].mean()
            current_price = data.get('last', 0)
            dist_ma200 = ((current_price - ma200) / ma200 * 100) if ma200 > 0 else 0
            
            # --- 逻辑 C：综合评分 ---
            score = 0
            if current_price > ma200: score += 50
            if v_ratio > 2.5: score += 30
            if data.get('percentage', 0) > 0: score += 20

            results.append({
                "币种": sym,
                "5min量比": round(v_ratio, 2),
                "24h涨跌%": round(data.get('percentage', 0), 2),
                "偏离200MA%": round(dist_ma200, 2),
                "价格": current_price,
                "状态": "🔥 趋势之上" if current_price > ma200 else "❄️ 趋势之下",
                "综合评分": score
            })
            status_text.text(f"正在扫描: {sym} ({i+1}/80)")
        except:
            continue
            
    status_text.empty() # 扫描完清空提示

    if not results:
        return pd.DataFrame(columns=columns)
    
    return pd.DataFrame(results)

# --- Streamlit 界面 ---
st.title("🎯 8:00 汰弱留强：云端狙击看板")
st.write(f"实时北京时间: {datetime.now().strftime('%H:%M:%S')} (每 20s 自动刷新)")

# 自动刷新插件 (需要 pip install streamlit-autorefresh)
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=20 * 1000, key="pro_datarefresh")
except ImportError:
    st.warning("建议安装 streamlit-autorefresh 以实现自动刷新。")

# 获取数据
df = get_data()

# 核心渲染逻辑
if not df.empty and '5min量比' in df.columns:
    # 1. 狙击区 (符合条件的币)
    st.subheader("🚨 换仓指令：真命天子名单")
    # 宽松一点过滤量比，确保 8:00 能看到东西
    signals = df[(df['5min量比'] > 1.5) & (df['状态'] == "🔥 趋势之上")].sort_values(by='综合评分', ascending=False)

    if not signals.empty:
        st.success("检测到潜在换仓目标！")
        st.table(signals.style.background_gradient(cmap='Reds', subset=['5min量比', '综合评分']))
    else:
        st.info("当前暂无强力爆发信号（若在 08:00 附近，请保持关注）")

    # 2. 对照展示
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("💎 趋势之上 (强)")
        st.dataframe(df[df['状态'] == "🔥 趋势之上"].sort_values(by='5min量比', ascending=False))
    with c2:
        st.subheader("❄️ 趋势之下 (弱)")
        st.dataframe(df[df['状态'] == "❄️ 趋势之下"].sort_values(by='24h涨跌%', ascending=True))
else:
    st.warning("正在等待 API 数据响应，请点击按钮手动刷新或等待 20 秒...")
    if st.button('点击手动刷新'):
        st.cache_data.clear()
        st.rerun()

st.markdown("---")
st.info("💡 提示：只在左侧【趋势之上】且【5min量比】爆表时，才把右侧的【趋势之下】亏损币卖掉换过去。")
