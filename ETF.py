import streamlit as st
import ccxt.async_support as ccxt_async
import pandas as pd
import numpy as np
import asyncio
import time

# --- 页面配置 ---
st.set_page_config(page_title="2026量化神兵-直连版", layout="wide")

st.title("🚀 加密货币聚合扫描器 (直连节点版)")
st.markdown("如果币安超时，请在侧边栏切换不同的‘直连节点’试试。")

# --- 侧边栏：直连节点切换 ---
st.sidebar.title("🌐 节点设置")
# 备选节点：api3、api1 或者是专门的 vision 节点
binance_node = st.sidebar.selectbox("币安亚太直连节点", 
    ["api3.binance.com", "api1.binance.com", "api.binance.vision", "api.bmwweb.academy"], 
    index=0)

# --- 币种列表处理 ---
uploaded = st.file_uploader("上传币种列表 (.txt)", type="txt")
if uploaded:
    content = uploaded.read().decode("utf-8")
    symbols = [line.strip().upper() for line in content.splitlines() if line.strip()]
    symbols = list(dict.fromkeys(symbols))
    symbols = [s if '/' in s else f"{s}/USDT" for s in symbols]
    st.success(f"已加载 {len(symbols)} 个交易对")
else:
    st.stop()

# --- 主参数 ---
timeframe = st.selectbox("周期", ["1m", "5m", "15m", "1h"], index=1)
refresh_sec = st.slider("刷新(秒)", 5, 60, 20)
vol_multiplier = st.slider("放量阈值", 1.0, 5.0, 2.5)

# --- 交易所实例化 (纯直连，不加 proxy) ---
exchanges = {}
ex_list = ['binance', 'okx', 'gate', 'bitget', 'huobi', 'bybit']

for name in ex_list:
    cfg = {
        'enableRateLimit': True,
        'options': {'defaultType': 'spot', 'adjustForTimeDifference': True},
        'timeout': 20000, # 增加到 20 秒，给网络留足宽限
    }
    if name == 'binance':
        cfg['urls'] = {'api': {'public': f'https://{binance_node}'}}
    
    ex_class = getattr(ccxt_async, name if name != 'huobi' else 'htx')
    exchanges[name] = ex_class(cfg)

# --- 数据抓取 ---
async def fetch_ohlcv(ex, symbol, timeframe, limit):
    try:
        data = await asyncio.wait_for(ex.fetch_ohlcv(symbol, timeframe, limit=limit), timeout=15.0)
        return data, None
    except Exception as e:
        return None, str(e)

async def process_symbol(symbol, timeframe):
    N = {"1m": 40, "5m": 20, "15m": 12, "1h": 8}[timeframe]
    tasks = [fetch_ohlcv(ex, symbol, timeframe, N + 5) for ex in exchanges.values()]
    results = await asyncio.gather(*tasks)
    
    agg_df = None
    success, fails = [], []
    for (name, ex), (ohlcv, err) in zip(exchanges.items(), results):
        if ohlcv and len(ohlcv) > 2:
            df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
            success.append(name)
            if agg_df is None: agg_df = df.copy()
            else: agg_df['v'] += df['v']
        else:
            fails.append(name)
    return agg_df, success, fails

placeholder = st.empty()

async def main():
    while True:
        data_rows = []
        for symbol in symbols:
            df, success, fails = await process_symbol(symbol, timeframe)
            status = f"✅{len(success)} ❌{len(fails)}"
            if 'binance' in fails: status += " (超时)"
            
            if df is None or len(df) < 5:
                data_rows.append([symbol, "-", "-", "-", "-", "", "", status])
                continue
                
            df[['c','o','v']] = df[['c','o','v']].apply(pd.to_numeric)
            curr_c, prev_c = df['c'].iloc[-1], df['c'].iloc[-2]
            curr_v, avg_v = df['v'].iloc[-1], df['v'].iloc[:-1].tail(15).mean()
            vol_ratio = curr_v / avg_v if avg_v > 0 else 0
            change = (curr_c - prev_c) / prev_c * 100

            sig1 = (curr_c > df['o'].iloc[-1]) and (vol_ratio > vol_multiplier)
            sig2 = (vol_ratio > 1.2) and (change > 0.5)
            
            sig_list = [str(i) for i, s in enumerate([sig1, sig2], 1) if s]
            data_rows.append([
                symbol, f"{curr_c}", f"{change:+.2f}%", f"{curr_v:,.0f}", 
                f"{vol_ratio:.2f}x", ",".join(sig_list), "⚠️" if sig_list else "", status
            ])

        df_final = pd.DataFrame(data_rows, columns=["交易对","现价","涨幅","成交量","放量比","方法","信号","状态"])
        df_final['v_val'] = pd.to_numeric(df_final['放量比'].str.replace('x',''), errors='coerce').fillna(0)
        df_final = df_final.sort_values('sort_v' if 'sort_v' in df_final else 'v_val', ascending=False)

        # 清爽的透明红色样式
        def style_rows(row):
            if row["信号"] == "⚠️":
                # 0.1 透明度，确保能看清数字
                return ['background-color: rgba(255, 75, 75, 0.1); color: #FF4B4B; font-weight: bold;'] * len(row)
            return [''] * len(row)

        with placeholder.container():
            st.write(f"⏱️ 更新: {time.strftime('%H:%M:%S')} | 当前节点: {binance_node}")
            st.dataframe(df_final.style.apply(style_rows, axis=1), use_container_width=True, height=800)
        
        await asyncio.sleep(refresh_sec)

if __name__ == "__main__":
    asyncio.run(main())
