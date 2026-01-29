import streamlit as st
import ccxt.async_support as ccxt_async
import pandas as pd
import numpy as np
import asyncio
import time

# --- 页面配置 ---
st.set_page_config(page_title="量化扫描器-清晰版", layout="wide")
st.title("加密货币聚合扫描器 (视觉增强 & 币安补丁版)")

# --- 币种列表处理 ---
uploaded = st.file_uploader("上传币种列表 (.txt)", type="txt")
if uploaded:
    content = uploaded.read().decode("utf-8")
    symbols = [line.strip().upper() for line in content.splitlines() if line.strip()]
    symbols = list(dict.fromkeys(symbols))
    symbols = [s if '/' in s else f"{s}/USDT" for s in symbols]
    st.success(f"已加载 {len(symbols)} 个交易对")
else:
    st.info("💡 请先上传交易对文件")
    st.stop()

# --- 参数设置区 ---
col1, col2, col3, col4 = st.columns(4)
with col1:
    timeframe = st.selectbox("K线周期", ["1m", "5m", "15m", "1h"], index=1)
with col2:
    refresh_sec = st.slider("刷新间隔", 5, 60, 20)
with col3:
    vol_multiplier = st.slider("成交量放大倍数", 1.0, 5.0, 2.5)
with col4:
    min_change_pct = st.slider("方法2最小涨幅(%)", 0.05, 2.0, 0.5)

# --- 交易所配置 (针对币安连接的终极尝试) ---
# 如果你的代理端口不是 10809，请在下面修改
proxy_url = 'http://127.0.0.1:10809' 

ex_config = {
    'binance': {
        'urls': {'api': {'public': 'https://api1.binance.com'}},
        'proxies': {'http': proxy_url, 'https': proxy_url} 
    },
    'okx': {}, 'gate': {}, 'bitget': {}, 'huobi': {}, 'bybit': {}
}

exchanges = {}
for name, cfg in ex_config.items():
    ex_class = getattr(ccxt_async, name if name != 'huobi' else 'htx')
    exchanges[name] = ex_class({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'},
        'timeout': 10000, # 增加到10秒超时
        **cfg
    })

# --- 核心抓取函数 ---
async def fetch_ohlcv(ex, symbol, timeframe, limit):
    try:
        data = await asyncio.wait_for(ex.fetch_ohlcv(symbol, timeframe, limit=limit), timeout=8.0)
        return data, None
    except Exception as e:
        return None, str(e)

async def process_symbol(symbol, timeframe):
    N = {"1m": 60, "5m": 20, "15m": 12, "1h": 8}[timeframe]
    tasks = [fetch_ohlcv(ex, symbol, timeframe, N + 10) for ex in exchanges.values()]
    results = await asyncio.gather(*tasks)
    
    agg_df = None
    success_list = []
    fail_list = []
    
    for (name, ex), (ohlcv, err) in zip(exchanges.items(), results):
        if ohlcv and len(ohlcv) > 5:
            df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
            success_list.append(name)
            if agg_df is None:
                agg_df = df.copy()
            else:
                agg_df['v'] += df['v']
        else:
            fail_list.append(name)
            
    return agg_df, success_list, fail_list

# --- 主循环 ---
placeholder = st.empty()

async def main():
    while True:
        data_rows = []
        for symbol in symbols:
            df, success, fails = await process_symbol(symbol, timeframe)
            
            # 状态显示优化
            status_str = f"✅{len(success)} ❌{len(fails)}"
            if 'binance' in fails:
                status_str += " (Binance连不上，请检查10809端口)"
            
            if df is None or len(df) < 5:
                data_rows.append([symbol, "无数据", "", "", "", "", "", status_str])
                continue
                
            # 数据清洗
            for col in ['c','o','h','l','v']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.dropna(subset=['c','v'])

            curr_c, prev_c = df['c'].iloc[-1], df['c'].iloc[-2]
            curr_v, avg_v = df['v'].iloc[-1], df['v'].iloc[:-1].tail(15).mean()
            vol_ratio = curr_v / avg_v if avg_v > 0 else 0
            price_change = (curr_c - prev_c) / prev_c * 100

            # 信号算法
            sig1 = (curr_c > df['o'].iloc[-1]) and (vol_ratio > vol_multiplier)
            sig2 = (vol_ratio > 1.0) and (price_change > min_change_pct)
            sig3 = False
            if len(df) >= 20:
                c_vals = df['c'].values
                v_vals = df['v'].values
                if len(c_vals) > 1:
                    price_diff = np.diff(c_vals)
                    obv_series = np.cumsum(np.sign(price_diff) * v_vals[1:])
                    obv_ma = pd.Series(obv_series).rolling(10).mean().iloc[-1]
                    sig3 = (obv_series[-1] > obv_ma * 1.03) and (price_change > 0)

            sig_list = [str(i) for i, s in enumerate([sig1, sig2, sig3], 1) if s]
            has_sig = len(sig_list) > 0
            
            data_rows.append([
                symbol, f"{curr_c:.4f}", f"{price_change:+.2f}%",
                f"{curr_v:,.0f}", f"{vol_ratio:.2f}x", 
                ",".join(sig_list), "⚠️" if has_sig else "", status_str
            ])

        # 渲染表格并应用视觉优化
        df_final = pd.DataFrame(data_rows, columns=["交易对","现价","涨幅","聚合成交量","放量比","方法","信号","状态"])
        df_final['v_val'] = pd.to_numeric(df_final['放量比'].str.replace('x',''), errors='coerce').fillna(0)
        df_final = df_final.sort_values('v_val', ascending=False).drop(columns=['v_val'])

        # --- 重点：视觉透明度优化 ---
        def style_rows(row):
            if row["信号"] == "⚠️":
                # 使用带透明度的浅红色，确保文字清晰
                return ['background-color: rgba(255, 0, 0, 0.2); font-weight: bold; color: white;'] * len(row)
            return [''] * len(row)

        with placeholder.container():
            st.write(f"⏱️ 更新: {time.strftime('%H:%M:%S')} | 周期: {timeframe}")
            st.dataframe(df_final.style.apply(style_rows, axis=1), use_container_width=True, height=700)

        await asyncio.sleep(refresh_sec)

if __name__ == "__main__":
    asyncio.run(main())
