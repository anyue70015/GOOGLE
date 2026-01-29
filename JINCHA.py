import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time

st.set_page_config(page_title="加密货币放量/吃单扫描器", layout="wide")
st.title("加密货币实时放量/吃单扫描器")

# 上传币种列表
uploaded = st.file_uploader("上传币种列表 (.txt，每行一个，如 BTC-USD)", type="txt")
if uploaded:
    content = uploaded.read().decode("utf-8")
    coins = [line.strip().upper() for line in content.splitlines() if line.strip()]
    # 自动补 -USD
    coins = [c if c.endswith('-USD') else f"{c}-USD" for c in coins]
    coins = list(dict.fromkeys(coins))
    st.success(f"已加载 {len(coins)} 个币种")
    st.write("监控列表：", ", ".join(coins[:10]) + " ..." if len(coins) > 10 else ", ".join(coins))
else:
    st.info("请先上传包含币种的txt文件")
    st.stop()

# 参数设置
col1, col2, col3, col4 = st.columns(4)
with col1:
    interval = st.selectbox("K线周期", ["1m", "5m", "15m", "1h"], index=1)
with col2:
    refresh_sec = st.slider("刷新间隔（秒）", 30, 120, 60)
with col3:
    base_vol_mult = st.slider("基础放量倍数阈值", 1.5, 4.0, 2.54, 0.01)
with col4:
    min_change_pct = st.slider("方法2最小涨幅(%)", 0.3, 2.0, 0.6, 0.1)

use_method1 = st.checkbox("方法1：阳线 + 异常放量", value=True)
use_method2 = st.checkbox("方法2：放量上涨 + 尾盘强势（需放量>1x）", value=True)
use_method3 = st.checkbox("方法3：OBV急升（需放量>1x）", value=True)

# 周期参数
N_for_avg = {"1m": 60, "5m": 20, "15m": 12, "1h": 8}[interval]
vol_multiplier = base_vol_mult + (0.5 if interval == "1m" else 0)

# 状态
if 'alerted' not in st.session_state:
    st.session_state.alerted = set()

placeholder = st.empty()
alert_container = st.empty()

while True:
    data_rows = []
    new_alerts = []

    for coin in coins:
        try:
            # 延长 period 解决数据不足
            period = "7d" if interval in ["1m", "5m"] else "1mo"
            df = yf.download(coin, period=period, interval=interval, progress=False)
            if df.empty or len(df) < N_for_avg + 5:
                data_rows.append([coin, "历史不足/空", "", "", "", "", f"len={len(df)}"])
                continue

            df = df.tail(N_for_avg + 10)

            current_close = float(df['Close'].iloc[-1])
            current_open = float(df['Open'].iloc[-1])
            current_high = float(df['High'].iloc[-1])
            current_low = float(df['Low'].iloc[-1])
            current_vol = float(df['Volume'].iloc[-1])

            prev_close = float(df['Close'].iloc[-2])

            if current_vol <= 0:
                data_rows.append([coin, f"{current_close:.2f}", "Vol=0", "0", "0.00x", "", ""])
                continue

            avg_vol = float(df['Volume'].iloc[:-1].mean())
            vol_ratio = current_vol / avg_vol if avg_vol > 0 else 0.0

            price_change = (current_close - prev_close) / prev_close * 100 if prev_close != 0 else 0.0

            # 方法1
            signal1 = False
            if use_method1:
                is_bull = current_close > current_open
                vol_spike = vol_ratio > vol_multiplier
                signal1 = is_bull and vol_spike and vol_ratio > 1.0

            # 方法2：强制 vol_ratio > 1.0
            signal2 = False
            if use_method2 and vol_ratio > 1.0:
                strong_close = (current_high - current_close) / (current_high - current_low + 1e-8) < 0.3
                vol_spike = vol_ratio > vol_multiplier
                signal2 = ((price_change > min_change_pct) and vol_spike) or strong_close

            # 方法3：强制 vol_ratio > 1.0 + 长度
            signal3 = False
            if use_method3 and len(df) >= 21 and vol_ratio > 1.0:
                obv = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
                obv_ma = float(obv.rolling(20).mean().iloc[-1])
                current_obv = float(obv.iloc[-1])
                signal3 = (current_obv > obv_ma * 1.05) and (price_change > 0)

            has_signal = signal1 or signal2 or signal3

            signals_str = []
            if signal1: signals_str.append("1")
            if signal2: signals_str.append("2")
            if signal3: signals_str.append("3")
            signals_display = ", ".join(signals_str) if signals_str else ""

            row = [
                coin,
                f"{current_close:.2f}",
                f"{price_change:+.2f}%",
                f"{int(current_vol):,}",
                f"{vol_ratio:.2f}x",
                signals_display,
                "⚠️" if has_signal else ""
            ]
            data_rows.append(row)

            # 报警
            key = f"{coin}_{interval}"
            if has_signal and key not in st.session_state.alerted:
                alert_msg = f"【{coin} {interval}】吃单信号！涨幅{price_change:+.2f}%，放量{vol_ratio:.2f}x → 方法{signals_display}"
                new_alerts.append(alert_msg)
                st.session_state.alerted.add(key)

                st.components.v1.html(
                    """
                    <audio autoplay>
                        <source src="https://www.soundjay.com/buttons/beep-07.mp3" type="audio/mpeg">
                    </audio>
                    <script>
                        var audio = document.querySelector('audio');
                        audio.play().catch(function(error) {
                            console.log("Autoplay blocked: " + error);
                            alert("请点击页面允许自动声音播放");
                        });
                    </script>
                    """,
                    height=0
                )

        except Exception as e:
            data_rows.append([coin, "错误", str(e)[:40], "", "", "", ""])

    columns = ["币种", "当前价", "涨幅", "成交量", "放量倍数", "触发方法", "信号"]
    df_display = pd.DataFrame(data_rows, columns=columns)

    def highlight(row):
        return ['background-color: #ffcccc' if row["信号"] == "⚠️" else ''] * len(row)

    styled = df_display.style.apply(highlight, axis=1)

    with placeholder.container():
        st.subheader(f"当前监控（周期：{interval}，刷新间隔：{refresh_sec}秒）")
        st.dataframe(styled, use_container_width=True, height=600)

        if new_alerts:
            for msg in new_alerts:
                st.error(msg)

    time.sleep(refresh_sec)
    st.rerun()
