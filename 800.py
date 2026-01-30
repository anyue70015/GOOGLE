import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="指挥部-全周期监控版", layout="wide")

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "ZEC", "ASTER"]
TIMEFRAMES = {
    '1m涨跌': '1m',
    '5m涨跌': '5m',
    '15m涨跌': '15m',
    '1h涨跌': '1h'
}

# ==========================================
# 2. 核心抓取逻辑：多周期回溯
# ==========================================
def fetch_multi_timeframe_data(symbol):
    pair = f"{symbol}/USDT"
    # TAO 优先 Bitget，其他常用 OKX
    exchange_list = ['bitget', 'okx'] if symbol in ['TAO', 'HYPE', 'ASTER'] else ['okx', 'bitget']
    
    res = {"币种": symbol, "最新价": 0.0}
    
    for eid in exchange_list:
        try:
            ex = getattr(ccxt, eid)({'timeout': 5000, 'enableRateLimit': True})
            ticker = ex.fetch_ticker(pair)
            curr_p = ticker['last']
            res["最新价"] = curr_p
            res["24h涨跌"] = ticker.get('percentage', 0.0)
            
            # 抓取不同周期的涨跌
            for label, tf in TIMEFRAMES.items():
                try:
                    # 抓取最近 2 根 K 线：index 0 是前一根(已闭合)，index 1 是当前根
                    ohlcv = ex.fetch_ohlcv(pair, timeframe=tf, limit=2)
                    if len(ohlcv) >= 2:
                        base_p = ohlcv[0][4] # 前一根的收盘价
                        res[label] = ((curr_p - base_p) / base_p) * 100
                    else:
                        res[label] = 0.0
                except:
                    res[label] = 0.0
            
            res["来源"] = eid.upper()
            return res # 成功抓取一个交易所就返回
        except:
            continue
            
    # 兜底数据
    return {**{"币种": symbol, "最新价": 0.0, "24h涨跌": 0.0}, **{k: 0.0 for k in TIMEFRAMES}, "来源": "失败"}

# ==========================================
# 3. UI 渲染与自动刷新
# ==========================================
st.title("🛡️ 2026 金融风暴：多维度全周期监控")

placeholder = st.empty()

while True:
    # 全量并发抓取 (18个币同时多时段扫描)
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        results = list(executor.map(fetch_multi_timeframe_data, SYMBOLS))
    
    df = pd.DataFrame(results)
    
    # 排序：按 5 分钟波动最剧烈的排前面（最能反映瞬间插针）
    if '5m涨跌' in df.columns:
        df = df.sort_values(by="5m涨跌", ascending=True)

    # 格式化
    display_df = df.copy()
    cols_to_fix = ['24h涨跌', '1m涨跌', '5m涨跌', '15m涨跌', '1h涨跌']
    for col in cols_to_fix:
        display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%")

    with placeholder.container():
        st.write(f"🔄 **全周期同步成功** | 刷新时间: {time.strftime('%H:%M:%S')} | 频率: 10s/次")
        
        # TAO 专项报警
        tao_data = df[df['币种'] == 'TAO']
        if not tao_data.empty:
            t_5m = tao_data.iloc[0]['5m涨跌']
            if t_5m < -1: # 5分钟内跌超1%就是危险信号
                st.error(f"🔥 **TAO 正在插针**: 5分钟跌幅 {t_5m:.2f}% | 请检查 Bitget 杠杆仓位！")

        st.dataframe(display_df, use_container_width=True, height=650)

    time.sleep(10)
