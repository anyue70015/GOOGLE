import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
import requests
from concurrent.futures import ThreadPoolExecutor

# --- 配置区 ---
st.set_page_config(page_title="指挥部 - BTC Binance 完整修复版", layout="wide")

# 1. 如果你本地有代理软件，请在此修改端口（常见 7890, 1080, 1081）
LOCAL_PROXY_URL = "http://127.0.0.1:7890" 

SYMBOLS = ["BTC"]

def get_tactical_logic(df, curr_p, flow, rsi, symbol, change_1m):
    """战术诊断逻辑"""
    try:
        atr_series = ta.atr(df['h'], df['l'], df['c'], length=14)
        atr_val = atr_series.iloc[-1] if atr_series is not None and not atr_series.empty else 0
        atr_pct = (atr_val / curr_p) * 100 if curr_p != 0 else 0
        
        obv_series = ta.obv(df['c'], df['v'])
        if len(obv_series) < 2:
            obv_trend = "UNKNOWN"
        else:
            obv_trend = "UP" if obv_series.iloc[-1] > obv_series.iloc[-2] else "DOWN"
        
        macd = ta.macd(df['c'])
        macd_status = "金叉" if macd['MACDh_12_26_9'].iloc[-1] > 0 else "死叉"
        
        diag = "🔎 观望"
        atr_threshold = 3.0
        
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
    except:
        return "计算中", 0.0, "-"

def fetch_commander_data(symbol):
    """获取币安数据核心函数"""
    pair = f"{symbol}/USDT"
    res = {"币种": symbol}
    
    # 2. 初始化 CCXT，集成代理配置
    main_ex = ccxt.binance({
        'enableRateLimit': True,
        'rateLimit': 1200,
        'timeout': 20000,
        'options': {'defaultType': 'spot'},
        # 让 Python 借用浏览器的代理通道
        'proxies': {
            'http': LOCAL_PROXY_URL,
            'https': LOCAL_PROXY_URL,
        },
    })
    
    try:
        # 获取基础价格信息
        tk = main_ex.fetch_ticker(pair)
        curr_p = tk['last']
        res["最新价"] = f"{curr_p:,.2f}"
        res["24h"] = tk.get('percentage', 0)

        # 多周期涨跌幅计算
        timeframes = {"1m": '1m', "5m": '5m', "15m": '15m', "1h": '1h'}
        for label, tf in timeframes.items():
            k = main_ex.fetch_ohlcv(pair, tf, limit=2)
            if len(k) >= 2:
                base_p = k[-2][4]
                res[label] = ((curr_p - base_p) / base_p) * 100
            else:
                res[label] = 0.0

        # 净流入模拟计算 (基于最近成交)
        trades = main_ex.fetch_trades(pair, limit=50)
        total_flow = sum((t['price'] * t['amount']) if t['side'] == 'buy' else -(t['price'] * t['amount']) for t in trades)
        res["净流入(万)"] = round(total_flow / 10000, 1)

        # 指标计算
        ohlcv_raw = main_ex.fetch_ohlcv(pair, '1h', limit=40)
        df_ohlcv = pd.DataFrame(ohlcv_raw, columns=['t','o','h','l','c','v'])
        rsi_val = ta.rsi(df_ohlcv['c'], length=14).iloc[-1] if len(df_ohlcv) >= 14 else 50
        res["RSI"] = round(rsi_val, 1)
        
        diag, atr_p, obv_s = get_tactical_logic(df_ohlcv, curr_p, res["净流入(万)"], rsi_val, symbol, res.get("1m", 0))
        res["战术诊断"] = diag
        res["ATR%"] = atr_p
        res["OBV"] = obv_s
        res["TVL (百万$)"] = "-"
        res["交易量来源"] = "Binance"

    except Exception as e:
        res["最新价"] = "连接失败"
        res["战术诊断"] = f"错误: 检查代理端口"
        print(f"Fetch Error for {symbol}: {e}")
    
    return res

# --- UI 渲染区 ---
st.title("🛰️ BTC Binance 完整修复版 (2026)")

# 使用状态容器避免刷新闪烁
placeholder = st.empty()

while True:
    with ThreadPoolExecutor(max_workers=1) as executor:
        results = list(executor.map(fetch_commander_data, SYMBOLS))
    
    df = pd.DataFrame([r for r in results if "币种" in r])
    
    if not df.empty:
        # 复制一份用于显示的 DF
        display_df = df.copy()
        
        # 定义显示顺序
        order = ["币种", "最新价", "战术诊断", "1m", "5m", "15m", "1h", "24h", "净流入(万)", "RSI", "ATR%", "OBV"]
        available_order = [col for col in order if col in display_df.columns]
        
        # 格式化百分比列
        for col in ["1m", "5m", "15m", "1h", "24h"]:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(lambda x: f"{x:+.2f}%" if isinstance(x, (int, float)) else x)

        with placeholder.container():
            st.write(f"📊 实时监控中 | 代理地址: `{LOCAL_PROXY_URL}` | 刷新时间: {time.strftime('%H:%M:%S')}")
            
            # --- 样式逻辑 ---
            def style_logic(val):
                if not isinstance(val, str): return ''
                if "底部吸筹" in val or "轻微偏强" in val or "💎流入" in val: return 'color: #00ff00; font-weight: bold'
                if "确认破位" in val or "短线急跌" in val or "💀流出" in val: return 'color: #ff4b4b; font-weight: bold'
                return ''

            # --- 关键修复点：动态计算 subset ---
            target_cols = ["战术诊断", "OBV"]
            # 只有当列确实存在于当前的切片中，才应用样式，防止 KeyError
            actual_subset = [c for c in target_cols if c in display_df[available_order].columns]

            if actual_subset:
                styled_df = display_df[available_order].style.map(style_logic, subset=actual_subset)
            else:
                styled_df = display_df[available_order]

            st.dataframe(styled_df, use_container_width=True, height=200)
    else:
        st.warning("正在尝试连接币安 API，请确保你的代理软件已开启并允许局域网连接...")

    time.sleep(10) # 测试建议设短一点，正常运行可调回 180
