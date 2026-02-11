import streamlit as st
import pandas as pd
import ccxt
from datetime import datetime
import time

# --- 页面配置 ---
st.set_page_config(page_title="8:00 换仓决策系统", layout="wide")

# 1. 黑名单：彻底过滤掉稳定币，不浪费屏幕空间
STABLECOINS = ['USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'USDE', 'USDG', 'PYUSD', 'EUR', 'USDS', 'USDM']

# 2. 初始化交易所 (使用 OKX 接口，香港/新加坡服务器访问最快)
ex = ccxt.okx()

def get_data():
    # 获取实时行情
    tickers = ex.fetch_tickers()
    # 筛选成交量前 80 且非稳定币的 USDT 对
    valid_list = [s for s in tickers.items() if '/USDT' in s[0] and not any(sc in s[0] for sc in STABLECOINS)]
    top_80 = sorted(valid_list, key=lambda x: x[1].get('quoteVolume', 0), reverse=True)[:80]

    results = []
    # 进度条
    progress_bar = st.progress(0)
    
    for i, (sym, data) in enumerate(top_80):
        try:
            # 抓取 5 分钟线 (看最近 15 分钟的持续性)
            bars_5m = ex.fetch_ohlcv(sym, timeframe='5m', limit=3)
            # 抓取日线 (算 200MA)
            daily = ex.fetch_ohlcv(sym, timeframe='1d', limit=200)
            
            # --- 逻辑 A：5 分钟平滑量能 ---
            v_5m_now = bars_5m[-1][5] # 最近一个 5min 成交量
            # 24h 平均 5min 成交量 = 总量 / 288
            avg_v_5m = data['quoteVolume'] / 288
            v_ratio = v_5m_now / avg_v_5m if avg_v_5m > 0 else 0
            
            # --- 逻辑 B：200MA 趋势 ---
            df_daily = pd.DataFrame(daily, columns=['ts','o','h','l','c','v'])
            ma200 = df_daily['c'].mean()
            current_price = data['last']
            dist_ma200 = (current_price - ma200) / ma200 * 100
            
            # --- 逻辑 C：综合评分 ---
            # 只有在 200MA 之上且放量的才给高分
            score = 0
            if current_price > ma200: score += 50
            if v_ratio > 3: score += 30
            if data['percentage'] > 0: score += 20

            results.append({
                "币种": sym,
                "5min量比": round(v_ratio, 2),
                "24h涨跌%": round(data['percentage'], 2),
                "偏离200MA%": round(dist_ma200, 2),
                "价格": current_price,
                "状态": "🔥 趋势之上" if current_price > ma200 else "❄️ 趋势之下",
                "综合评分": score
            })
            progress_bar.progress((i + 1) / len(top_80))
        except: continue
    return pd.DataFrame(results)

# --- Streamlit 界面 ---
st.title("🎯 8:00 汰弱留强：换仓狙击系统")
st.write(f"实时扫描频率: 每 15 秒 | 当前北京时间: {datetime.now().strftime('%H:%M:%S')}")

# 自动刷新逻辑
from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=15 * 1000, key="datarefresh")

df = get_data()

# --- 1. 狙击区 (核心信号) ---
st.subheader("🚨 换仓指令：真命天子名单")
# 严格过滤：量比 > 2 且 必须在 200MA 之上
signals = df[(df['5min量比'] > 2.0) & (df['状态'] == "🔥 趋势之上")].sort_values(by='综合评分', ascending=False)

if not signals.empty:
    st.warning("检测到强势爆发！建议将右侧【僵尸资产】卖出，换入以下品种：")
    # 高亮显示
    st.table(signals.style.background_gradient(cmap='Reds', subset=['5min量比', '综合评分']))
else:
    st.info("目前 8:00 盘面平稳。若此时成交量低迷，建议暂不换仓。")

# --- 2. 对比区 (你的存量资产对照) ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("💎 强者池 (Top 200MA)")
    st.dataframe(df[df['状态'] == "🔥 趋势之上"].sort_values(by='5min量比', ascending=False), use_container_width=True)

with col2:
    st.subheader("💀 僵尸池 (Below 200MA)")
    st.write("检查你手上的币是否在这里。如果是，请等待左侧信号出现时执行换仓。")
    st.dataframe(df[df['状态'] == "❄️ 趋势之下"].sort_values(by='24h涨跌%', ascending=True), use_container_width=True)

st.markdown("---")
st.write("### 📖 执行手册")
st.markdown("""
1. **扫描阶段 (08:00-08:05)**: 盯着红色【换仓指令】表。
2. **确认阶段 (08:05-08:10)**: 如果某个币连续两次刷新都在榜单，说明资金流入真实。
3. **换仓动作**: 
    - 卖掉【僵尸池】里那些偏离 200MA 超过 -20% 的币。
    - 买入【真命天子名单】中量比最高的币。
4. **止损设定**: 若换入后跌破 08:00 开盘价，视为失败，立刻回撤到 USDT。
""")
