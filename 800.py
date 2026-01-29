import streamlit as st
import ccxt.async_support as ccxt_async
import pandas as pd
import numpy as np
import asyncio
import time
import nest_asyncio
import requests

# 允许 Streamlit 嵌套 asyncio
nest_asyncio.apply()

# --- 页面配置 ---
st.set_page_config(page_title="2026量化神兵-自动节点优化版", layout="wide")

st.title("🚀 加密货币聚合扫描器 (自动节点 + 优先Binance)")
st.markdown("点击侧边栏'自动测试'选最快节点。优先Binance数据，超时自动fallback。")

# --- 侧边栏：节点设置 + 自动测试 ---
st.sidebar.title("🌐 节点优化")

# 节点列表（官方2026最新）
all_nodes = [
    "api.binance.com",
    "api-gcp.binance.com",
    "api1.binance.com",
    "api2.binance.com",
    "api3.binance.com",
    "api4.binance.com"
]

# 自动测试按钮
if st.sidebar.button("⚡ 自动测试最快节点 (10-20秒)"):
    results = {}
    best_node = None
    best_time = float('inf')
    
    with st.spinner("正在ping所有节点..."):
        for node in all_nodes:
            url = f"https://{node}/api/v3/ping"
            start = time.time()
            try:
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    elapsed = (time.time() - start) * 1000  # ms
                    results[node] = round(elapsed, 0)
                    if elapsed < best_time:
                        best_time = elapsed
                        best_node = node
                else:
                    results[node] = f"失败 ({resp.status_code})"
            except Exception as e:
                results[node] = f"超时/错误"
    
    # 显示结果
    st.sidebar.write("测试结果（延迟 ms，越小越好）：")
    for n, t in results.items():
        if isinstance(t, (int, float)):
            st.sidebar.write(f"**{n}**: {t} ms")
        else:
            st.sidebar.write(f"{n}: {t}")
    
    if best_node:
        st.session_state['selected_node'] = best_node
        st.sidebar.success(f"最快节点：**{best_node}** ({best_time} ms) 已自动切换！")
    else:
        st.sidebar.error("所有节点失败，请检查网络/VPN")

# 节点选择（优先用自动选的）
if 'selected_node' in st.session_state:
    default_node = st.session_state['selected_node']
    st.sidebar.info(f"当前使用自动选节点：{default_node}")
else:
    default_node = "api.binance.com"  # 默认最稳

binance_node = st.sidebar.selectbox("手动选节点（或用上面的自动）", 
    all_nodes, index=all_nodes.index(default_node) if default_node in all_nodes else 0)

# --- 币种列表 ---
uploaded = st.file_uploader("上传币种列表 (.txt)", type="txt")
if uploaded:
    content = uploaded.read().decode("utf-8")
    symbols = [line.strip().upper() for line in content.splitlines() if line.strip()]
    symbols = list(dict.fromkeys(symbols))
    symbols = [s if '/' in s else f"{s}/USDT" for s in symbols]
    st.success(f"已加载 {len(symbols)} 个交易对")
else:
    st.stop()

# --- 参数 ---
timeframe = st.selectbox("周期", ["1m", "5m", "15m", "1h"], index=1)
refresh_sec = st.slider("刷新(秒)", 10, 120, 45)  # 建议高点防超时
vol_multiplier = st.slider("放量阈值 x", 1.0, 5.0, 2.5)

# --- 交易所 ---
exchanges = {}
ex_list = ['binance', 'bybit', 'okx', 'gate', 'bitget']  # 优先 bybit fallback

for name in ex_list:
    cfg = {
        'enableRateLimit': True,
        'options': {'defaultType': 'spot', 'adjustForTimeDifference': True},
        'timeout': 60000,  # 60s 宽限，防 -1007
    }
    if name == 'binance':
        cfg['urls'] = {'api': {'public': f'https://{binance_node}'}}
    ex_class = getattr(ccxt_async, name)
    exchanges[name] = ex_class(cfg)

binance_ex = exchanges['binance']

# --- fetch with retry ---
async def fetch_ohlcv(ex, symbol, timeframe, limit, retries=3):
    backoff = 1
    for attempt in range(retries):
        try:
            data = await asyncio.wait_for(ex.fetch_ohlcv(symbol, timeframe, limit=limit), timeout=45.0)
            return data, None
        except Exception as e:
            if attempt == retries - 1:
                return None, str(e)
            await asyncio.sleep(backoff)
            backoff *= 2

# --- process ---
async def process_symbol(symbol, timeframe):
    N = {"1m": 40, "5m": 20, "15m": 12, "1h": 8}[timeframe]
    limit = N + 10

    binance_ohlcv, binance_err = await fetch_ohlcv(binance_ex, symbol, timeframe, limit, retries=3)
    
    if binance_ohlcv and len(binance_ohlcv) >= N:
        df = pd.DataFrame(binance_ohlcv, columns=['t','o','h','l','c','v'])
        source = "Binance"
        success = ["binance"]
        fails = []
    else:
        fallback_names = ['bybit', 'okx', 'gate', 'bitget']
        df = None
        source = "无数据"
        success = []
        fails = ["binance"]
        for name in fallback_names:
            if df is not None: break
            ex = exchanges.get(name)
            if not ex: continue
            ohlcv, err = await fetch_ohlcv(ex, symbol, timeframe, limit, retries=2)
            if ohlcv and len(ohlcv) >= N:
                df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
                source = name.capitalize()
                success = [name]
                fails += [n for n in fallback_names if n != name]
                break
            else:
                fails.append(name)

    if df is None:
        return None, success, fails, source
    
    return df, success, fails, source

placeholder = st.empty()

async def main_loop():
    while True:
        data_rows = []
        for symbol in symbols:
            df, success, fails, source = await process_symbol(symbol, timeframe)
            status = f"源:{source} | ✅{len(success)} ❌{len(fails)}"
            if 'binance' in fails:
                status += " (Binance超时)"
            
            if df is None or len(df) < 5:
                data_rows.append([symbol, "-", "-", "-", "-", "", "", status])
                continue
                
            df[['c','o','v']] = df[['c','o','v']].apply(pd.to_numeric, errors='coerce')
            curr_c = df['c'].iloc[-1]
            prev_c = df['c'].iloc[-2] if len(df) > 1 else curr_c
            curr_v = df['v'].iloc[-1]
            avg_v_slice = df['v'].iloc[-21:-1]
            avg_v = avg_v_slice.mean() if not avg_v_slice.empty else 1.0
            vol_ratio = curr_v / avg_v if avg_v > 0 else 0
            change = (curr_c - prev_c) / prev_c * 100 if prev_c != 0 else 0

            sig1 = (curr_c > df['o'].iloc[-1]) and (vol_ratio > vol_multiplier)
            sig2 = (vol_ratio > 1.2) and (change > 0.5)
            
            sig_list = [str(i) for i, s in enumerate([sig1, sig2], 1) if s]
            signal_str = ",".join(sig_list)
            alert = "⚠️" if sig_list else ""
            
            data_rows.append([
                symbol, f"{curr_c:.4f}", f"{change:+.2f}%", f"{curr_v:,.0f}", 
                f"{vol_ratio:.2f}x", signal_str, alert, status
            ])

        if data_rows:
            df_final = pd.DataFrame(data_rows, columns=["交易对","现价","涨幅(1根)","成交量","放量比","信号","警报","状态"])
            df_final['放量比_num'] = pd.to_numeric(df_final['放量比'].str.replace('x', ''), errors='coerce').fillna(0)
            df_final = df_final.sort_values('放量比_num', ascending=False).drop(columns=['放量比_num'])

            def style_rows(row):
                if row["警报"] == "⚠️":
                    return ['background-color: rgba(255, 75, 75, 0.12); color: #FF4B4B; font-weight: bold;'] * len(row)
                return [''] * len(row)

            with placeholder.container():
                st.write(f"⏱️ 更新: {time.strftime('%Y-%m-%d %H:%M:%S EST')} | 节点: {binance_node} | 间隔: {refresh_sec}s")
                st.dataframe(df_final.style.apply(style_rows, axis=1), use_container_width=True, height=800)
        
        await asyncio.sleep(refresh_sec)

# 运行
if __name__ == "__main__":
    asyncio.run(main_loop())
