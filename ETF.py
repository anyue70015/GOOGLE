import os
import streamlit as st

# --- 页面配置（必须在最前） ---
st.set_page_config(page_title="2026量化神兵-终极版", layout="wide")

# --- 侧边栏：代理与连接配置 ---
st.sidebar.title("🛠️ 连接设置")
proxy_port = st.sidebar.text_input("代理端口 (Clash填7890, V2Ray填10809)", "7890")
api_mirror = st.sidebar.selectbox("币安镜像节点", ["api1", "api2", "api3"], index=2)

# 动态注入系统环境变量，劫持所有网络请求
os.environ['http_proxy'] = f'http://127.0.0.1:{proxy_port}'
os.environ['https_proxy'] = f'http://127.0.0.1:{proxy_port}'

import ccxt.async_support as ccxt_async
import pandas as pd
import numpy as np
import asyncio
import time

st.title("🚀 加密货币聚合扫描器 (系统劫持版)")
st.markdown("---")

# --- 币种列表处理 ---
uploaded = st.file_uploader("上传币种列表 (.txt)", type="txt")
if uploaded:
    content = uploaded.read().decode("utf-8")
    symbols = [line.strip().upper() for line in content.splitlines() if line.strip()]
    symbols = list(dict.fromkeys(symbols))
    symbols = [s if '/' in s else f"{s}/USDT" for s in symbols]
    st.success(f"已加载 {len(symbols)} 个交易对")
else:
    st.info("💡 请先上传交易对文件以启动监控。")
    st.stop()

# --- 主参数设置 ---
col1, col2, col3, col4 = st.columns(4)
with col1:
    timeframe = st.selectbox("周期", ["1m", "5m", "15m", "1h"], index=1)
with col2:
    refresh_sec = st.slider("刷新(秒)", 5, 60, 20)
with col3:
    vol_multiplier = st.slider("放量阈值", 1.0, 5.0, 2.5)
with col4:
    min_change_pct = st.slider("方法2最小涨幅(%)", 0.05, 2.0, 0.5)

# --- 交易所实例化 ---
exchanges = {}
ex_list = ['binance', 'okx', 'gate', 'bitget', 'huobi', 'bybit']

for name in ex_list:
    cfg = {
        'enableRateLimit': True,
        'options': {'defaultType': 'spot', 'adjustForTimeDifference': True},
        'timeout': 15000,
    }
    if name == 'binance':
        cfg['urls'] = {'api': {'public': f'https://{api_mirror}.binance.com'}}
    
    # 动态获取 ccxt 属性
    ex_class = getattr(ccxt_async, name if name != 'huobi' else 'htx')
    exchanges[name] = ex_class(cfg)

# --- 数据抓取核心 ---
async def fetch_ohlcv(ex, symbol, timeframe, limit):
    try:
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

# --- UI 渲染循环 ---
placeholder = st.empty()

async def main():
    if 'alerted' not in st.session_state:
        st.session_state.alerted = set()

    while True:
        data_rows = []
        for symbol in symbols:
            df, success, fails = await process_symbol(symbol, timeframe)
            status = f"✅{len(success)} ❌{len(fails)}"
            if 'binance' in fails: status += " (Binance连接超时)"
            
            if df is None or len(df) < 5:
                data_rows.append([symbol, "-", "-", "-", "-", "", "", status])
                continue
                
            # 数据转换与清洗
            df[['c','o','v']] = df[['c','o','v']].apply(pd.to_numeric)
            curr_c, prev_c = df['c'].iloc[-1], df['c'].iloc[-2]
            curr_v, avg_v = df['v'].iloc[-1], df['v'].iloc[:-1].tail(15).mean()
            vol_ratio = curr_v / avg_v if avg_v > 0 else 0
            change = (curr_c - prev_c) / prev_c * 100

            # 信号算法逻辑
            sig1 = (curr_c > df['o'].iloc[-1]) and (vol_ratio > vol_multiplier)
            sig2 = (vol_ratio > 1.2) and (change > min_change_pct)
            
            # OBV 逻辑修复
            sig3 = False
            if len(df) >= 10:
                c_vals = df['c'].values
                v_vals = df['v'].values
                if len(c_vals) > 1:
                    obv = np.cumsum(np.sign(np.diff(c_vals)) * v_vals[1:])
                    if len(obv) >= 5:
                        obv_ma = pd.Series(obv).rolling(5).mean().iloc[-1]
                        sig3 = (obv[-1] > obv_ma * 1.03) and (change > 0)

            sig_list = [str(i) for i, s in enumerate([sig1, sig2, sig3], 1) if s]
            has_sig = len(sig_list) > 0
            
            data_rows.append([
                symbol, f"{curr_c}", f"{change:+.2f}%", f"{curr_v:,.0f}", 
                f"{vol_ratio:.2f}x", ",".join(sig_list), "⚠️" if has_sig else "", status
            ])

        # 表格排序与格式化
        df_final = pd.DataFrame(data_rows, columns=["交易对","现价","涨幅","成交量","放量比","方法","信号","状态"])
        df_final['v_val'] = pd.to_numeric(df_final['放量比'].str.replace('x',''), errors='coerce').fillna(0)
        df_final = df_final.sort_values('v_val', ascending=False).drop(columns=['v_val'])

        # --- 清晰的样式：半透明淡红 ---
        def style_rows(row):
            if row["信号"] == "⚠️":
                # 背景极浅红(0.12透明度)，文字深红加粗
                return ['background-color: rgba(255, 75, 75, 0.12); color: #FF4B4B; font-weight: bold; border-left: 5px solid #FF4B4B;'] * len(row)
            return [''] * len(row)

        with placeholder.container():
            st.write(f"⏱️ 刷新时间: {time.strftime('%H:%M:%S')} | 代理端口: {proxy_port}")
            st.dataframe(df_final.style.apply(style_rows, axis=1), use_container_width=True, height=800)
        
        await asyncio.sleep(refresh_sec)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        st.error(f"⚠️ 发生错误: {e}")
