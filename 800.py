import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
import requests
from concurrent.futures import ThreadPoolExecutor  # ← 这行必须有！修复 NameError

st.set_page_config(page_title="指挥部 - BTC Binance 专用完整版", layout="wide")

# 只保留 BTC
SYMBOLS = ["BTC"]

def get_tactical_logic(df, curr_p, flow, rsi, symbol, change_1m):
    atr_series = ta.atr(df['h'], df['l'], df['c'], length=14)
    atr_val = atr_series.iloc[-1] if atr_series is not None else 0
    atr_pct = (atr_val / curr_p) * 100 if curr_p != 0 else 0
    
    obv_series = ta.obv(df['c'], df['v'])
    obv_trend = "UP" if obv_series.iloc[-1] > obv_series.iloc[-2] else "DOWN"
    
    macd = ta.macd(df['c'])
    macd_status = "金叉" if macd['MACDh_12_26_9'].iloc[-1] > 0 else "死叉"
    
    diag = "🔎 观望"
    
    atr_threshold = 3.0  # BTC 大币阈值
    
    if rsi < 30 and obv_trend == "UP":
        diag = "🛒 底部吸筹"
    elif atr_pct > atr_threshold and macd_status == "死叉" and flow < -20:
        diag = "💀 确认破位"
    elif obv_trend == "DOWN" and rsi > 65:
        diag = "⚠️ 诱多虚涨"
    elif change_1m > 1.2 and flow > 20 and rsi > 55 and obv_trend == "UP":
        diag = "🚀 轻微偏强"
    elif change_1m < -1.2 and flow < -20:
        diag = "🩸 短线急跌"
        
    return diag, round(atr_pct, 2), "💎流入" if obv_trend == "UP" else "💀流出"

def fetch_commander_data(symbol):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol}
    
    # 强制 Binance + 强限频保护
    main_ex = ccxt.binance({
        'enableRateLimit': True,
        'rateLimit': 1000,          # 每请求间隔1秒
        'timeout': 15000,
        'options': {'defaultType': 'spot'},
    })
    
    try:
        tk = main_ex.fetch_ticker(pair)
        curr_p = tk['last']
        res["最新价"] = f"{curr_p:,.2f}"
        res["24h"] = tk['percentage']

        # 短期涨幅
        timeframes = {"1m": '1m', "5m": '5m', "15m": '15m', "1h": '1h'}
        for label, tf in timeframes.items():
            k = main_ex.fetch_ohlcv(pair, tf, limit=2)
            if len(k) >= 2:
                base_p = k[-2][4]
                res[label] = ((curr_p - base_p) / base_p) * 100
            else:
                res[label] = 0.0

        # 交易量来源 + 净流入（只 Binance）
        total_flow = 0.0
        volume_sources = []
        
        tk_ex = main_ex.fetch_ticker(pair)
        qvol = tk_ex.get('quoteVolume', 0) or 0
        bvol = tk_ex.get('baseVolume', 0) or 0
        est_qvol = qvol if qvol > 0 else (bvol * curr_p if bvol > 0 and curr_p > 0 else 0)
        
        # 日志打印（本地控制台 / Cloud logs 查看）
        print(f"BTC @ BINANCE: quoteVol={qvol}, baseVol={bvol}, est_qvol={est_qvol:.2f}, price={curr_p}")
        
        if est_qvol > 0:
            volume_sources.append("Binance")
        
        trades = main_ex.fetch_trades(pair, limit=50)
        total_flow += sum((t['price'] * t['amount']) if t['side'] == 'buy' else -(t['price'] * t['amount']) for t in trades)
        
        res["净流入(万)"] = round(total_flow / 10000, 1)
        res["交易量来源"] = ", ".join(volume_sources) if volume_sources else "-"

        # 指标
        ohlcv_raw = main_ex.fetch_ohlcv(pair, '1h', limit=40)
        df = pd.DataFrame(ohlcv_raw, columns=['t','o','h','l','c','v'])
        rsi_val = ta.rsi(df['c'], length=14).iloc[-1] if len(df) >= 14 else 50
        res["RSI"] = round(rsi_val, 1)
        
        diag, atr_p, obv_s = get_tactical_logic(df, curr_p, res["净流入(万)"], rsi_val, symbol, res.get("1m", 0))
        res["战术诊断"] = diag
        res["ATR%"] = atr_p
        res["OBV"] = obv_s
        
        res["TVL (百万$)"] = "-"
        
    except ccxt.RateLimitExceeded as e:
        res["最新价"] = "限频"
        res["战术诊断"] = "Rate Limit"
        res["交易量来源"] = str(e)[:30]
        print(f"Rate limit hit: {e}")
    except Exception as e:
        res["最新价"] = "Err"
        res["战术诊断"] = "异常"
        res["交易量来源"] = str(e)[:30]
        print(f"Error: {e}")
    
    return res

# 界面
st.title("🛰️ BTC Binance 专用完整版 (限频优化 + 日志)")
placeholder = st.empty()

while True:
    with ThreadPoolExecutor(max_workers=1) as executor:
        results = list(executor.map(fetch_commander_data, SYMBOLS))
    
    df = pd.DataFrame([r for r in results if r])
    if not df.empty:
        df = df.sort_values(by="1m", ascending=False)

    display_df = df.copy()
    order = ["币种", "最新价", "战术诊断", "1m", "5m", "15m", "1h", "24h", "净流入(万)", "RSI", "ATR%", "OBV", "TVL (百万$)", "交易量来源"]
    
    for col in ["1m", "5m", "15m", "1h", "24h"]:
        display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%" if isinstance(x, (int, float)) else x)

    with placeholder.container():
        st.write(f"📊 只监控 BTC | 来源: 纯 Binance | 频率: 180s | 时间: {time.strftime('%H:%M:%S')} | **查看日志确认 quoteVolume**")
        
        def style_logic(val):
            if "底部吸筹" in val: return 'background-color: #006400; color: white'
            if "确认破位" in val: return 'background-color: #8B0000; color: white'
            if "轻微偏强" in val: return 'background-color: #228B22; color: white'
            if "短线急跌" in val: return 'background-color: #B22222; color: white'
            if val == "💎流入": return 'color: #00ff00'
            return ''

        st.dataframe(
            display_df[order].style.applymap(style_logic, subset=["战术诊断", "OBV"]),
            use_container_width=True, height=400
        )

    time.sleep(180)
