import streamlit as st
import requests
import pandas as pd
import numpy as np
import time

st.set_page_config(page_title="加密货币全网聚合扫描器", layout="wide")
st.title("加密货币实时放量/吃单扫描器（CryptoCompare 全网聚合）")

# 上传币种列表
uploaded = st.file_uploader("上传币种列表 (.txt，每行一个符号，如 BTC)", type="txt")
if uploaded:
    content = uploaded.read().decode("utf-8")
    fsyms = [line.strip().upper() for line in content.splitlines() if line.strip()]
    fsyms = list(dict.fromkeys(fsyms))
    st.success(f"已加载 {len(fsyms)} 个币种")
    st.write("监控列表：", ", ".join(fsyms[:10]) + " ..." if len(fsyms) > 10 else ", ".join(fsyms))
else:
    st.info("请先上传包含符号的txt文件")
    st.stop()

# 参数设置
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    timeframe = st.selectbox("K线周期", ["1m", "5m", "15m", "1h"], index=1)
with col2:
    refresh_sec = st.slider("刷新间隔（秒）", 60, 300, 120)
with col3:
    vol_multiplier = st.slider("放量倍数阈值", 1.5, 5.0, 2.8, 0.01)
with col4:
    min_change_pct = st.slider("方法2最小涨幅(%)", 0.3, 2.0, 0.6, 0.1)
with col5:
    min_abs_vol = st.slider("最小绝对成交量阈值", 100, 10000, 1000, 100, help="低于此值视为无有效成交")

use_method1 = st.checkbox("方法1：阳线 + 异常放量", value=True)
use_method2 = st.checkbox("方法2：放量上涨 + 尾盘强势", value=True)
use_method3 = st.checkbox("方法3：OBV急升", value=True)

N_for_avg = {"1m": 60, "5m": 20, "15m": 12, "1h": 8}[timeframe]

if 'alerted' not in st.session_state:
    st.session_state.alerted = set()

placeholder = st.empty()
alert_container = st.empty()

while True:
    data_rows = []
    new_alerts = []

    for fsym in fsyms:
        try:
            limit = N_for_avg + 20
            url = f"https://min-api.cryptocompare.com/data/v2/histo{'minute' if timeframe in ['1m','5m','15m'] else 'hour'}?fsym={fsym}&tsym=USDT&limit={limit}"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            if data.get('Response') != 'Success' or 'Data' not in data:
                data_rows.append([fsym, "API错误", "", "", "", "", ""])
                continue

            df = pd.DataFrame(data['Data']['Data'])
            if len(df) < N_for_avg + 5:
                data_rows.append([fsym, "历史不足", "", "", "", "", f"根数={len(df)}"])
                continue

            df = df[['time', 'open', 'high', 'low', 'close', 'volumefrom']]
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            df = df.tail(N_for_avg + 10)

            current_close = float(df['close'].iloc[-1])
            current_open = float(df['open'].iloc[-1])
            current_high = float(df['high'].iloc[-1])
            current_low = float(df['low'].iloc[-1])
            current_vol = float(df['volume'].iloc[-1])

            prev_close = float(df['close'].iloc[-2])

            status = ""
            if current_vol <= min_abs_vol:
                status = "无有效成交"
                data_rows.append([fsym, f"{current_close:.2f}", "Vol低", f"{int(current_vol):,}", "0.00x", "", status])
                continue

            avg_vol = float(df['volume'].iloc[:-1].mean())
            vol_ratio = current_vol / avg_vol if avg_vol > 0 else 0.0

            price_change = (current_close - prev_close) / prev_close * 100 if prev_close != 0 else 0.0

            signal1 = use_method1 and (current_close > current_open) and (vol_ratio > vol_multiplier) and (vol_ratio > 1.0)
            signal2 = use_method2 and (vol_ratio > 1.0) and (((price_change > min_change_pct) and (vol_ratio > vol_multiplier)) or ((current_high - current_close) / (current_high - current_low + 1e-8) < 0.3))
            signal3 = False
            if use_method3 and len(df) >= 21 and vol_ratio > 1.0:
                obv = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
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
                fsym,
                f"{current_close:.2f}",
                f"{price_change:+.2f}%",
                f"{int(current_vol):,}",
                f"{vol_ratio:.2f}x",
                signals_display,
                "⚠️" if has_signal else status
            ]
            data_rows.append(row)

            key = f"{fsym}_{timeframe}"
            if has_signal and key not in st.session_state.alerted:
                alert_msg = f"【{fsym} {timeframe}】全网吃单信号！涨幅{price_change:+.2f}%，放量{vol_ratio:.2f}x → 方法{signals_display}"
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
                            alert("浏览器阻止自动播放声音，请点击页面允许音频");
                        });
                    </script>
                    """,
                    height=0
                )

        except Exception as e:
            data_rows.append([fsym, "错误", str(e)[:50], "", "", "", ""])

    columns = ["币种", "当前价 (USDT)", "涨幅", "全网成交量", "放量倍数", "触发方法", "信号/状态"]
    df_display = pd.DataFrame(data_rows, columns=columns)

    def highlight(row):
        if row["信号/状态"] == "⚠️":
            return ['background-color: #ffcccc'] * len(row)
        if "无有效成交" in row["信号/状态"]:
            return ['background-color: #ffffcc'] * len(row)
        return [''] * len(row)

    styled = df_display.style.apply(highlight, axis=1)

    with placeholder.container():
        st.subheader(f"当前监控（CryptoCompare 全网聚合，周期：{timeframe}，刷新间隔：{refresh_sec}秒）")
        st.dataframe(styled, use_container_width=True, height=600)

        if new_alerts:
            for msg in new_alerts:
                st.error(msg)

    time.sleep(refresh_sec)
    st.rerun()
