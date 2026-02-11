import streamlit as st
import pandas as pd
import ccxt
import time
from datetime import datetime

st.set_page_config(page_title="8:00 最终稳定版", layout="wide")

# 1. 【硬名单】直接写死 Top 80 活跃币种，确保名单永远不会变成只有一个
STABLE_LIST = [
    'TAO/USDT', 'XAG/USDT', 'XAU/USDT', 'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'SUI/USDT',
    'XRP/USDT', 'DOGE/USDT', 'ADA/USDT', 'TRX/USDT', 'TON/USDT', 'LINK/USDT', 'AVAX/USDT', 'SHIB/USDT',
    'DOT/USDT', 'BCH/USDT', 'NEAR/USDT', 'LTC/USDT', 'APT/USDT', 'PEPE/USDT', 'STX/USDT', 'ORDI/USDT',
    'RENDER/USDT', 'WIF/USDT', 'FET/USDT', 'TIA/USDT', 'ARB/USDT', 'OP/USDT', 'INJ/USDT', 'FIL/USDT',
    'LDO/USDT', 'JUP/USDT', 'PYTH/USDT', 'ENA/USDT', 'W/USDT', 'SATS/USDT', 'FLOKI/USDT', 'GALA/USDT',
    'GRT/USDT', 'AAVE/USDT', 'MKR/USDT', 'UNI/USDT', 'CRV/USDT', 'ETC/USDT', 'DYDX/USDT', 'ENS/USDT',
    'PENDLE/USDT', 'GAS/USDT', 'ARKM/USDT', 'NOT/USDT', 'SEI/USDT', 'RUNE/USDT', 'OM/USDT', 'BGB/USDT',
    'FTM/USDT', 'IMX/USDT', 'KAS/USDT', 'WLD/USDT', 'BONK/USDT', 'JASMY/USDT', 'AR/USDT', 'THETA/USDT'
]

# 初始化交易所
ex = ccxt.gateio({'enableRateLimit': True})

def get_stats(sym):
    """精准计算：量比(对比1h均值) 和 200MA"""
    try:
        # 抓取 5min 线 (13根，其中前12根算均值，最后1根是当前)
        bars = ex.fetch_ohlcv(sym, timeframe='5m', limit=13)
        # 抓取日线
        daily = ex.fetch_ohlcv(sym, timeframe='1d', limit=205)
        
        if not bars or not daily: return 0, 0, "无数据"
        
        # 量比逻辑：当前 5min 成交量 / 过去 1 小时(12根5min线)的平均量
        current_v = bars[-1][5]
        past_avg_v = sum([b[5] for b in bars[:-1]]) / 12
        v_ratio = current_v / past_avg_v if past_avg_v > 0 else 0
        
        # 200MA 逻辑
        df_d = pd.DataFrame(daily, columns=['t','o','h','l','c','v'])
        ma200 = df_d['c'].rolling(200).mean().iloc[-1]
        last_p = df_d['c'].iloc[-1]
        
        status = "🔥 趋势之上" if last_p > ma200 else "❄️ 趋势之下"
        dist = (last_p - ma200) / ma200 * 100
        
        return v_ratio, dist, status
    except:
        return 0, 0, "限速/错误"

st.title("🛡️ 8:00 汰弱留强：Top 80 精准监控")
st.write(f"当前时间: {datetime.now().strftime('%H:%M:%S')} | 锁定币种: {len(STABLE_LIST)}")

# 自动刷新 (45秒/次)
from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=45000, key="final_refresh")

placeholder = st.empty()
results = []

# 开始逐个“啃”名单
for i, sym in enumerate(STABLE_LIST):
    try:
        # 为了防封，必须给 0.2s 延时，跑完 80 个约 16s
        time.sleep(0.2)
        
        v_ratio, dist_ma, status = get_stats(sym)
        ticker = ex.fetch_ticker(sym)
        
        results.append({
            "币种": sym,
            "5min量比": round(v_ratio, 2),
            "200MA状态": status,
            "偏离200MA%": round(dist_ma, 2),
            "24h涨跌%": round(ticker.get('percentage', 0), 2),
            "价格": ticker.get('last', 0),
            "类型": "合约" if any(x in sym for x in ['TAO', 'XAG', 'XAU']) else "现货"
        })
        
        # 实时排序并动态刷新
        df_display = pd.DataFrame(results).sort_values(by="5min量比", ascending=False)
        with placeholder.container():
            def style_row(val):
                color = 'background-color: #ff4b4b; color: white' if val == "🔥 趋势之上" else ''
                return color

            st.dataframe(
                df_display.style.applymap(style_row, subset=['200MA状态']),
                use_container_width=True,
                height=800
            )
            st.caption(f"加载进度: {len(results)} / {len(STABLE_LIST)}")
            
    except:
        continue

st.success("✅ 扫描任务完成")
