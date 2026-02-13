import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="老兵做市商战术板", layout="wide")
st.title("⚔️ 老兵 30 年做市商：10天回血战术板")

def calculate_strategy(df):
# 下面这些行必须比 def 往右缩进 4 个空格
df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=10)
n_loss = 3 * df['atr']
ts = np.zeros(len(df))
for i in range(1, len(df)):
if df['Close'].iloc[i] > ts[i-1]:
ts[i] = max(ts[i-1], df['Close'].iloc[i] - n_loss.iloc[i])
else:
ts[i] = df['Close'].iloc[i] + n_loss.iloc[i]
df['ts'] = ts
df['mfi'] = ta.mfi(df['High'], df['Low'], df['Close'], df['Volume'], length=14)
counts, bins = np.histogram(df['Close'], bins=50, weights=df['Volume'])
poc_price = bins[np.argmax(counts)]
return df, poc_price

target = st.sidebar.text_input("代码 (如 SNDK 或 BTC-USD)", "SNDK")

if target:
df = yf.download(target, period="6mo", interval="1d")
if not df.empty:
df, poc = calculate_strategy(df)
last = df.iloc[-1]
c1, c2, c3 = st.columns(3)
c1.metric("现价", f"last[′Close′]:.2f")c2.metric("生命线(ts)",f"{last['ts']:.2f}")
c3.metric("资金流 (MFI)", f"{last['mfi']:.1f}")
