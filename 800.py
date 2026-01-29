import streamlit as st
import ccxt.pro as ccxt_pro
import pandas as pd
import numpy as np
import asyncio
import time
import nest_asyncio

nest_asyncio.apply()

st.set_page_config(page_title="2026量化神兵-WebSocket版", layout="wide")

st.title("🚀 加密货币聚合扫描器 (WebSocket实时版 - 防超时)")
st.markdown("点击'启动 WebSocket 订阅'后等待数据推送。如果仍失败，尝试本地跑或加代理。")

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

if len(symbols) > 20:
    st.warning("建议先用 <20 个交易对测试，太多会增加 WS 连接压力。")

# --- 参数 ---
timeframe = st.selectbox("周期", ["1m", "5m", "15m", "1h"], index=1)
refresh_sec = st.slider("刷新间隔(秒)", 5, 120, 30)
vol_multiplier = st.slider("放量阈值 x", 1.0, 5.0, 2.5)

# --- WS 管理 ---
@st.cache_resource
def get_exchange():
    ex = ccxt_pro.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'},
        # 加代理示例（V2RayN socks5）：'proxies': {'https': 'socks5://127.0.0.1:10808'},
    })
    return ex

exchange = get_exchange()

candle_cache = {}

N_dict = {"1m": 40, "5m": 20, "15m": 12, "1h": 8}

async def subscribe_and_update():
    global candle_cache
    while True:
        try:
            for sym in symbols:
                try:
                    ohlcv_list = await exchange.watchOHLCV(sym, timeframe, limit=1)
                    if ohlcv_list:
                        latest = ohlcv_list[-1]
                        sym_key = sym.upper()
                        if sym_key not in candle_cache:
                            hist = await exchange.fetch_ohlcv(sym, timeframe, limit=N_dict[timeframe] + 20)
                            df = pd.DataFrame(hist, columns=['t', 'o', 'h', 'l', 'c', 'v'])
                            candle_cache[sym_key] = df
                        else:
                            df = candle_cache[sym_key]
                            new_row = pd.DataFrame([latest], columns=['t', 'o', 'h', 'l', 'c', 'v'])
                            if df['t'].iloc[-1] == latest[0]:
                                df.iloc[-1] = new_row.iloc[0]
                            else:
                                df = pd.concat([df, new_row], ignore_index=True)
                                df = df.tail(N_dict[timeframe] + 30)
                            candle_cache[sym_key] = df
                except Exception as inner_e:
                    st.warning(f"{sym} 更新失败: {inner_e}")
                    await asyncio.sleep(5)
            await asyncio.sleep(1)
        except Exception as e:
            st.error(f"WS 断开: {e}，10秒后重连...")
            await asyncio.sleep(10)

# 按钮启动控制
if 'ws_started' not in st.session_state:
    st.session_state.ws_started = False
    st.session_state.ws_task = None

if st.button("启动 WebSocket 订阅（只点一次）"):
    if not st.session_state.ws_started:
        try:
            # 显式处理 no running loop：新建 loop 并设置
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            st.session_state.ws_task = loop.create_task(subscribe_and_update())
            st.session_state.ws_started = True
            st.success("WebSocket 订阅启动成功！正在后台接收推送...（初次可能需几秒补历史数据）")
            st.info("如果无数据更新，检查控制台/日志，或加代理重试。")
        except Exception as e:
            st.error(f"启动失败（新建loop也异常）: {str(e)}\n建议：\n1. 刷新页面重试\n2. 本地跑测试\n3. 加 V2RayN 代理到 ccxt 配置")
    else:
        st.info("订阅已在运行。")

placeholder = st.empty()

def compute_signals():
    data_rows = []
    for symbol in symbols:
        df = candle_cache.get(symbol)
        if df is None or len(df) < 5:
            data_rows.append([symbol, "-", "-", "-", "-", "", "", "无数据 (等待WS)"])
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
        alert = "⚠️" if sig_list else ""
        status = "WS实时" if len(df) > 10 else "补齐历史中"

        data_rows.append([
            symbol, f"{curr_c:.4f}", f"{change:+.2f}%", f"{curr_v:,.0f}", 
            f"{vol_ratio:.2f}x", ",".join(sig_list), alert, status
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

# 主循环（定时刷新 UI）
async def main_loop():
    while True:
        compute_signals()
        await asyncio.sleep(refresh_sec)

if __name__ == "__main__":
    asyncio.run(main_loop())
