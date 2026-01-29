import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
import os

st.set_page_config(page_title="加密货币放量/吃单扫描器", layout="wide")
st.title("加密货币实时放量/吃单扫描器")

# ── 上传币种列表 ──
uploaded = st.file_uploader("上传币种列表 (.txt，每行一个符号，如 BTC-USD)", type="txt")
if uploaded:
    content = uploaded.read().decode("utf-8")
    coins = [line.strip().upper() for line in content.splitlines() if line.strip()]
    coins = list(dict.fromkeys(coins))  # 去重
    st.success(f"已加载 {len(coins)} 个币种")
    st.write("监控列表：", ", ".join(coins[:10]) + " ..." if len(coins) > 10 else ", ".join(coins))
else:
    st.info("请先上传包含币种的txt文件")
    st.stop()

# ── 参数设置 ──
col1, col2, col3, col4 = st.columns(4)
with col1:
    interval = st.selectbox("K线周期", ["1m", "5m", "15m", "1h"], index=1)
with col2:
    refresh_sec = st.slider("刷新间隔（秒）", 15, 120, 45, help="太短可能触发API限流")
with col3:
    vol_multiplier = st.slider("放量倍数阈值", 1.5, 4.0, 2.54, 0.01)
with col4:
    min_change_pct = st.slider("方法2最小涨幅(%)", 0.3, 2.0, 0.6, 0.1)

use_method1 = st.checkbox("方法1：阳线 + 异常放量", value=True)
use_method2 = st.checkbox("方法2：放量上涨 + 尾盘强势", value=True)
use_method3 = st.checkbox("方法3：OBV急升（资金净流入）", value=True)

# 不同周期建议的平均窗口
N_for_avg = {
    "1m": 30,    # ≈30分钟
    "5m": 20,    # ≈100分钟
    "15m": 12,   # ≈3小时
    "1h": 8      # ≈8小时
}[interval]

# ── 状态管理 ──
if 'alerted' not in st.session_state:
    st.session_state.alerted = set()  # 已报警的 (coin_interval)

if 'last_alert_time' not in st.session_state:
    st.session_state.last_alert_time = 0

# ── 主扫描逻辑 ──
placeholder = st.empty()  # 用于动态更新表格
alert_container = st.empty()  # 用于显示新警示

while True:
    data_rows = []
    new_alerts = []

    for coin in coins:
        try:
            # 拉取最近数据（2d 确保有足够历史）
            df = yf.download(coin, period="2d", interval=interval, progress=False)
            if df.empty or len(df) < N_for_avg + 5:
                data_rows.append([coin, "数据不足", "", "", "", "", ""])
                continue

            df = df.tail(N_for_avg + 10)  # 多取几根防边界
            current = df.iloc[-1]
            prev = df.iloc[-2]

            avg_vol = df['Volume'].iloc[:-1].mean()
            current_vol = current['Volume']
            vol_ratio = current_vol / avg_vol if avg_vol > 0 else 0

            price_change = (current['Close'] - prev['Close']) / prev['Close'] * 100 if prev['Close'] != 0 else 0

            # 方法1：阳线 + 异常放量
            signal1 = False
            if use_method1:
                is_bull = current['Close'] > current['Open']
                vol_spike = vol_ratio > vol_multiplier
                signal1 = is_bull and vol_spike

            # 方法2：放量上涨 + 尾盘强势
            signal2 = False
            if use_method2:
                strong_close = (current['High'] - current['Close']) / (current['High'] - current['Low'] + 1e-8) < 0.3
                vol_spike = vol_ratio > vol_multiplier
                signal2 = (price_change > min_change_pct and vol_spike) or strong_close

            # 方法3：OBV急升
            signal3 = False
            if use_method3:
                obv = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
                obv_ma = obv.rolling(20).mean().iloc[-1]
                current_obv = obv.iloc[-1]
                signal3 = (current_obv > obv_ma * 1.05) and (price_change > 0)

            has_signal = any([signal1, signal2, signal3])

            signals_str = []
            if signal1: signals_str.append("方法1")
            if signal2: signals_str.append("方法2")
            if signal3: signals_str.append("方法3")
            signals_display = ", ".join(signals_str) if signals_str else ""

            row = [
                coin,
                f"{current['Close']:.2f}",
                f"{price_change:+.2f}%",
                f"{current_vol:,.0f}",
                f"{vol_ratio:.2f}x",
                signals_display,
                "⚠️" if has_signal else ""
            ]
            data_rows.append(row)

            # 报警：只首次触发
            key = f"{coin}_{interval}"
            if has_signal and key not in st.session_state.alerted:
                alert_msg = f"【{coin} {interval}】检测到吃单信号！涨幅 {price_change:+.2f}%，放量 {vol_ratio:.2f}x，触发：{signals_display}"
                new_alerts.append(alert_msg)
                st.session_state.alerted.add(key)

                # 用 JS 播放声音（浏览器自动播放，需用户允许）
                st.components.v1.html(
                    """
                    <audio autoplay>
                        <source src="https://www.soundjay.com/buttons/beep-07.mp3" type="audio/mpeg">
                    </audio>
                    <script>
                        var audio = document.querySelector('audio');
                        audio.play().catch(function(error) {
                            console.log("Autoplay prevented: " + error);
                        });
                    </script>
                    """,
                    height=0
                )

        except Exception as e:
            data_rows.append([coin, "错误", str(e)[:30], "", "", "", ""])

    # 显示表格（信号行背景变红）
    columns = ["币种", "当前价", "涨幅", "成交量", "放量倍数", "触发方法", "信号"]
    df_display = pd.DataFrame(data_rows, columns=columns)

    def highlight_signal(row):
        if row["信号"] == "⚠️":
            return ['background-color: #ffcccc'] * len(row)
        return [''] * len(row)

    styled_df = df_display.style.apply(highlight_signal, axis=1)

    with placeholder.container():
        st.subheader(f"当前监控（周期：{interval}，刷新间隔：{refresh_sec}秒）")
        st.dataframe(styled_df, use_container_width=True, height=600)

        # 显示本次新报警（只显示新出现的）
        if new_alerts:
            with alert_container.container():
                for msg in new_alerts:
                    st.error(msg)

    # 等待下一次刷新
    time.sleep(refresh_sec)
    st.rerun()
