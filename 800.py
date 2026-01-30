import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="指挥部-彻底修复版", layout="wide")

SYMBOLS = ["BTC", "ETH", "SOL", "AAVE", "DOGE", "TAO", "SUI", "RENDER", "UNI", "HYPE", "XRP","ADA", "BCH", "LINK", "LTC", "TRX", "ZEC", "ASTER"]
EXCHANGE_IDS = {'OKX': 'okx', 'Gate': 'gateio', 'Huobi': 'htx', 'Bitget': 'bitget'}
ALL_CH_COLS = ['1m涨跌', '5m涨跌', '15m涨跌', '1h涨跌', '4h涨跌', '24h涨跌', '7d涨跌']

if 'cache' not in st.session_state: st.session_state.cache = {}

# ==========================================
# 2. 核心抓取引擎 (精准时间窗口)
# ==========================================
def fetch_worker(symbol, base_threshold, is_slow_tick):
    pair = f"{symbol}/USDT"
    local_threshold = base_threshold if symbol in ['BTC', 'ETH'] else base_threshold / 4
    
    res = {"币种": symbol, "最新价": "NO", "OBV预警": "正常", "net_flow": 0, "active_count": 0}
    # 继承缓存，防止 NO 刷屏
    if symbol in st.session_state.cache: res.update(st.session_state.cache[symbol])

    # --- 策略：找到第一个能提供行情的数据源 ---
    target_ex = None
    for ex_name in ['OKX', 'Gate', 'Bitget']:
        try:
            ex = getattr(ccxt, EXCHANGE_IDS[ex_name])({'timeout': 2000, 'enableRateLimit': True})
            tk = ex.fetch_ticker(pair)
            res["最新价"] = tk['last']
            now_ms = ex.milliseconds()
            
            # 1. 短周期 (总是刷新)
            for tf, col in zip(['1m', '5m', '15m'], ['1m涨跌', '5m涨跌', '15m涨跌']):
                # 拿 2 根，第一根就是我们要的“滚动起点”
                k = ex.fetch_ohlcv(pair, tf, limit=2)
                if len(k) >= 2: res[col] = ((tk['last'] - k[0][4]) / k[0][4]) * 100

            # 2. 长周期 (滚动窗口精准对齐)
            if is_slow_tick:
                # 近1h: 找 60分钟前的点
                h1 = ex.fetch_ohlcv(pair, '1m', since=now_ms - 3600000, limit=1)
                if h1: res["1h涨跌"] = ((tk['last'] - h1[0][4]) / h1[0][4]) * 100
                
                # 近24h: 找 86400秒前的点 (彻底解决8点问题)
                d1 = ex.fetch_ohlcv(pair, '1h', since=now_ms - 86400000, limit=1)
                if d1: res["24h涨跌"] = ((tk['last'] - d1[0][4]) / d1[0][4]) * 100
                
                # 近7d
                w1 = ex.fetch_ohlcv(pair, '4h', since=now_ms - 604800000, limit=1)
                if w1: res["7d涨跌"] = ((tk['last'] - w1[0][4]) / w1[0][4]) * 100
            
            target_ex = ex_name
            break # 成功找到数据源，跳出交易所循环
        except: continue

    # --- 3. 大单扫描 (保持多源) ---
    for name, eid in EXCHANGE_IDS.items():
        try:
            ex_trade = getattr(ccxt, eid)({'timeout': 1000})
            trades = ex_trade.fetch_trades(pair, limit=30)
            buy_sum = 0
            for t in trades:
                v = t['price'] * t['amount']
                res['net_flow'] += v if t['side'] == 'buy' else -v
                if t['side'] == 'buy' and v >= local_threshold: buy_sum += v
            res[name] = f"{buy_sum/10000:.1f}万" if buy_sum > 0 else "·"
            if buy_sum > 0: res['active_count'] += 1
        except: res[name] = "NO"

    res['OBV预警'] = f"💎底背离({target_ex})" if (res.get('1h涨跌', 0) < -0.3 and res['net_flow'] > 0) else f"正常({target_ex})"
    st.session_state.cache[symbol] = res
    return res

# ==========================================
# 3. 页面渲染 (略，同之前逻辑)
# ==========================================
