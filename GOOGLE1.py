import streamlit as st
import pandas as pd
import ccxt
import time
from datetime import datetime

# --- 配置 ---
st.set_page_config(page_title="8:00 换仓狙击", layout="wide")
STABLECOINS = ['USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'USDE', 'USDG', 'PYUSD', 'EUR', 'USDS']

# 初始化交易所
ex = ccxt.okx({'enableRateLimit': True})

def get_ma200_safe(sym):
    """安全获取200MA，失败返回0"""
    try:
        daily = ex.fetch_ohlcv(sym, timeframe='1d', limit=200)
        if len(daily) < 150: return 0
        df = pd.DataFrame(daily, columns=['ts','o','h','l','c','v'])
        return df['c'].mean()
    except:
        return 0

# --- 侧边栏设置 ---
st.sidebar.header("⚙️ 扫描设置")
scan_count = st.sidebar.slider("扫描币种数量", 10, 80, 40) # 建议先开40个，速度最快

# --- 主界面 ---
st.title("🎯 8:00 汰弱留强系统")
st.write(f"最后更新: {datetime.now().strftime('%H:%M:%S')}")

# 自动刷新
from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=30000, key="fresher") # 云端建议 30秒 刷一次

# 1. 获取行情快照 (这一步极快)
try:
    tickers = ex.fetch_tickers()
    valid_list = [s for s in tickers.items() if '/USDT' in s[0] and not any(sc in s[0] for sc in STABLECOINS)]
    top_coins = sorted(valid_list, key=lambda x: x[1].get('quoteVolume', 0), reverse=True)[:scan_count]
except Exception as e:
    st.error(f"无法连接交易所: {e}")
    st.stop()

# 2. 核心数据抓取 (带实时反馈)
results = []
status_placeholder = st.empty()
table_placeholder = st.empty()

for i, (sym, data) in enumerate(top_coins):
    status_placeholder.text(f"⚡ 正在分析 ({i+1}/{scan_count}): {sym}")
    try:
        price = data.get('last', 0)
        change = data.get('percentage', 0)
        vol_24h = data.get('quoteVolume', 0)
        
        # 抓 5min 线算量比
        bars_5m = ex.fetch_ohlcv(sym, timeframe='5m', limit=2)
        v_now = bars_5m[-1][5] if bars_5m else 0
        avg_v_5min = vol_24h / 288
        v_ratio = v_now / avg_v_5min if avg_v_5min > 0 else 0
        
        # 只要量比有苗头，立刻算 200MA
        ma200 = 0
        if v_ratio > 1.0 or i < 10:
            ma200 = get_ma200_safe(sym)
        
        dist_ma = ((price - ma200) / ma200 * 100) if ma200 > 0 else 0
        status = "🔥 趋势之上" if (ma200 > 0 and price > ma200) else "❄️ 趋势之下"
        
        results.append({
            "币种": sym,
            "5min量比": round(v_ratio, 2),
            "24h涨跌%": round(change, 2),
            "偏离200MA%": round(dist_ma, 2),
            "价格": price,
            "状态": status
        })
        
        # 每抓 5 个币，刷新一次表格，让你不用等
        if len(results) % 5 == 0:
            with table_placeholder.container():
                temp_df = pd.DataFrame(results)
                st.dataframe(temp_df.sort_values(by='5min量比', ascending=False), use_container_width=True)
                
    except Exception as e:
        continue

status_placeholder.success("✅ 全盘扫描完成")

# 3. 最终信号展示
final_df = pd.DataFrame(results)
if not final_df.empty:
    st.divider()
    st.subheader("🚨 换仓信号建议")
    # 只要满足：趋势向上 + 量能翻倍
    signals = final_df[(final_df['5min量比'] > 2.0) & (final_df['状态'] == "🔥 趋势之上")]
    
    if not signals.empty:
        st.error("发现爆发标的！符合汰弱留强逻辑：")
        st.table(signals.sort_values(by='5min量比', ascending=False))
    else:
        st.info("暂无 200MA 之上的爆发信号。")
