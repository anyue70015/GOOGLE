import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
from concurrent.futures import ThreadPoolExecutor

# --- 基础配置 ---
st.set_page_config(page_title="指挥部 - 智能端口适配版", layout="wide")

# 常见的代理端口列表
COMMON_PROXY_PORTS = [7890, 10808, 10809, 1081, 1080, 7897, 7891]

# 在 st.session_state 中存储已经探测成功的端口
if 'working_proxy' not in st.session_state:
    st.session_state.working_proxy = None

def find_working_proxy():
    """遍历端口，寻找能连通币安的代理"""
    st.toast("正在探测本地可用代理端口...")
    for port in COMMON_PROXY_PORTS:
        proxy_url = f"http://127.0.0.1:{port}"
        try:
            # 使用简单的 requests 测试连通性，超时设短一点
            import requests
            # 访问币安的测试接口
            test_url = "https://api.binance.com/api/v3/ping"
            resp = requests.get(test_url, proxies={"http": proxy_url, "https": proxy_url}, timeout=2)
            if resp.status_code == 200:
                st.success(f"检测到可用代理端口: {port}")
                return proxy_url
        except:
            continue
    return None

def get_tactical_logic(df, curr_p, flow, rsi, change_1m):
    """战术诊断逻辑"""
    try:
        if df is None or len(df) < 14: return "计算中", 0.0, "-"
        atr_series = ta.atr(df['h'], df['l'], df['c'], length=14)
        atr_val = atr_series.iloc[-1] if atr_series is not None else 0
        atr_pct = (atr_val / curr_p) * 100 if curr_p != 0 else 0
        obv_series = ta.obv(df['c'], df['v'])
        obv_trend = "UP" if len(obv_series) > 1 and obv_series.iloc[-1] > obv_series.iloc[-2] else "DOWN"
        diag = "🔎 观望"
        if rsi < 35 and obv_trend == "UP": diag = "🛒 底部吸筹"
        elif rsi > 70 and obv_trend == "DOWN": diag = "⚠️ 诱多虚涨"
        elif change_1m > 1.0: diag = "🚀 轻微偏强"
        elif change_1m < -1.0: diag = "🩸 短线急跌"
        return diag, round(atr_pct, 2), "💎流入" if obv_trend == "UP" else "💀流出"
    except:
        return "异常", 0.0, "-"

def fetch_commander_data(symbol):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol, "最新价": "连接中..."}
    
    # 获取当前已找到的代理
    proxy_url = st.session_state.get('working_proxy')
    
    main_ex = ccxt.binance({
        'enableRateLimit': True,
        'timeout': 15000,
        'proxies': {'http': proxy_url, 'https': proxy_url} if proxy_url else {}
    })
    
    try:
        tk = main_ex.fetch_ticker(pair)
        curr_p = tk['last']
        res["最新价"] = f"{curr_p:,.2f}"
        res["24h"] = tk.get('percentage', 0)

        # 1m 涨跌
        kline = main_ex.fetch_ohlcv(pair, '1m', limit=2)
        res["1m"] = ((curr_p - kline[-2][4]) / kline[-2][4]) * 100 if len(kline) >= 2 else 0.0

        # 流入和指标
        trades = main_ex.fetch_trades(pair, limit=30)
        flow = sum((t['price'] * t['amount']) if t['side'] == 'buy' else -(t['price'] * t['amount']) for t in trades)
        res["净流入(万)"] = round(flow / 10000, 1)

        ohlcv_h1 = main_ex.fetch_ohlcv(pair, '1h', limit=30)
        df = pd.DataFrame(ohlcv_h1, columns=['t','o','h','l','c','v'])
        rsi_val = ta.rsi(df['c'], length=14).iloc[-1] if len(df) >= 14 else 50
        res["RSI"] = round(rsi_val, 1)
        
        diag, atr_p, obv_s = get_tactical_logic(df, curr_p, res["净流入(万)"], rsi_val, res["1m"])
        res["战术诊断"], res["ATR%"], res["OBV"] = diag, atr_p, obv_s

    except Exception:
        res["最新价"] = "❌ 连不上"
        res["战术诊断"] = "代理失效"
    
    return res

# --- 页面 UI ---
st.title("🛰️ 自动适配代理指挥部 (Multi-Port Support)")

# 自动探测逻辑
if st.session_state.working_proxy is None:
    st.session_state.working_proxy = find_working_proxy()

placeholder = st.empty()

while True:
    # 每一轮开始前检查，如果没代理，重试探测
    if st.session_state.working_proxy is None:
        st.session_state.working_proxy = find_working_proxy()

    with ThreadPoolExecutor(max_workers=1) as executor:
        results = list(executor.map(fetch_commander_data, ["BTC"]))
    
    df_raw = pd.DataFrame(results)
    
    if not df_raw.empty:
        # 清理列索引，确保无 KeyError
        target_order = ["币种", "最新价", "战术诊断", "1m", "24h", "净流入(万)", "RSI", "ATR%", "OBV"]
        safe_cols = [c for c in target_order if c in df_raw.columns]
        display_df = df_raw[safe_cols].copy()

        # 格式化数据
        if "1m" in display_df.columns:
            display_df["1m"] = display_df["1m"].map(lambda x: f"{x:+.2f}%" if isinstance(x, (int, float)) else x)

        with placeholder.container():
            st.caption(f"当前通信通道: `{st.session_state.working_proxy or '直接连接 (不推荐)'}`")
            
            def style_picker(val):
                if not isinstance(val, str): return ''
                if any(k in val for k in ["底部", "偏强", "流入"]): return 'color: #00ff00; font-weight: bold'
                if any(k in val for k in ["破位", "急跌", "流出"]): return 'color: #ff4b4b; font-weight: bold'
                return ''

            try:
                # 动态确定样式子集，彻底防御 KeyError
                subset_cols = [c for c in ["战术诊断", "OBV"] if c in display_df.columns]
                if subset_cols:
                    st.dataframe(display_df.style.map(style_picker, subset=subset_cols), use_container_width=True)
                else:
                    st.dataframe(display_df, use_container_width=True)
            except:
                st.dataframe(display_df, use_container_width=True)
    
    time.sleep(15)
