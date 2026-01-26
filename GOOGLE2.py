# ==================== 核心回测逻辑：好的计算方式 ====================
def backtest_with_stats(close: np.ndarray, score: np.ndarray, steps: int):
    """
    科学计算方式：
    1. 严格隔离未来数据
    2. 计算真实的期望盈亏比 (Profit Factor)
    """
    if len(close) <= steps + 1:
        return 0.5, 0.0
        
    # 找到历史上所有符合买入条件（得分>=3）的索引
    idx = np.where(score[:-steps] >= 3)[0]
    
    if len(idx) == 0:
        return 0.5, 0.0
        
    # 计算持仓7天后的收益率
    rets = close[idx + steps] / close[idx] - 1
    win_rate = (rets > 0).mean()
    
    pos_ret_sum = rets[rets > 0].sum()
    neg_ret_sum = abs(rets[rets <= 0].sum())
    
    # 科学处理 PF 边界：如果有亏损，计算比例；若无亏损，给一个合理的上限
    if neg_ret_sum > 0:
        pf = pos_ret_sum / neg_ret_sum
    else:
        pf = 9.9 if pos_ret_sum > 0 else 0.0
        
    return win_rate, pf

# ==================== 核心计算函数：好的计算方式 ====================
@st.cache_data(show_spinner=False)
def compute_stock_metrics(symbol: str, cfg_key: str = "1年"):
    yahoo_symbol = symbol.upper()
    close, high, low, volume = fetch_yahoo_ohlcv(yahoo_symbol, BACKTEST_CONFIG[cfg_key]["range"])
    
    if close is None:
        return None

    # --- 1. 指标计算 ---
    macd_hist = macd_hist_np(close)
    rsi = rsi_np(close)
    atr = atr_np(high, low, close)
    obv = obv_np(close, volume)
    vol_ma20 = rolling_mean_np(volume, 20)
    atr_ma20 = rolling_mean_np(atr, 20)
    obv_ma20 = rolling_mean_np(obv, 20)

    # --- 2. 信号生成 (Score Array) ---
    s1 = (macd_hist > 0).astype(int)
    s2 = (volume > vol_ma20 * 1.1).astype(int)
    s3 = (rsi >= 60).astype(int)
    s4 = (atr > atr_ma20 * 1.1).astype(int)
    s5 = (obv > obv_ma20 * 1.05).astype(int)
    score_arr = s1 + s2 + s3 + s4 + s5

    # --- 3. 核心计算改进：滚动回测 40 日明细 ---
    # 这一步是为了让你在界面上看到的每一行 PF7 都是动态变化的
    detail_len = min(40, len(close))
    details = []
    dates = pd.date_range(end="2026-01-24", periods=len(close)).strftime("%Y-%m-%d").values # 简便日期处理

    for i in range(len(close) - detail_len, len(close)):
        # 关键改进：close[:i] 确保计算每一天时只参考历史，PF7 会因此每天都波动，非常准确
        sub_prob, sub_pf = backtest_with_stats(close[:i], score_arr[:i], 7)
        chg = (close[i]/close[i-1]-1)*100 if i > 0 else 0
        details.append({
            "日期": dates[i], 
            "价格": round(close[i], 2), 
            "涨跌": f"{chg:+.2f}%",
            "得分": int(score_arr[i]),
            "胜率": f"{sub_prob*100:.1f}%", 
            "PF7": round(sub_pf, 2)
        })

    # --- 4. 整体数据汇总 ---
    # 使用 [:-1] 排除掉最后一天，计算截止到目前的真实历史战绩
    f_prob, f_pf = backtest_with_stats(close[:-1], score_arr[:-1], 7)

    # 134万资金所需的流动性检查
    avg_dollar_vol = (volume[-20:] * close[-20:]).mean()
    is_low_liquidity = avg_dollar_vol < 50_000_000

    return {
        "symbol": symbol.upper(),
        "display_symbol": symbol.upper() + (" (⚠️低流动)" if is_low_liquidity else ""),
        "price": close[-1],
        "change": (close[-1]/close[-2]-1)*100 if len(close)>1 else 0,
        "score": int(score_arr[-1]),
        "prob7": f_prob,
        "pf7": f_pf,
        "sig_details": {
            "MACD>0": bool(s1[-1]),
            "放量": bool(s2[-1]),
            "RSI≥60": bool(s3[-1]),
            "ATR放大": bool(s4[-1]),
            "OBV上升": bool(s5[-1])
        },
        "is_low_liquidity": is_low_liquidity,
        "details": details[::-1] # 这里的 details 现在每天都不一样了
    }
