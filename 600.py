# ================================
# 币圈信号筛选策略代码（4小时级别）
# 策略名称：70%+2-3分 逻辑（4小时版）
# 适用场景：加密货币短线轮动（每4小时运行一次筛选）
# 作者：基于你的交易逻辑编写
# 日期：2026年1月
# ================================

import pandas as pd
import numpy as np
from typing import List, Dict, Optional
import datetime

# 假设你的数据来源是一个DataFrame，每行代表一个币种（每4小时更新一次）
# 必须包含以下列：
# 'symbol'          : 币种名称（如 'BTC/USDT', 'ETH/USDT', 'SOL/USDT'）
# 'prob_4h'         : 4小时上涨概率（百分比，如 76.4 表示 76.4%）
# 'score_5'         : 五大指标得分（0/5, 1/5, 2/5, 3/5, 4/5, 5/5 中的一个整数）
# 'price'           : 当前价格（可选，用于排序或计算权重）
# 'timestamp'       : 数据时间戳（可选，用于记录）
# 'pf_4h'           : 4小时PF值（可选，本策略不使用）

def filter_70plus_2to3_4h_strategy(df: pd.DataFrame) -> pd.DataFrame:
    """
    核心筛选函数（4小时级别）：只返回满足 “4小时上涨概率 ≥ 70% 且 五大指标得分为 2/5 或 3/5” 的币种
    
    参数:
        df (pd.DataFrame): 输入数据表，必须包含 prob_4h 和 score_5 列
        
    返回:
        pd.DataFrame: 筛选后的4小时建仓信号，按 prob_4h 降序排列
    """
    
    # 数据清洗与类型转换
    df = df.copy()
    df['prob_4h'] = pd.to_numeric(df['prob_4h'], errors='coerce')
    df['score_5'] = pd.to_numeric(df['score_5'], errors='coerce')
    
    # 核心条件
    condition_prob = df['prob_4h'] >= 70.0
    condition_score = df['score_5'].isin([2, 3])  # 只接受 2/5 或 3/5
    
    # 组合条件
    signal_mask = condition_prob & condition_score
    
    # 筛选结果
    signals = df[signal_mask].copy()
    
    # 添加信号说明和当前时间（4小时级别标识）
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    signals['signal_reason'] = f'4小时概率≥70% + 得分2-3/5 ({current_time})'
    signals['timeframe'] = '4h'
    
    # 排序：概率越高越靠前
    signals = signals.sort_values(by='prob_4h', ascending=False).reset_index(drop=True)
    
    return signals

# ================================
# 示例使用（模拟4小时数据）
# ================================

if __name__ == "__main__":
    # 模拟一轮4小时数据（实际中从交易所API、你的信号源每4小时获取）
    data = {
        'symbol': ['TAO/USDT', 'SOL/USDT', 'RENDER/USDT', 'ETH/USDT', 'SUI/USDT', 
                   'HYPE/USDT', 'BNB/USDT', 'DOGE/USDT', 'BTC/USDT', 'AAVE/USDT'],
        'prob_4h': [78.5, 75.2, 72.8, 69.1, 73.9, 67.4, 71.5, 64.2, 76.8, 70.9],
        'score_5': [3, 2, 1, 0, 3, 5, 2, 4, 2, 3],
        'price': [458.2, 142.8, 18.5, 3055, 3.45, 26.1, 895, 0.282, 92000, 285],
        'pf_4h': [6.8, 4.2, 3.9, 2.7, 4.1, 5.2, 3.1, 1.9, 4.5, 3.8]
    }
    
    df = pd.DataFrame(data)
    
    print("=== 当前4小时数据（示例） ===")
    print(df[['symbol', 'prob_4h', 'score_5', 'price']])
    
    print("\n=== 筛选后的4小时建仓信号（70%+2-3分） ===")
    signals = filter_70plus_2to3_4h_strategy(df)
    
    if signals.empty:
        print("本4小时周期无符合信号")
    else:
        print(signals[['symbol', 'prob_4h', 'score_5', 'price', 'signal_reason']])
        
        # 等权分配建议（总资金100万）
        total_capital = 1000000
        if len(signals) > 0:
            capital_per_coin = total_capital / len(signals)
            signals['allocation'] = capital_per_coin
            signals['buy_amount'] = signals['allocation'] / signals['price']
            print("\n等权建仓建议（总资金100万）：")
            print(signals[['symbol', 'price', 'allocation', 'buy_amount']].round(2))
            
            print(f"\n建议操作：当前4小时周期建仓以上币种，持有至下一个4小时周期结束（或得分/概率触发卖出条件）")
