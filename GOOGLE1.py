import streamlit as st
import pandas as pd
import ccxt
import time
from datetime import datetime

st.set_page_config(page_title="8:00 汰弱留强-硬核版", layout="wide")

# 1. 【硬编码名单】直接定义成交量前 80 的币种，不再依赖 API 自动获取名单
TOP_80_SYMBOLS = [
    'TAO/USDT', 'XAG/USDT', 'XAU/USDT', # 你的核心合约
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'SUI/USDT', 'XRP/USDT', 'ADA/USDT',
    'DOGE/USDT', 'TRX/USDT', 'TON/USDT', 'LINK/USDT', 'AVAX/USDT', 'SHIB/USDT', 'DOT/USDT',
    'BCH/USDT', 'NEAR/USDT', 'LTC/USDT', 'APT/USDT', 'PEPE/USDT', 'STX/USDT', 'ORDI/USDT',
    'RENDER/USDT', 'WIF/USDT', 'FET/USDT', 'TIA/USDT', 'ARB/USDT', 'OP/USDT', 'INJ/USDT',
    'FIL/USDT', 'LDO/USDT', 'JUP/USDT', 'PYTH/USDT', 'ENA/USDT', 'W/USDT', 'SATS/USDT',
    'FLOKI/USDT', 'GALA/USDT', 'GRT/USDT', 'AAVE/USDT', 'MKR/USDT', 'UNI/USDT', 'CRV/USDT',
    'ETC/USDT', 'DYDX/USDT', 'ENS/USDT', 'PENDLE/USDT', 'GAS/USDT', 'ARKM/USDT', 'AGIX/USDT'
    # ... (名单可根据需要继续增加)
]

# 初始化交易所 - 尝试用 OKX，如果报错则不中断
ex = ccxt.okx({'enableRateLimit': True})

def get_ma200_info(sym):
    try:
        daily = ex.fetch_ohlcv(sym, timeframe='1d', limit=205)
        if not daily or len(daily) < 200: return 0, "数据不足"
        df = pd.DataFrame(daily, columns=['ts','o','h','l','c','v'])
        ma200 = df['c'].rolling(200).mean().iloc[-1]
        price = df['c'].iloc[-1]
        status = "🔥 趋势之上" if price > ma200 else "❄️ 趋势之下"
        dist = (price - ma200) / ma200 * 100
        return dist, status
    except:
        return 0, "接口忙"

st.title("🛡️ 8:00 汰弱留强：硬核全名单监控")
st.write(f"当前时间: {datetime.now().strftime('%H:%M:%S')} | 已锁定目标: {len(TOP_80_SYMBOLS)} 个")

from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=60000, key="hard_refresh")

placeholder = st.empty()
results = []

# 直接对硬编码名单进行遍历
for i, sym in enumerate(TOP_80_SYMBOLS):
    try:
        # 增加延时防止被封
        time.sleep(0.3) 
        
        # 1. 获取行情
        ticker = ex.fetch_ticker(sym)
        price = ticker.get('last', 0)
        change = ticker.get('percentage', 0)
        vol_24h = ticker.get('quoteVolume', 0)
        
        # 2. 获取 5min 量能
        bars_5m = ex.fetch_ohlcv(sym, timeframe='5m', limit=2)
        v_now = bars_5m[-1][5] if bars_5m else 0
        v_ratio = v_now / (vol_24h / 288) if vol_24h > 0 else 0
        
        # 3. 获取 200MA (只对量比有波动的或重点币种算，节省频率)
        dist, status = 0, "待加载"
        if i < 15 or v_ratio > 1.1:
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
        
        # 实时渲染表格
        df_display = pd.DataFrame(results).sort_values(by="5min量比", ascending=False)
        with placeholder.container():
            def highlight_row(val):
                if val == "🔥 趋势之上": return 'background-color: #ff4b4b; color: white'
                return ''
            
            st.dataframe(
                df_display.style.applymap(highlight_row, subset=['200MA状态']),
                use_container_width=True,
                height=800
            )
            st.caption(f"已加载: {len(results)} / {len(TOP_80_SYMBOLS)}")
            
    except Exception as e:
        # 如果某个币报错，跳过继续下一个，保证表格不卡死
        continue

st.success("✅ 名单扫描完成。")
