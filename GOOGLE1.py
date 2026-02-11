import streamlit as st
import pandas as pd
import ccxt
import time
from datetime import datetime

# --- 基础配置 ---
st.set_page_config(page_title="8:00 全盘狙击看板", layout="wide")
STABLECOINS = ['USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'USDE', 'USDG', 'PYUSD', 'EUR', 'USDS', 'USDM']

# 初始化交易所
ex = ccxt.okx({'enableRateLimit': True})

def get_ma200_info(sym):
    """获取200MA信息"""
    try:
        daily = ex.fetch_ohlcv(sym, timeframe='1d', limit=200)
        if len(daily) < 150: return 0, "数据不足"
        df = pd.DataFrame(daily, columns=['ts','o','h','l','c','v'])
        ma200 = df['c'].mean()
        price = df['c'].iloc[-1]
        status = "🔥 趋势之上" if price > ma200 else "❄️ 趋势之下"
        dist = (price - ma200) / ma200 * 100
        return dist, status
    except:
        return 0, "获取失败"

st.title("🎯 Top 80 币种实时全量监控")
st.write(f"当前北京时间: {datetime.now().strftime('%H:%M:%S')} (每 30s 自动刷新)")

# 自动刷新
from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=30000, key="full_monitor")

# 1. 获取基础快照
try:
    tickers = ex.fetch_tickers()
    valid_list = [s for s in tickers.items() if '/USDT' in s[0] and not any(sc in s[0] for sc in STABLECOINS)]
    top_coins = sorted(valid_list, key=lambda x: x[1].get('quoteVolume', 0), reverse=True)[:80]
except Exception as e:
    st.error(f"连接失败: {e}")
    st.stop()

# 2. 循环抓取并直接显示
results = []
placeholder = st.empty()

for i, (sym, data) in enumerate(top_coins):
    try:
        price = data.get('last', 0)
        change = data.get('percentage', 0)
        vol_24h = data.get('quoteVolume', 0)
        
        # 抓 5min 量能
        bars_5m = ex.fetch_ohlcv(sym, timeframe='5m', limit=2)
        v_now = bars_5m[-1][5] if bars_5m else 0
        v_ratio = v_now / (vol_24h / 288) if vol_24h > 0 else 0
        
        # 抓 200MA 状态
        dist, status = get_ma200_info(sym)
        
        results.append({
            "币种": sym,
            "5min量比": round(v_ratio, 2),
            "24h涨跌%": round(change, 2),
            "200MA状态": status,
            "偏离200MA%": round(dist, 2),
            "当前价": price
        })
        
        # 实时更新表格，让用户不用等
        if len(results) % 3 == 0 or len(results) == len(top_coins):
            df_display = pd.DataFrame(results).sort_values(by="5min量比", ascending=False)
            with placeholder.container():
                # 使用 Pandas Styler 进行着色：趋势之上的标红
                def color_status(val):
                    color = 'red' if val == "🔥 趋势之上" else 'white'
                    return f'color: {color}'
                
                st.dataframe(
                    df_display.style.applymap(color_status, subset=['200MA状态']),
                    use_container_width=True,
                    height=800
                )
        
        # 稍微给点延时，防止被封
        time.sleep(0.05)
        
    except:
        continue

st.success(f"✅ 已完成 {len(results)} 个活跃币种扫描")
