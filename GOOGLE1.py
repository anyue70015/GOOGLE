import streamlit as st
import pandas as pd
import ccxt
import time
from datetime import datetime

st.set_page_config(page_title="8:00 汰弱留强-Gate版", layout="wide")

# 1. 资产定义
CONTRACTS = ['TAO/USDT', 'XAG/USDT', 'XAU/USDT']
STABLES = ['USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'EUR']

# 使用 Gate.io，因为它对美国云端 IP 限制较少
ex = ccxt.gateio({'enableRateLimit': True})

def get_ma200_info(sym):
    try:
        # 抓取日线
        daily = ex.fetch_ohlcv(sym, timeframe='1d', limit=205)
        if len(daily) < 200: return 0, "数据不足"
        df = pd.DataFrame(daily, columns=['ts','o','h','l','c','v'])
        ma200 = df['c'].rolling(200).mean().iloc[-1]
        price = df['c'].iloc[-1]
        status = "🔥 趋势之上" if price > ma200 else "❄️ 趋势之下"
        dist = (price - ma200) / ma200 * 100
        return dist, status
    except Exception:
        return 0, "接口限速"

st.title("🛡️ 8:00 汰弱留强看板 (Gate.io 链路)")
st.write(f"当前时间: {datetime.now().strftime('%H:%M:%S')}")

# 自动刷新
from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=45000, key="gate_refresh")

placeholder = st.empty()
results = []

# 2. 获取名单
try:
    with st.spinner('正在从 Gate.io 同步行情...'):
        tickers = ex.fetch_tickers()
    # 筛选成交量大的 USDT 对
    valid_tickers = [t for t in tickers.items() if '/USDT' in t[0] and not any(s in t[0] for s in STABLES)]
    top_list = sorted(valid_tickers, key=lambda x: x[1].get('quoteVolume', 0), reverse=True)[:60]
    target_symbols = [t[0] for t in top_list]
    
    # 强制把你的重点币种塞进去
    for s in CONTRACTS:
        if s not in target_symbols:
            target_symbols.insert(0, s)
except Exception as e:
    st.error(f"Gate.io 名单获取失败: {e}")
    target_symbols = CONTRACTS # 最终保底

# 3. 逐个循环
for i, sym in enumerate(target_symbols):
    try:
        ticker = ex.fetch_ticker(sym)
        price = ticker.get('last', 0)
        change = ticker.get('percentage', 0)
        vol_24h = ticker.get('quoteVolume', 0)
        
        # 5min 量能
        bars_5m = ex.fetch_ohlcv(sym, timeframe='5m', limit=2)
        v_now = bars_5m[-1][5] if bars_5m else 0
        v_ratio = v_now / (vol_24h / 288) if vol_24h > 0 else 0
        
        # 趋势
        dist, status = get_ma200_info(sym)
        
        # 标注
        asset_label = "合约" if any(x in sym for x in ['TAO', 'XAG', 'XAU']) else "现货"
        
        results.append({
            "币种": sym,
            "类型": asset_label,
            "5min量比": round(v_ratio, 2),
            "24h涨跌%": round(change, 2),
            "200MA状态": status,
            "偏离200MA%": round(dist, 2),
            "价格": price
        })
        
        # 渲染
        df_display = pd.DataFrame(results).sort_values(by="5min量比", ascending=False)
        with placeholder.container():
            def highlight(val):
                return 'color: #ff4b4b; font-weight: bold' if val == "🔥 趋势之上" else ''
            
            st.dataframe(
                df_display.style.applymap(highlight, subset=['200MA状态']),
                use_container_width=True,
                height=600
            )
            st.caption(f"已加载: {len(results)} / {len(target_symbols)}")
        
        time.sleep(0.2) # Gate.io 频率限制较严，慢即是稳
    except:
        continue

st.success("✅ 扫描完成")
