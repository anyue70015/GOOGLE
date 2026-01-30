import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="指挥部-全滚动最终版", layout="wide")

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC","ZEC", "ASTER"]
EXCHANGES = {'OKX': 'okx', 'Bitget': 'bitget', 'Gate': 'gateio', 'Huobi': 'htx'}

def fetch_all_rolling(symbol):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol}
    
    # 确定主交易所节点
    main_ex_id = 'bitget' if symbol in ['TAO', 'HYPE', 'ASTER', 'ZEC'] else 'okx'
    main_ex = getattr(ccxt, main_ex_id)({'timeout': 5000})
    
    try:
        # 1. 抓取 Ticker (自带滚动 24h 涨跌)
        tk = main_ex.fetch_ticker(pair)
        curr_p = tk['last']
        res["最新价"] = curr_p
        res["24h"] = tk['percentage'] # 交易所原生的 Rolling 24h
        
        # 2. 精确滚动回溯 (1m, 5m, 15m, 1h)
        now_ms = main_ex.milliseconds()
        offsets = {
            "1m": 60 * 1000,
            "5m": 5 * 60 * 1000,
            "15m": 15 * 60 * 1000,
            "1h": 60 * 60 * 1000
        }
        
        for label, ms in offsets.items():
            # 回溯到精确的时间点拿那一根 1 分钟线作为基准
            k = main_ex.fetch_ohlcv(pair, '1m', since=now_ms - ms - 1000, limit=1)
            if k:
                base_p = k[0][4]
                res[label] = ((curr_p - base_p) / base_p) * 100
            else:
                res[label] = 0.0

        # 3. 聚合四大交易所实时净流 (最近 50 笔)
        total_flow = 0.0
        for eid in EXCHANGES.values():
            try:
                ex = getattr(ccxt, eid)({'timeout': 2000})
                trades = ex.fetch_trades(pair, limit=50)
                total_flow += sum([(t['price'] * t['amount']) if t['side'] == 'buy' else -(t['price'] * t['amount']) for t in trades])
            except: continue
        
        flow_wan = round(total_flow / 10000, 2)
        res["聚合净流(万)"] = flow_wan
        
        # 4. 战术诊断逻辑 (Rolling Logic)
        diag = "🔎 震荡博弈"
        if res["1h"] < -3 and flow_wan < -30:
            diag = "💀 主力跑了"
        elif res["1h"] < -5 and res["1m"] > 0.3 and flow_wan > 5:
            diag = "🛒 抄底信号"
        elif res["24h"] < -10 and res["1h"] > 0:
            diag = "💎 主力吸筹"
        elif res["1m"] > 0.5 and flow_wan < -10:
            diag = "⚠️ 诱多空涨"
            
        res["战术诊断"] = diag
            
    except:
        return None
    return res

# ==========================================
# 3. UI 界面布局
# ==========================================
st.title("🛰️ 全网聚合·全滚动时窗指挥部")

placeholder = st.empty()

while True:
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        results = list(executor.map(fetch_all_rolling, SYMBOLS))
    
    df = pd.DataFrame([r for r in results if r is not None])
    
    # --- 核心排序：1分钟涨幅置顶 ---
    df = df.sort_values(by="1m", ascending=False)

    display_df = df.copy()
    pct_cols = ["1m", "5m", "15m", "1h", "24h"]
    for c in pct_cols:
        display_df[c] = display_df[c].apply(lambda x: f"{x:+.2f}%")

    with placeholder.container():
        st.write(f"📊 **2026.01.30 实时风控** | 刷新: {time.strftime('%H:%M:%S')} | **模式：全时段 Rolling**")
        
        # 优化显示顺序和列宽
        order = ["币种", "最新价", "战术诊断", "1m", "5m", "15m", "1h", "24h", "聚合净流(万)"]
        st.dataframe(
            display_df[order],
            use_container_width=True,
            height=660
        )
        
        # 底部跑马灯预警
        if not df.empty:
            heavy_sell = df[df['聚合净流(万)'] < -50]
            if not heavy_sell.empty:
                st.error(f"🔥 **严重抛售**: {', '.join(heavy_sell['币种'].tolist())} 正面临全网大规模抛压！")

    time.sleep(10) # 建议 10 秒刷新一次，抓取 1m 滚动的变化
