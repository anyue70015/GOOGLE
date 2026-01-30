import streamlit as st
import pandas as pd
import ccxt
import time
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="指挥部-战术诊断版", layout="wide")

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "ZEC", "ASTER"]
EXCHANGES = {'OKX': 'okx', 'Bitget': 'bitget', 'Gate': 'gateio', 'Huobi': 'htx'}

# ==========================================
# 2. 核心抓取与诊断逻辑
# ==========================================
def fetch_and_diagnose(symbol):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol}
    
    # 聚合数据初始化
    total_flow_5m = 0.0
    prices = []
    main_ex_id = 'bitget' if symbol in ['TAO', 'HYPE', 'ASTER'] else 'okx'
    main_ex = getattr(ccxt, main_ex_id)({'timeout': 3000})

    # 多所聚合：最新价与净流
    for eid in EXCHANGES.values():
        try:
            ex = getattr(ccxt, eid)({'timeout': 2000})
            tk = ex.fetch_ticker(pair)
            prices.append(tk['last'])
            # 抓取 50 笔成交计算净流
            trades = ex.fetch_trades(pair, limit=50)
            total_flow_5m += sum([(t['price'] * t['amount']) if t['side'] == 'buy' else -(t['price'] * t['amount']) for t in trades])
        except: continue

    if not prices: return None
    
    avg_price = sum(prices) / len(prices)
    res["最新价"] = avg_price
    net_flow_wan = round(total_flow_5m / 10000, 2)
    res["全网净流(万)"] = net_flow_wan
    
    # 获取指标
    try:
        ohlcv_1h = main_ex.fetch_ohlcv(pair, '1h', limit=2)
        k_1m = main_ex.fetch_ohlcv(pair, '1m', limit=2)
        k_5m = main_ex.fetch_ohlcv(pair, '5m', limit=2)
        
        # 基础数据
        change_1m = ((avg_price - k_1m[0][4]) / k_1m[0][4] * 100) if len(k_1m)>=2 else 0.0
        change_1h = ((avg_price - ohlcv_1h[0][4]) / ohlcv_1h[0][4] * 100) if len(ohlcv_1h)>=2 else 0.0
        obv_in = avg_price > ohlcv_1h[0][4] # 1h OBV流入判定
        
        res["1m"] = change_1m
        res["1h"] = change_1h
        res["OBV"] = "流入" if obv_in else "流出"
        
        # --- 核心战术诊断 ---
        diag = "💡 观望"
        if not obv_in and net_flow_wan < -20:
            diag = "💀 主力跑了"
        elif change_1h < 0 and obv_in:
            diag = "💎 主力吸筹"
        elif change_1m < -0.3 and net_flow_wan > 10 and obv_in:
            diag = "🛒 分批抄底"
        elif change_1m > 0.3 and net_flow_wan < -10:
            diag = "⚠️ 诱多/空涨"
        elif abs(change_1m) > 1.5:
            diag = "⚡ 极端插针"
            
        res["战术诊断"] = diag
        
        # 补全其他周期数据用于显示
        for label, tf in {'5m':'5m', '15m':'15m', '24h':'1d'}.items():
            k = main_ex.fetch_ohlcv(pair, tf, limit=2)
            res[label] = ((avg_price - k[0][4]) / k[0][4] * 100) if len(k)>=2 else 0.0
            
    except:
        res.update({"战术诊断": "数据断开", "1m": 0, "OBV": "·"})
        
    return res

# ==========================================
# 3. 渲染界面
# ==========================================
st.title("🛰️ 全网聚合战术指挥部 (18币全量监控)")

placeholder = st.empty()



while True:
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        results = list(executor.map(fetch_and_diagnose, SYMBOLS))
    
    df = pd.DataFrame([r for r in results if r is not None])
    
    # 按 1m 涨幅大的排前面
    df = df.sort_values(by="1m", ascending=False)

    display_df = df.copy()
    # 整理列顺序
    cols = ["币种", "最新价", "战术诊断", "1m", "5m", "15m", "1h", "24h", "全网净流(万)", "OBV"]
    display_df = display_df[cols]
    
    # 格式化百分比
    for c in ["1m", "5m", "15m", "1h", "24h"]:
        display_df[c] = display_df[c].apply(lambda x: f"{x:+.2f}%")

    with placeholder.container():
        st.write(f"🔄 **战术引擎运行中** | 刷新时间: {time.strftime('%H:%M:%S')} | 聚合节点: OKX/Bitget/Gate/Huobi")
        
        # 18个币一屏全览
        st.dataframe(
            display_df,
            use_container_width=True,
            height=660
        )
        
        # 底部特别预警
        critical = df[df['战术诊断'].isin(["💀 主力跑了", "⚡ 极端插针"])]
        if not critical.empty:
            for _, row in critical.iterrows():
                st.error(f"🚨 高危警报：{row['币种']} 目前【{row['战术诊断']}】，请谨慎持有！")

    time.sleep(10)
