import streamlit as st
import ccxt.async_support as ccxt_async
import pandas as pd
import numpy as np
import asyncio
import time

# --- 页面视觉优化：清爽背景 ---
st.set_page_config(page_title="2026量化神兵-直连版", layout="wide")
st.title("加密货币聚合扫描器 (系统直连/视觉增强版)")

# --- 币种列表处理 ---
uploaded = st.file_uploader("上传币种列表 (.txt)", type="txt")
if uploaded:
    content = uploaded.read().decode("utf-8")
    symbols = [line.strip().upper() for line in content.splitlines() if line.strip()]
    symbols = list(dict.fromkeys(symbols))
    symbols = [s if '/' in s else f"{s}/USDT" for s in symbols]
    st.success(f"已加载 {len(symbols)} 个交易对")
else:
    st.info("💡 浏览器能开 API 镜像，本程序就能连通")
    st.stop()

# --- 参数设置 ---
col1, col2, col3, col4 = st.columns(4)
with col1:
    timeframe = st.selectbox("周期", ["1m", "5m", "15m", "1h"], index=1)
with col2:
    refresh_sec = st.slider("刷新(秒)", 5, 60, 20)
with col3:
    vol_multiplier = st.slider("放量阈值", 1.0, 5.0, 2.5)
with col4:
    # 增加一个备选镜像切换
    api_mirror = st.selectbox("币安镜像节点", ["api1", "api2", "api3"], index=2)

# --- 交易所配置 (直连模式：不指定 proxies 参数) ---
exchanges = {}
ex_list = ['binance', 'okx', 'gate', 'bitget', 'huobi', 'bybit']

for name in ex_list:
    cfg = {
        'enableRateLimit': True,
        'options': {'defaultType': 'spot', 'adjustForTimeDifference': True},
        'timeout': 15000,
        # 注意：这里删除了 proxies 字段，让系统环境自行接管
    }
    
    if name == 'binance':
        # 动态切换镜像地址
        cfg['urls'] = {'api': {'public': f'https://{api_mirror}.binance.com'}}
    
    ex_class = getattr(ccxt_async, name if name != 'huobi' else 'htx')
    exchanges[name] = ex_class(cfg)

# --- 核心数据抓取 ---
async def fetch_ohlcv(ex, symbol, timeframe, limit):
    try:
        # 增加超时容错
        data = await asyncio.wait_for(ex.fetch_ohlcv(symbol, timeframe, limit=limit), timeout=10.0)
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

# --- 渲染逻辑 ---
placeholder = st.empty()

async def main():
    while True:
        data_rows = []
        for symbol in symbols:
            df, success, fails = await process_symbol(symbol, timeframe)
            status = f"✅{len(success)} ❌{len(fails)}"
            if 'binance' in fails:
                status += " (Binance仍受限)"
            
            if df is None or len(df) < 5:
                data_rows.append([symbol, "-", "-", "-", "-", "", "", status])
                continue
                
            df[['c','o','v']] = df[['c','o','v']].apply(pd.to_numeric)
            curr_c, prev_c = df['c'].iloc[-1], df['c'].iloc[-2]
            curr_v, avg_v = df['v'].iloc[-1], df['v'].iloc[:-1].tail(15).mean()
            vol_ratio = curr_v / avg_v if avg_v > 0 else 0
            change = (curr_c - prev_c) / prev_c * 100

            # 信号算法
            sig1 = (curr_c > df['o'].iloc[-1]) and (vol_ratio > vol_multiplier)
            sig2 = (vol_ratio > 1.2) and (change > 0.5)
            
            sig_list = [str(i) for i, s in enumerate([sig1, sig2], 1) if s]
            data_rows.append([
                symbol, f"{curr_c}", f"{change:+.2f}%", f"{curr_v:,.0f}", 
                f"{vol_ratio:.2f}x", ",".join(sig_list), "⚠️" if sig_list else "", status
            ])

        # 排序与样式
        df_final = pd.DataFrame(data_rows, columns=["交易对","现价","涨幅","成交量","放量比","方法","信号","状态"])
        df_final['sort_v'] = pd.to_numeric(df_final['放量比'].str.replace('x',''), errors='coerce').fillna(0)
        df_final = df_final.sort_values('sort_v', ascending=False).drop(columns=['sort_v'])

        # --- 清爽视觉样式 ---
        def style_rows(row):
            if row["信号"] == "⚠️":
                # 背景用极浅红色，边框加亮，文字用亮红色加粗
                return ['background-color: rgba(255, 75, 75, 0.1); border: 1px solid #FF4B4B; color: #FF4B4B; font-weight: bold;'] * len(row)
            return [''] * len(row)

        with placeholder.container():
            st.write(f"实时监控中... (OKX/Gate/Binance/Bitget/Huobi/Bybit)")
            st.dataframe(df_final.style.apply(style_rows, axis=1), use_container_width=True, height=800)
        
        await asyncio.sleep(refresh_sec)

if __name__ == "__main__":
    asyncio.run(main())
