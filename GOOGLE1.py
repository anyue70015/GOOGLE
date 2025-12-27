import streamlit as st
import requests
import numpy as np
import time
import pandas as pd
from io import StringIO

st.set_page_config(page_title="短线扫描-科学修复版", layout="wide")
st.title("🎯 短线扫描（修复PF7计算差异）")

# ==================== 修复的核心算法 ====================
HEADERS = {"User-Agent": "Mozilla/5.0"}

def fetch_data_consistent(symbol, range_str="1y"):
    """一致的数据获取函数"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range_str}&interval=1d"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        data = resp.json()["chart"]["result"][0]
        quote = data["indicators"]["quote"][0]
        
        # 使用pandas确保一致性
        df = pd.DataFrame({
            "close": quote["close"],
            "high": quote["high"],
            "low": quote["low"],
            "volume": quote["volume"]
        })
        
        # 统一的数据清洗
        df = df.dropna()
        df = df[df['volume'] > 0]
        
        if len(df) < 80:  # 折中的数据要求
            return None
            
        return df
    except:
        return None

def ema_consistent(x, span):
    """一致的EMA计算"""
    alpha = 2 / (span + 1)
    result = np.empty_like(x)
    result[0] = x[0]
    for i in range(1, len(x)):
        result[i] = alpha * x[i] + (1 - alpha) * result[i-1]
    return result

def rolling_mean_consistent(x, window):
    """一致的滚动平均 - 修复边界问题"""
    if len(x) < window:
        return np.full_like(x, np.mean(x))
    
    # 使用pandas但确保前window-1个值合理
    result = pd.Series(x).rolling(window=window, min_periods=1).mean()
    return result.values

def calculate_signals(df):
    """计算技术指标信号"""
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    volume = df['volume'].values
    
    # 1. MACD
    ema12 = ema_consistent(close, 12)
    ema26 = ema_consistent(close, 26)
    macd_line = ema12 - ema26
    signal = ema_consistent(macd_line, 9)
    macd_hist = macd_line - signal
    
    # 2. RSI
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    alpha = 1/14
    gain_ema = np.empty_like(gain)
    loss_ema = np.empty_like(loss)
    gain_ema[0] = gain[0]
    loss_ema[0] = loss[0]
    for i in range(1, len(gain)):
        gain_ema[i] = alpha * gain[i] + (1 - alpha) * gain_ema[i-1]
        loss_ema[i] = alpha * loss[i] + (1 - alpha) * loss_ema[i-1]
    rs = gain_ema / (loss_ema + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    
    # 3. ATR
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = ema_consistent(tr, 14)
    
    # 4. OBV
    direction = np.sign(np.diff(close, prepend=close[0]))
    obv = np.cumsum(direction * volume)
    
    # 移动平均
    vol_ma20 = rolling_mean_consistent(volume, 20)
    atr_ma20 = rolling_mean_consistent(atr, 20)
    obv_ma20 = rolling_mean_consistent(obv, 20)
    
    return {
        'close': close,
        'macd_hist': macd_hist,
        'rsi': rsi,
        'atr': atr,
        'obv': obv,
        'volume': volume,
        'vol_ma20': vol_ma20,
        'atr_ma20': atr_ma20,
        'obv_ma20': obv_ma20
    }

def backtest_corrected(close, signals, steps=7):
    """修正的回测函数 - 确保与第一段代码一致"""
    # 关键修复：使用与第一段代码相同的逻辑
    if len(close) <= steps + 1:
        return 0.5, 1.0
    
    # 信号必须>=3（5个指标中的3个）
    idx = np.where(signals[:-steps] >= 3)[0]
    
    if len(idx) == 0:
        return 0.5, 1.0
    
    # 关键：使用close[idx + steps]，不是close[:-steps]
    rets = close[idx + steps] / close[idx] - 1
    
    win_rate = np.mean(rets > 0)
    
    # 关键：与第一段代码相同的PF计算
    winning = rets[rets > 0]
    losing = rets[rets <= 0]
    
    if len(losing) > 0 and abs(losing.sum()) > 1e-9:
        pf = winning.sum() / abs(losing.sum())
    else:
        pf = 999.0 if len(winning) > 0 else 1.0
    
    return win_rate, pf

def analyze_stock_corrected(symbol):
    """修正的股票分析函数"""
    df = fetch_data_consistent(symbol)
    if df is None:
        return None
    
    indicators = calculate_signals(df)
    
    close = indicators['close']
    macd_hist = indicators['macd_hist']
    rsi = indicators['rsi']
    atr = indicators['atr']
    obv = indicators['obv']
    volume = indicators['volume']
    vol_ma20 = indicators['vol_ma20']
    atr_ma20 = indicators['atr_ma20']
    obv_ma20 = indicators['obv_ma20']
    
    # 当前信号（5个指标）
    current_signals = [
        macd_hist[-1] > 0,
        volume[-1] > vol_ma20[-1] * 1.1,
        rsi[-1] >= 60,
        atr[-1] > atr_ma20[-1] * 1.1,
        obv[-1] > obv_ma20[-1] * 1.05
    ]
    current_score = sum(current_signals)
    
    # 历史信号（用于回测）
    hist_signals = (
        (macd_hist > 0).astype(int) +
        (volume > vol_ma20 * 1.1).astype(int) +
        (rsi >= 60).astype(int) +
        (atr > atr_ma20 * 1.1).astype(int) +
        (obv > obv_ma20 * 1.05).astype(int)
    )
    
    # 关键修复：与第一段代码相同的回测调用
    prob7, pf7 = backtest_corrected(close[:-1], hist_signals[:-1], 7)
    
    price = close[-1]
    change = (close[-1] / close[-2] - 1) * 100 if len(close) >= 2 else 0
    
    return {
        'symbol': symbol,
        'price': price,
        'change': change,
        'score': current_score,
        'prob7': prob7,
        'pf7': pf7,
        'data_points': len(close)
    }

# ==================== 对比诊断工具 ====================
st.header("🔍 PF7差异诊断工具")

# 输入要诊断的股票
symbol_to_test = st.text_input("输入股票代码", "SNDK").upper()

if st.button("诊断PF7差异原因"):
    # 先获取数据
    df = fetch_data_consistent(symbol_to_test)
    
    if df is None:
        st.error("无法获取数据")
    else:
        st.success(f"获取到 {len(df)} 个数据点")
        
        # 计算指标
        indicators = calculate_signals(df)
        close = indicators['close']
        
        # 计算历史信号
        hist_signals = (
            (indicators['macd_hist'] > 0).astype(int) +
            (indicators['volume'] > indicators['vol_ma20'] * 1.1).astype(int) +
            (indicators['rsi'] >= 60).astype(int) +
            (indicators['atr'] > indicators['atr_ma20'] * 1.1).astype(int) +
            (indicators['obv'] > indicators['obv_ma20'] * 1.05).astype(int)
        )
        
        # 模拟第一段代码的回测
        idx1 = np.where(hist_signals[:-7] >= 3)[0]
        if len(idx1) > 0:
            rets1 = close[idx1 + 7] / close[idx1] - 1
            pf1 = (rets1[rets1 > 0].sum() / abs(rets1[rets1 <= 0].sum()) 
                   if (rets1 <= 0).any() else 999)
        else:
            pf1 = 1.0
        
        # 模拟第二段代码的回测（简化版）
        # 注意：第二段代码实际只用了3个指标，这里我们用5个但阈值=2来模拟
        idx2 = np.where(hist_signals[:-7] >= 2)[0]
        if len(idx2) > 0:
            rets2 = close[idx2 + 7] / close[idx2] - 1
            pf2 = rets2[rets2 > 0].sum() / (abs(rets2[rets2 <= 0].sum()) + 1e-9)
        else:
            pf2 = 1.0
        
        # 显示诊断结果
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("数据点数", len(close))
            st.write(f"信号≥3的数量: {len(idx1)}")
            st.write(f"信号≥2的数量: {len(idx2)}")
        
        with col2:
            st.metric("模拟第一段PF7", f"{pf1:.2f}")
            if len(idx1) > 0:
                st.write(f"盈利交易: {sum(rets1 > 0)}/{len(rets1)}")
                st.write(f"平均盈利: {rets1[rets1 > 0].mean()*100:.1f}%")
        
        with col3:
            st.metric("模拟第二段PF7", f"{pf2:.2f}")
            if len(idx2) > 0:
                st.write(f"盈利交易: {sum(rets2 > 0)}/{len(rets2)}")
                st.write(f"平均盈利: {rets2[rets2 > 0].mean()*100:.1f}%")
        
        # 分析差异原因
        st.subheader("📊 差异分析")
        
        if len(idx1) != len(idx2):
            st.warning(f"**主要差异**：信号数量不同（≥3: {len(idx1)} vs ≥2: {len(idx2)}）")
            st.write("第一段代码使用≥3作为阈值，第二段代码使用≥2（但实际第二段代码回测时只用了3个指标！）")
        
        if abs(pf1 - pf2) > 0.5:
            st.warning(f"**PF7差异显著**: {abs(pf1-pf2):.2f}")
            st.write("可能原因：")
            st.write("1. 信号阈值不同（3 vs 2）")
            st.write("2. PF计算公式不同（除零处理）")
            st.write("3. 数据清洗不同（NaN处理）")

# ==================== 修复版扫描 ====================
st.header("🚀 修复版扫描工具")

# 简单股票池
test_stocks = ["SNDK", "AAPL", "MSFT", "NVDA", "GOOGL", "WDC"]

if st.button("运行修复版扫描"):
    results = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, symbol in enumerate(test_stocks):
        status_text.text(f"扫描 {symbol} ({i+1}/{len(test_stocks)})")
        
        result = analyze_stock_corrected(symbol)
        if result:
            results.append(result)
        
        progress_bar.progress((i + 1) / len(test_stocks))
        time.sleep(2)
    
    if results:
        df_results = pd.DataFrame(results)
        
        # 应用筛选条件
        filtered = df_results[(df_results['pf7'] >= 3.6) | (df_results['prob7'] >= 0.68)]
        
        st.subheader(f"筛选结果 ({len(filtered)}/{len(results)})")
        
        for _, row in filtered.iterrows():
            st.write(
                f"**{row['symbol']}** | 价格: ${row['price']:.2f} ({row['change']:+.2f}%) | "
                f"得分: {row['score']}/5 | 胜率: {row['prob7']*100:.1f}% | PF7: {row['pf7']:.2f}"
            )
        
        # 特别显示SNDK
        sndk_result = df_results[df_results['symbol'] == 'SNDK']
        if not sndk_result.empty:
            st.subheader("🔬 SNDK详细分析")
            row = sndk_result.iloc[0]
            st.write(f"修复版计算的PF7: {row['pf7']:.2f}")
            st.write(f"对比原始第一段代码: 7.53")
            st.write(f"对比原始第二段代码: 6.32")
            st.write(f"修复版与第一段差异: {abs(row['pf7']-7.53):.2f}")
            st.write(f"修复版与第二段差异: {abs(row['pf7']-6.32):.2f}")

# ==================== 核心修复说明 ====================
st.header("🔧 核心修复点总结")

st.markdown("""
### 针对SNDK PF7差异7.53 vs 6.32的修复：

1. **统一数据获取标准**
   - 折中的数据要求：`if len(df) < 80:`
   - 统一使用pandas DataFrame处理

2. **修复滚动平均边界问题**
   ```python
   # 原第一段代码：
   return np.concatenate([np.full(window-1, ma[0]), ma])
   
   # 原第二段代码：
   return pd.Series(x).rolling(window).mean().values  # 前window-1个是NaN
   
   # 修复版：
   return pd.Series(x).rolling(window=window, min_periods=1).mean().values
