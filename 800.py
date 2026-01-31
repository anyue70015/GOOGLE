import streamlit as st
import pandas as pd
import ccxt
import time
import pandas_ta as ta
from concurrent.futures import ThreadPoolExecutor

# --- 全局配置 ---
st.set_page_config(page_title="指挥部 - 自动防灾增强版", layout="wide")

# 探测端口池
COMMON_PORTS = [10810, 10811, 7890, 10809, 10808, 1081, 1080, 7891, 7897]

if 'proxy_url' not in st.session_state:
    st.session_state.proxy_url = None

def probe_proxy():
    """自动化寻找可用的浏览器代理通道"""
    import requests
    test_url = "https://api3.binance.com/api/v3/ping"
    for port in COMMON_PORTS:
        url = f"http://127.0.0.1:{port}"
        try:
            # 增加 2 秒极速探测
            r = requests.get(test_url, proxies={"http": url, "https": url}, timeout=2)
            if r.status_code == 200:
                return url
        except:
            continue
    return None

def fetch_with_retry(func, *args, **kwargs):
    """针对 unexpected EOF 的自动重试器"""
    for i in range(3): # 最多尝试 3 次
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if i == 2: raise e
            time.sleep(1) # 等待 1 秒后重试
    return None

def get_tactical_logic(df, curr_p, flow, rsi, c1m):
    """战术诊断逻辑"""
    try:
        if df is None or len(df) < 14: return "分析中", 0.0, "-"
        obv = ta.obv(df['c'], df['v'])
        obv_t = "UP" if obv.iloc[-1] > obv.iloc[-2] else "DOWN"
        
        diag = "🔎 观望"
        if rsi < 30 and obv_t == "UP": diag = "🛒 底部吸筹"
        elif rsi > 70 and obv_t == "DOWN": diag = "⚠️ 诱多虚涨"
        elif c1m > 1.2: diag = "🚀 轻微偏强"
        elif c1m < -1.2: diag = "🩸 短线急跌"
        
        return diag, "💎流入" if obv_t == "UP" else "💀流出"
    except:
        return "数据不足", "-"

def fetch_data(symbol):
    pair = f"{symbol}/USDT"
    res = {"币种": symbol, "最新价": "加载中"}
    
    # 使用探测到的代理
    proxy = st.session_state.proxy_url
    ex = ccxt.binance({
        'enableRateLimit': True,
        'timeout': 20000,
        'hostname': 'api3.binance.com', # 避开主域名劫持
        'proxies': {'http': proxy, 'https': proxy} if proxy else {}
    })
    
    try:
        # 使用重试机制获取核心数据
        tk = fetch_with_retry(ex.fetch_ticker, pair)
        curr_p = tk['last']
        res["最新价"] = f"{curr_p:,.2f}"
        res["24h"] = tk.get('percentage', 0)

        # 获取 K 线 (用于诊断)
        ohlcv = fetch_with_retry(ex.fetch_ohlcv, pair, '1h', limit=30)
        df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
        
        # 计算 1m 涨跌 (复用 tk 数据减少请求)
        k1m = fetch_with_retry(ex.fetch_ohlcv, pair, '1m', limit=2)
        c1m = ((curr_p - k1m[-2][4]) / k1m[-2][4]) * 100 if len(k1m) >= 2 else 0
        res["1m"] = c1m

        # RSI 计算
        rsi_val = ta.rsi(df['c'], length=14).iloc[-1] if len(df) >= 14 else 50
        res["RSI"] = round(rsi_val, 1)

        # 诊断
        diag, obv_s = get_tactical_logic(df, curr_p, 0, rsi_val, c1m)
        res["战术诊断"], res["OBV"] = diag, obv_s

    except Exception as e:
        res["最新价"] = "❌ 连接中断"
        res["战术诊断"] = "节点不稳定"
        
    return res

# --- UI 渲染 ---
st.title("🛰️ 自动巡航指挥部 (防断连版)")

# 初始探测
if not st.session_state.proxy_url:
    with st.spinner("正在搜索本地代理通道..."):
        st.session_state.proxy_url = probe_proxy()

placeholder = st.empty()

while True:
    # 如果代理失效，尝试重新握手
    if not st.session_state.proxy_url:
        st.session_state.proxy_url = probe_proxy()

    with ThreadPoolExecutor(max_workers=1) as executor:
        results = list(executor.map(fetch_data, ["BTC"]))
    
    df_raw = pd.DataFrame(results)
    
    if not df_raw.empty:
        # 安全列过滤
        target_cols = ["币种", "最新价", "战术诊断", "1m", "24h", "RSI", "OBV"]
        active_cols = [c for c in target_cols if c in df_raw.columns]
        display_df = df_raw[active_cols].copy()

        if "1m" in display_df.columns:
            display_df["1m"] = display_df["1m"].map(lambda x: f"{x:+.2f}%" if isinstance(x, float) else x)

        with placeholder.container():
            st.caption(f"当前代理: `{st.session_state.proxy_url or '直连'}` | 如报错请切换全局模式")
            
            def style_func(val):
                if not isinstance(val, str): return ''
                if any(k in val for k in ["底部", "偏强", "流入"]): return 'color: #00ff00; font-weight: bold'
                if any(k in val for k in ["破位", "急跌", "流出"]): return 'color: #ff4b4b; font-weight: bold'
                return ''

            try:
                # 最后的 KeyError 屏障
                sub = [c for c in ["战术诊断", "OBV"] if c in display_df.columns]
                st.dataframe(display_df.style.map(style_func, subset=sub) if sub else display_df, use_container_width=True)
            except:
                st.dataframe(display_df, use_container_width=True)
    
    time.sleep(15)
