import streamlit as st
import pandas as pd
import ccxt
import time
from datetime import datetime

st.set_page_config(page_title="8:00 汰弱留强-Top80版", layout="wide")

# 1. 资产定义
CONTRACTS = ['TAO/USDT', 'XAG/USDT', 'XAU/USDT']
STABLES = ['USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'EUR', 'USDE', 'USDG']

# 初始化交易所
ex = ccxt.gateio({'enableRateLimit': True})

def get_ma200_info(sym):
    """安全获取200MA"""
    try:
        # 抓取日线
        daily = ex.fetch_ohlcv(sym, timeframe='1d', limit=205)
        if not daily or len(daily) < 200: return 0, "数据不足"
        df = pd.DataFrame(daily, columns=['ts','o','h','l','c','v'])
        ma200 = df['c'].rolling(200).mean().iloc[-1]
        price = df['c'].iloc[-1]
        status = "🔥 趋势之上" if price > ma200 else "❄️ 趋势之下"
        dist = (price - ma200) / ma200 * 100
        return dist, status
    except:
        return 0, "接口限速"

st.title("🛡️ 8:00 汰弱留强：Top 80 全监控看板")
st.write(f"当前时间: {datetime.now().strftime('%H:%M:%S')} (每 45s 自动扫描)")

# 自动刷新
from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=45000, key="top80_refresh")

placeholder = st.empty()
results = []

# 2. 获取 Top 80 名单
try:
    with st.spinner('正在同步 Top 80 行情...'):
        tickers = ex.fetch_tickers()
    
    # 筛选 USDT 对并排除稳定币
    valid_tickers = [
        t for t in tickers.items() 
        if '/USDT' in t[0] and not any(s in t[0] for s in STABLES)
    ]
    
    # 按 24h 成交额排序取前 80
    top_list = sorted(valid_tickers, key=lambda x: x[1].get('quoteVolume', 0), reverse=True)[:80]
    target_symbols = [t[0] for t in top_list]
    
    # 确保你的重点合约一定在 Top 80 名单首位
    for s in reversed(CONTRACTS):
        if s in target_symbols:
            target_symbols.remove(s)
        target_symbols.insert(0, s)
        
except Exception as e:
    st.error(f"无法获取名单: {e}")
    target_symbols = CONTRACTS

# 3. 逐个循环扫描数据
for i, sym in enumerate(target_symbols):
    try:
        # 稍微延时，防止被 Gate.io 彻底封锁
        time.sleep(0.15) 
        
        ticker = ex.fetch_ticker(sym)
        price = ticker.get('last', 0)
        change = ticker.get('percentage', 0)
        vol_24h = ticker.get('quoteVolume', 0)
        
        # 抓 5min 线算量比（这是 8:00 换仓的最核心指标）
        bars_5m = ex.fetch_ohlcv(sym, timeframe='5m', limit=2)
        v_now = bars_5m[-1][5] if bars_5m else 0
        v_ratio = v_now / (vol_24h / 288) if vol_24h > 0 else 0
        
        # 趋势状态：前 10 名和量比高的必算，其他的异步补齐
        dist, status = 0, "扫描中..."
        if i < 20 or v_ratio > 1.2:
             dist, status = get_ma200_info(sym)
        else:
             status = "等待确认"
        
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
        
        # 动态刷新表格
        df_display = pd.DataFrame(results).sort_values(by="5min量比", ascending=False)
        with placeholder.container():
            def highlight(val):
                if val == "🔥 趋势之上": return 'background-color: #ff4b4b; color: white'
                if val == "❄️ 趋势之下": return 'color: #888888'
                return ''
            
            st.dataframe(
                df_display.style.applymap(highlight, subset=['200MA状态']),
                use_container_width=True,
                height=800
            )
            st.caption(f"已同步 Top 80 进度: {len(results)} / {len(target_symbols)}")
            
    except Exception as e:
        continue

st.success(f"✅ Top 80 全量扫描完成。")
