import streamlit as st
import ccxt.pro as ccxt_pro  # 注意：pro 版
import pandas as pd
import numpy as np
import asyncio
import time
import nest_asyncio

nest_asyncio.apply()

st.set_page_config(page_title="2026量化神兵-WebSocket版", layout="wide")

st.title("🚀 加密货币聚合扫描器 (WebSocket实时版 - 防超时)")
st.markdown("使用Binance WebSocket订阅kline推送，优先Binance数据。适合代理/网络不稳环境。")

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
refresh_sec = st.slider("刷新间隔(秒)", 5, 120, 30)
vol_multiplier = st.slider("放量阈值 x", 1.0, 5.0, 2.5)

# --- WS 订阅管理 ---
@st.cache_resource
def get_exchange():
    ex = ccxt_pro.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'},
        # 如果代理需要：'proxies': {'https': 'socks5://127.0.0.1:10808'},
    })
    return ex

exchange = get_exchange()

# 全局缓存：{symbol: pd.DataFrame of OHLCV}
candle_cache = {}  # symbol -> df
ws_task = None

# N for avg_v 计算
N_dict = {"1m": 40, "5m": 20, "15m": 12, "1h": 8}

async def subscribe_and_update():
    global candle_cache
    ws_symbols = [s.lower().replace('/', '') for s in symbols]  # btcusdt
    streams = [f"{sym}@kline_{timeframe}" for sym in ws_symbols]
    combined_stream = '/'.join(streams)

    while True:
        try:
            # watchOHLCVForSymbols 支持多symbol，但如果太多可分批
            # 这里用 watchOHLCV 单symbol 循环 + 容错
            for sym in symbols:
                try:
                    ohlcv_list = await exchange.watchOHLCV(sym, timeframe, limit=1)  # 只取最新一根更新
                    if ohlcv_list:
                        latest = ohlcv_list[-1]  # [timestamp, o, h, l, c, v]
                        sym_key = sym.upper()
                        if sym_key not in candle_cache:
                            # 初次：fetch 历史补齐
                            hist = await exchange.fetch_ohlcv(sym, timeframe, limit=N_dict[timeframe] + 20)
                            df = pd.DataFrame(hist, columns=['t', 'o', 'h', 'l', 'c', 'v'])
                            candle_cache[sym_key] = df
                        else:
                            df = candle_cache[sym_key]
                            # 更新或追加最新 K
                            new_row = pd.DataFrame([latest], columns=['t', 'o', 'h', 'l', 'c', 'v'])
                            if df['t'].iloc[-1] == latest[0]:
                                df.iloc[-1] = new_row.iloc[0]  # 更新当前 K
                            else:
                                df = pd.concat([df, new_row], ignore_index=True)
                                df = df.tail(N_dict[timeframe] + 30)  # 保持长度
                            candle_cache[sym_key] = df
                except Exception as e:
                    st.warning(f"{sym} WS 更新失败: {e}")
                    await asyncio.sleep(5)
            await asyncio.sleep(1)  # 循环检查
        except Exception as e:
            st.error(f"WS 连接断开: {e}，尝试重连...")
            await asyncio.sleep(10)  # 重连等待

# 启动 WS 后台任务（只跑一次）
if 'ws_running' not in st.session_state:
    st.session_state.ws_running = True
    ws_task = asyncio.create_task(subscribe_and_update())
    st.write("WebSocket 订阅已启动（后台实时更新 K 线）")

placeholder = st.empty()

def compute_signals():
    data_rows = []
    for symbol in symbols:
        df = candle_cache.get(symbol, None)
        if df is None or len(df) < 5:
            data_rows.append([symbol, "-", "-", "-", "-", "", "", "无数据 (WS等待中)"])
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
        
        status = "WS实时" if len(df) > 10 else "历史补齐中"
        
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
            st.write(f"⏱️ 更新: {time.strftime('%Y-%m-%d %H:%M:%S EST')} | WS模式 | 间隔: {refresh_sec}s")
            st.dataframe(df_final.style.apply(style_rows, axis=1), use_container_width=True, height=800)

# 主循环：定时读取缓存计算
async def main_loop():
    while True:
        compute_signals()
        await asyncio.sleep(refresh_sec)

if __name__ == "__main__":
    asyncio.run(main_loop())
