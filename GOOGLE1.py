import streamlit as st
import pandas as pd
import ccxt
import time
from datetime import datetime

st.set_page_config(page_title="8:00 精准汰弱留强", layout="wide")

# 1. 资产定义
CONTRACTS = ['TAO/USDT', 'XAG/USDT', 'XAU/USDT']
STABLES = ['USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'EUR', 'USDE']

# 初始化交易所 - 改回 OKX 或 Gate 均可，关键在逻辑
ex = ccxt.gateio({'enableRateLimit': True})

def get_accurate_metrics(sym):
    """精准计算量比和MA"""
    try:
        # 抓取 1 小时的 5min 线 (12 根) 算平均，抓日线算 MA
        bars_5m = ex.fetch_ohlcv(sym, timeframe='5m', limit=13)
        daily = ex.fetch_ohlcv(sym, timeframe='1d', limit=205)
        
        if len(bars_5m) < 12 or len(daily) < 200:
            return 0, 0, "数据不足"
        
        # --- 精准量比计算 ---
        current_v = bars_5m[-1][5] # 最近 5min 成交量
        past_v_avg = sum([b[5] for b in bars_5m[:-1]]) / (len(bars_5m)-1)
        # 量比 = 当前 5min / 过去 1 小时均值
        v_ratio = current_v / past_v_avg if past_v_avg > 0 else 0
        
        # --- 趋势计算 ---
        df_daily = pd.DataFrame(daily, columns=['ts','o','h','l','c','v'])
        ma200 = df_daily['c'].rolling(200).mean().iloc[-1]
        current_p = df_daily['c'].iloc[-1]
        
        status = "🔥 趋势之上" if current_p > ma200 else "❄️ 趋势之下"
        dist = (current_p - ma200) / ma200 * 100
        
        return v_ratio, dist, status
    except:
        return 0, 0, "接口限速"

st.title("🛡️ 8:00 汰弱留强：精准量化看板")
st.write(f"当前检测时间: {datetime.now().strftime('%H:%M:%S')}")

# 自动刷新
from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=30000, key="precise_refresh")

placeholder = st.empty()
results = []

# 名单获取 (Top 80)
try:
    tickers = ex.fetch_tickers()
    valid = [t for t in tickers.items() if '/USDT' in t[0] and not any(s in t[0] for s in STABLES)]
    top_80 = sorted(valid, key=lambda x: x[1].get('quoteVolume', 0), reverse=True)[:80]
    target_symbols = [t[0] for t in top_80]
    for s in reversed(CONTRACTS):
        if s in target_symbols: target_symbols.remove(s)
        target_symbols.insert(0, s)
except:
    target_symbols = CONTRACTS

# 执行扫描
for i, sym in enumerate(target_symbols):
    try:
        time.sleep(0.2)
        v_ratio, dist, status = get_accurate_metrics(sym)
        
        # 获取基础行情
        ticker = ex.fetch_ticker(sym)
        
        results.append({
            "币种": sym,
            "类型": "合约" if any(x in sym for x in CONTRACTS) else "现货",
            "5min量比(vs 1h)": round(v_ratio, 2),
            "24h涨跌%": round(ticker.get('percentage', 0), 2),
            "200MA状态": status,
            "偏离200MA%": round(dist, 2),
            "价格": ticker.get('last', 0)
        })
        
        # 实时排序并渲染
        df_display = pd.DataFrame(results).sort_values(by="5min量比(vs 1h)", ascending=False)
        with placeholder.container():
            st.dataframe(
                df_display.style.applymap(lambda x: 'background-color: #ff4b4b' if x == "🔥 趋势之上" else '', subset=['200MA状态']),
                use_container_width=True,
                height=600
            )
            st.caption(f"已校准数据: {len(results)} / {len(target_symbols)}")
    except:
        continue
