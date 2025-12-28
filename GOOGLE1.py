# us_stock_quant_tool.py
# 美股量化工具：简单双均线交叉策略回测
# 支持指定股票（如AAPL）、回测周期（默认最近7个交易日）
# 计算：7天胜率、PF7（7天Profit Factor）、5大指标（总收益率、年化收益率、夏普比率、最大回撤、胜率）

import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

def fetch_data(ticker: str, days: int = 180):
    """
    下载股票历史数据（默认下载180天，确保有足够数据计算均线）
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days + 50)  # 多下载一些用于均线计算
    data = yf.download(ticker, start=start_date, end=end_date)
    if data.empty:
        raise ValueError(f"无法下载 {ticker} 的数据，请检查股票代码或网络。")
    return data

def backtest_strategy(ticker: str = "AAPL", short_window: int = 5, long_window: int = 20, backtest_days: int = 7):
    """
    双均线交叉策略回测（简单示例策略）
    - 短期均线上穿长期均线：买入
    - 短期均线下穿长期均线：卖出
    - 只做多，不做空
    """
    data = fetch_data(ticker)
    
    # 计算均线
    data['Short_MA'] = data['Close'].rolling(window=short_window).mean()
    data['Long_MA'] = data['Close'].rolling(window=long_window).mean()
    
    # 生成信号
    data['Signal'] = 0
    data['Signal'][short_window:] = np.where(
        data['Short_MA'][short_window:] > data['Long_MA'][short_window:], 1, 0)
    data['Position'] = data['Signal'].diff()  # 1: 买入, -1: 卖出
    
    # 限制回测到最近的backtest_days个交易日（约7天）
    recent_data = data[-backtest_days:]
    
    # 计算每日收益率（策略持仓时使用股票收益率）
    recent_data = recent_data.copy()
    recent_data['Returns'] = recent_data['Close'].pct_change()
    recent_data['Strategy_Returns'] = recent_data['Returns'] * recent_data['Signal'].shift(1)
    
    # 累计收益率
    recent_data['Cumulative_Strategy'] = (1 + recent_data['Strategy_Returns']).cumprod()
    recent_data['Cumulative_Market'] = (1 + recent_data['Returns']).cumprod()
    
    # 交易记录（每次买入后到卖出算一笔交易）
    trades = []
    position = 0  # 0: 无仓, 1: 有仓
    entry_price = 0
    
    for index, row in recent_data.iterrows():
        if row['Position'] == 1 and position == 0:  # 买入信号
            position = 1
            entry_price = row['Close']
        elif row['Position'] == -1 and position == 1:  # 卖出信号
            position = 0
            exit_price = row['Close']
            profit = (exit_price - entry_price) / entry_price
            trades.append(profit)
    
    # 如果最后仍有持仓，计算到最新价格的未实现盈亏
    if position == 1:
        exit_price = recent_data['Close'].iloc[-1]
        profit = (exit_price - entry_price) / entry_price
        trades.append(profit)
    
    # 计算7天指标
    total_return_7d = recent_data['Cumulative_Strategy'].iloc[-1] - 1 if len(recent_data) > 0 else 0
    win_rate_7d = (np.sum(np.array(trades) > 0) / len(trades)) * 100 if trades else 0
    gross_profit = np.sum([p for p in trades if p > 0])
    gross_loss = np.abs(np.sum([p for p in trades if p < 0]))
    pf_7d = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
    
    # 5大整体回测指标（使用最近backtest_days数据）
    annual_return = (1 + total_return_7d) ** (252 / backtest_days) - 1 if total_return_7d > -1 else 0
    sharpe_ratio = (recent_data['Strategy_Returns'].mean() / recent_data['Strategy_Returns'].std()) * np.sqrt(252) if recent_data['Strategy_Returns'].std() != 0 else 0
    max_drawdown = ((recent_data['Cumulative_Strategy'].cummax() - recent_data['Cumulative_Strategy']) / recent_data['Cumulative_Strategy'].cummax()).max()
    
    # 输出结果
    print(f"股票: {ticker}   回测最近约 {backtest_days} 个交易日")
    print("="*50)
    print(f"7天专用指标:")
    print(f"  胜率 (7天): {win_rate_7d:.2f}%")
    print(f"  PF7 (Profit Factor 7天): {pf_7d:.2f}" + (" (完美，无亏损)" if pf_7d == float('inf') else ""))
    print(f"  总收益率 (7天): {total_return_7d * 100:.2f}%")
    print("="*50)
    print(f"5大核心指标 (基于7天回测):")
    print(f"  1. 总收益率: {total_return_7d * 100:.2f}%")
    print(f"  2. 年化收益率: {annual_return * 100:.2f}%")
    print(f"  3. 夏普比率 (Sharpe Ratio): {sharpe_ratio:.2f}")
    print(f"  4. 最大回撤 (Max Drawdown): {max_drawdown * 100:.2f}%")
    print(f"  5. 胜率: {win_rate_7d:.2f}%")
    print("="*50)
    
    # 绘图
    plt.figure(figsize=(12, 8))
    plt.plot(recent_data.index, recent_data['Cumulative_Strategy'], label='策略累计收益')
    plt.plot(recent_data.index, recent_data['Cumulative_Market'], label='市场买入持有')
    plt.title(f"{ticker} 双均线策略 vs 买入持有 (最近约{backtest_days}天)")
    plt.legend()
    plt.grid()
    plt.show()

# 使用示例
if __name__ == "__main__":
    # 可修改股票代码和回测天数
    backtest_strategy(ticker="AAPL", short_window=5, long_window=20, backtest_days=7)
    # 其他股票示例：TSLA, MSFT, NVDA 等
