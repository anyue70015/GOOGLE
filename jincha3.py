import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="老兵做市商战术板", layout="wide")
st.title("⚔️ 老兵 30 年做市商：10天回血战术板")

def calculate_strategy(df, key_value=3, atr_period=10):
df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=atr_period)
n_loss = key_value * df['atr']
ts = np.zeros(len(df))
for i in range(1, len(df)):
p_ts = ts[i-1]
c = df['Close'].iloc[i]
pc = df['Close'].iloc[i-1]
if c > p_ts and pc > p_ts:
ts[i] = max(p_ts, c - n_loss.iloc[i])
elif c < p_ts and pc < p_ts:
ts[i] = min(p_ts, c + n_loss.iloc[i])
else:
ts[i] = c - n_loss.iloc[i] if c > p_ts else c + n_loss.iloc[i]
df['ts'] = ts
df['mfi'] = ta.mfi(df['High'], df['Low'], df['Close'], df['Volume'], length=14)
counts, bins = np.histogram(df['Close'], bins=50, weights=df['Volume'])
poc_price = bins[np.argmax(counts)]
return df, poc_price

st.sidebar.header("🎯 决战目标")
target = st.sidebar.text_input("代码 (美股如 SNDK, 币如 BTC-USD)", "SNDK")
days = st.sidebar.slider("回测天数", 30, 365, 180)

if target:
df = yf.download(target, period=f"{days}d", interval="1d")
if not df.empty:
df, poc = calculate_strategy(df)
last = df.iloc[-1]
