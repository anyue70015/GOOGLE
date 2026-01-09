import streamlit as st
import pandas as pd
import numpy as np
import ccxt
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import time

# --- 页面配置 ---
st.set_page_config(page_title="币安小时级强势币扫描器", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #1e2130; padding: 15px; border-radius: 10px; }
    .strong-signal { color: #00ff00; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

class BinanceScanner:
    def __init__(self, proxy=None):
        # 币安连接初始化
        config = {
            'timeout': 20000,
            'enableRateLimit': True,
        }
        if proxy:
            config['proxies'] = {'http': proxy, 'https': proxy}
        
        self.exchange = ccxt.binance(config)

    def fetch_ohlcv_safe(self, symbol):
        """抓取并处理数据"""
        try:
            # 抓取 100 小时 K 线
            bars = self.exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100)
            if len(bars) < 60: return None
            
            df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
            
            # 计算技术指标
            df['sma20'] = df['close'].rolling(20).mean()
            df['sma50'] = df['close'].rolling(50).mean()
            df['vol_sma'] = df['volume'].rolling(20).mean() # 20小时平均成交量
            
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            # --- 强势逻辑判断 ---
            # 1. 多头排列：价格 > SMA20 > SMA50
            is_strong = last['close'] > last['sma20'] > last['sma50']
            
            # 2. 成交量异动：当前成交量是过去 20 小时平均值的几倍
            vol_ratio = last['volume'] / last['vol_sma'] if last['vol_sma'] > 0 else 0
            
            # 3. 24h 涨幅
            price_24h_ago = df['close'].iloc[-24] if len(df) >= 24 else df['close'].iloc[0]
            change_24h = (last['close'] - price_24h_ago) / price_24h_ago * 100
            
            # 4. 偏离度：价格离 SMA20 多远 (太远容易回调)
            bias = (last['close'] - last['sma20']) / last['sma20'] * 100

            return {
                "交易对": symbol,
                "当前价": last['close'],
                "24h涨幅%": round(change_24h, 2),
                "量比": round(vol_ratio, 2),
                "偏离度%": round(bias, 2),
                "状态": "🔥 强力多头" if is_strong else "☁️ 震荡回调",
                "成交额(h)": round(last['close'] * last['volume'], 2)
            }
        except:
            return None

def main():
    st.title("🚀 币安全币种智能扫描器 (小时级)")
    
    # --- 侧边栏配置 ---
    with st.sidebar:
        st.header("扫描设置")
        proxy = st.text_input("代理服务器 (可选)", placeholder="例如 http://127.0.0.1:7890")
        min_vol = st.number_input("最小小时成交额 (USDT)", value=50000, step=10000)
        top_n = st.slider("显示涨幅前几名", 10, 100, 30)
        
        scan_btn = st.button("开始全市场扫描", type="primary", use_container_width=True)

    if scan_btn:
        scanner = BinanceScanner(proxy)
        
        with st.spinner("正在从币安获取活跃交易对..."):
            try:
                markets = scanner.exchange.load_markets()
                symbols = [s for s, m in markets.items() if m['spot'] and s.endswith('/USDT') and m['active']]
                st.success(f"成功获取 {len(symbols)} 个 USDT 交易对")
            except Exception as e:
                st.error(f"连接失败，请检查网络或代理: {e}")
                return

        # --- 并行执行 ---
        progress_bar = st.progress(0)
        status_text = st.empty()
        results = []
        
        start_time = time.time()
        
        # 使用 30 个线程并发
        with ThreadPoolExecutor(max_workers=30) as executor:
            future_to_symbol = {executor.submit(scanner.fetch_ohlcv_safe, s): s for s in symbols}
            
            for i, future in enumerate(future_to_symbol):
                res = future.result()
                if res and res['成交额(h)'] >= min_vol:
                    results.append(res)
                
                if i % 20 == 0:
                    prog = (i + 1) / len(symbols)
                    progress_bar.progress(prog)
                    status_text.text(f"已扫描 {i+1}/{len(symbols)} 个币种...")

        duration = time.time() - start_time
        st.info(f"扫描耗时: {duration:.2f} 秒")

        # --- 数据展示 ---
        if results:
            df = pd.DataFrame(results)
            
            # 排序：按 24h 涨幅
            df = df.sort_values(by='24h涨幅%', ascending=False).reset_index(drop=True)
            
            # 指标概览
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("扫描币种总数", len(symbols))
            with col2:
                st.metric("多头排列币种", len(df[df['状态'] == "🔥 强力多头"]))
            with col3:
                st.metric("平均 24h 涨幅", f"{df['24h涨幅%'].mean():.2f}%")

            st.divider()

            # 结果表格
            st.subheader(f"📊 实时涨幅榜 (前 {top_n} 名)")
            
            # 样式美化
            def color_status(val):
                color = '#00ff00' if val == "🔥 强力多头" else '#888888'
                return f'color: {color}'

            st.dataframe(
                df.head(top_n).style.applymap(color_status, subset=['状态']),
                use_container_width=True,
                height=600
            )
            
            # --- 避险提示 ---
            st.warning("""
                **⚠️ 避险操作指引：**
                1. **看偏离度**：如果偏离度 > 10%，说明短线严重超买，此时扫出涨幅再高也别追，容易被针扎。
                2. **看量比**：量比 > 2 代表有大资金正在突击。
                3. **看状态**：只有“强力多头”才具备持有价值，如果只是 24h 涨幅高但状态是“震荡”，说明只是超跌反弹。
            """)
        else:
            st.error("没有符合筛选条件的币种")

if __name__ == "__main__":
    main()
