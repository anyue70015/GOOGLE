import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz

# 初始化交易所 (使用 OKX)
ex = ccxt.okx({'enableRateLimit': True})
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def fetch_top_80_symbols():
    """自动获取市值前 80 名 (以成交量作为活跃度代理)"""
    markets = ex.fetch_tickers()
    # 过滤出 USDT 交易对，并按成交量降序排列
    sorted_markets = sorted(markets.items(), 
                            key=lambda x: x[1].get('quoteVolume', 0), 
                            reverse=True)
    # 取前 100 名 (为了容纳一些非 USDT 对)
    top_100 = sorted_markets[:100]
    
    # 精确过滤出前 80 个活跃的 USDT 对
    active_usdt_list = []
    for s in top_100:
        if '/USDT' in s[0]:
            active_usdt_list.append(s[0])
            if len(active_usdt_list) == 80: break
    return active_usdt_list

def check_momentum(sym):
    """扫描特定币种的动量和均线状态"""
    try:
        # 获取日线数据以计算 200MA
        daily_bars = ex.fetch_ohlcv(sym, timeframe='1d', limit=205)
        df_daily = pd.DataFrame(daily_bars, columns=['ts','o','h','l','c','v'])
        ma200 = df_daily['c'].rolling(window=200).mean().iloc[-1]
        
        # 获取 5 分钟线，监控 8:00 - 8:30 动量
        bars = ex.fetch_ohlcv(sym, timeframe='5m', limit=288) # 足够抓取今天的数据
        df = pd.DataFrame(bars, columns=['ts','o','h','l','c','v'])
        df['time'] = pd.to_datetime(df['ts'], unit='ms').dt.tz_localize('UTC').dt.tz_convert(BEIJING_TZ)
        
        # 过滤出 8:00 - 8:30 的数据
        morning_data = df[(df['time'].dt.hour == 8) & (df['time'].dt.minute < 30)]
        if morning_data.empty or len(morning_data) < 2: return None
        
        p_start = morning_data.iloc[0]['o']
        p_end = morning_data.iloc[-1]['c']
        change = (p_end - p_start) / p_start * 100
        
        # 成交量爆发计算 (对比前4小时平均成交量)
        ref_data = df[df['time'].dt.hour < 8].tail(48) # 前4小时数据
        avg_v = ref_data['v'].mean() * 6 # 换算成30分钟量
        v_morning = morning_data['v'].sum()
        v_ratio = v_morning / avg_v if avg_v > 0 else 0
        
        # 当前均线状态
        current_price = df['c'].iloc[-1]
        above_ma200 = current_price > ma200
        
        return {
            "symbol": sym,
            "change": change,
            "v_ratio": v_ratio,
            "above_ma200": above_ma200,
            "current_price": current_price
        }
    except Exception as e:
        print(f"Error checking {sym}: {e}")
        return None

def run_scanner():
    print("🚀 正在获取 Top 80 市值币种...")
    symbols = fetch_top_80_symbols()
    print(f"✅ 已锁定 {len(symbols)} 个目标币种。")
    
    results = []
    for sym in symbols:
        data = check_momentum(sym)
        if data:
            results.append(data)
        time.sleep(0.1) # 频率限制
        
    # 按放量幅度和涨幅综合排序
    df_results = pd.DataFrame(results)
    if df_results.empty: return
    
    # 这里定义我们的“真命天子”筛选规则
    df_results['score'] = df_results['change'] * df_results['v_ratio']
    top_picks = df_results.sort_values(by='score', ascending=False)
    
    # 打印前 5 个最强信号
    print("\n🏆 今日 8:30 动量狙击榜 (Top 5):")
    print(top_picks[['symbol', 'change', 'v_ratio', 'above_ma200', 'current_price']].head(5).to_string(index=False))
    
    # 这里是触发微信推送的逻辑位置
    # send_wx_alert(top_picks.iloc[0]) 

# 模拟运行
if __name__ == "__main__":
    # 在云端服务器，可以用 crontab 设置在每天 08:31 运行此脚本
    run_scanner()
