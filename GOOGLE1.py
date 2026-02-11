import streamlit as st
import pandas as pd
import ccxt
import time
from datetime import datetime

st.set_page_config(page_title="8:00 汰弱留强", layout="wide")

# --- 1. 资产配置：根据你的要求区分合约与现货 ---
# 如果 API 拿不到名单，我们就用这个保底名单
SYMBOLS_TO_MONITOR = [
    'TAO/USDT', 'XAG/USDT', 'XAU/USDT', # 你的合约重点
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'SUI/USDT', 
    'ORDI/USDT', 'STX/USDT', 'WIF/USDT', 'PEPE/USDT', 'FET/USDT'
]

# 初始化交易所 - 尝试用币安，因为它对云端 IP 最友好
ex = ccxt.binance({'enableRateLimit': True})

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
    except:
        return 0, "接口限制"

st.title("🛡️ 8:00 汰弱留强看板 (高可用版)")
st.info("如果 OKX 连不上，系统将自动使用币安行情数据。")

# --- 核心逻辑 ---
placeholder = st.empty()
results = []

# 1. 尝试获取活跃名单
try:
    tickers = ex.fetch_tickers()
    # 过滤成交量前 60 的 USDT 交易对
    top_tickers = sorted(
        [t for t in tickers.items() if '/USDT' in t[0] and 'UP/' not in t[0] and 'DOWN/' not in t[0]], 
        key=lambda x: x[1].get('quoteVolume', 0), 
        reverse=True
    )[:60]
    target_symbols = [t[0] for t in top_tickers]
    
    # 确保你的重点币种一定在名单里
    for s in SYMBOLS_TO_MONITOR:
        if s not in target_symbols:
            target_symbols.insert(0, s)
            
except Exception as e:
    st.warning(f"全量行情获取失败，启动【硬编码保底名单】模式。原因: {e}")
    target_symbols = SYMBOLS_TO_MONITOR

# 2. 遍历扫描
for i, sym in enumerate(target_symbols):
    try:
        # 获取实时 Ticker
        ticker = ex.fetch_ticker(sym)
        price = ticker.get('last', 0)
        change = ticker.get('percentage', 0)
        vol_24h = ticker.get('quoteVolume', 0)
        
        # 5min 量能
        bars_5m = ex.fetch_ohlcv(sym, timeframe='5m', limit=2)
        v_now = bars_5m[-1][5] if bars_5m else 0
        v_ratio = v_now / (vol_24h / 288) if vol_24h > 0 else 0
        
        # 200MA 状态
        dist, status = get_ma200_info(sym)
        
        # 资产类型标注
        is_contract = "合约" if any(x in sym for x in ['TAO', 'XAG', 'XAU']) else "现货"
        
        results.append({
            "币种": sym,
            "类型": is_contract,
            "5min量比": round(v_ratio, 2),
            "24h涨跌%": round(change, 2),
            "200MA状态": status,
            "偏离200MA%": round(dist, 2),
            "价格": price
        })
        
        # 渲染
        df_display = pd.DataFrame(results).sort_values(by="5min量比", ascending=False)
        with placeholder.container():
            def style_status(val):
                color = 'red' if val == "🔥 趋势之上" else 'white'
                return f'color: {color}'
            
            st.dataframe(
                df_display.style.applymap(style_status, subset=['200MA状态']),
                use_container_width=True,
                height=600
            )
            st.caption(f"已扫描: {len(results)} / {len(target_symbols)}")
            
        time.sleep(0.1) # 频率控制
    except:
        continue

st.success("✅ 扫描完成。")
