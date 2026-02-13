import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="老兵做市商战术板", layout="wide")
st.title("⚔️ 老兵 30 年做市商战术板：10天回血决战")

def calculate_strategy(df, key_value=3, atr_period=10):
df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=atr_period)
n_loss = key_value * df['atr']
ts = np.zeros(len(df))
for i in range(1, len(df)):
prev_ts = ts[i-1]
close, prev_close = df['Close'].iloc[i], df['Close'].iloc[i-1]
if close > prev_ts and prev_close > prev_ts:
ts[i] = max(prev_ts, close - n_loss.iloc[i])
elif close < prev_ts and prev_close < prev_ts:
ts[i] = min(prev_ts, close + n_loss.iloc[i])
else:
ts[i] = close - n_loss.iloc[i] if close > prev_ts else close + n_loss.iloc[i]
df['ts'] = ts
df['mfi'] = ta.mfi(df['High'], df['Low'], df['Close'], df['Volume'], length=14)
counts, bins = np.histogram(df['Close'], bins=50, weights=df['Volume'])
poc_price = bins[np.argmax(counts)]
return df, poc_price

st.sidebar.header("🎯 目标选择")
ticker = st.sidebar.text_input("输入代码 (币加 -USD, 美股直接敲)", "SNDK")
period = st.sidebar.selectbox("数据跨度", ["1mo", "3mo", "6mo", "1y"], index=1)

if ticker:
df = yf.download(ticker, period=period, interval="1d")
if not df.empty:
df, poc = calculate_strategy(df)
last = df.iloc[-1]
c1, c2, c3, c4 = st.columns(4)
c1.metric("当前价格", f"last[′Close′]:.2f")c2.metric("止损线(ts)",f"{last['ts']:.2f}", f"{((last['Close']-last['ts'])/last['ts']*100):.1f}%")
c3.metric("资金流 (MFI)", f"{last['mfi']:.1f}")
c4.metric("筹码中心 (POC)", f"${poc:.2f}")
