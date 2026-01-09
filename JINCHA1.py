import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# --- 页面配置 ---
st.set_page_config(page_title="OKX/Gate 智能选币器", layout="wide")

class SimpleScanner:
    def __init__(self):
        # 移除了代理配置，直接连接
        self.exchanges = {
            'OKX': ccxt.okx({'timeout': 20000, 'enableRateLimit': True}),
            'Gate': ccxt.gateio({'timeout': 20000, 'enableRateLimit': True})
        }
        self.btc_change_1h = 0.0

    def get_btc_status(self):
        """获取大盘基准，默认从 OKX 获取 BTC 走势"""
        try:
            ohlcv = self.exchanges['OKX'].fetch_ohlcv('BTC/USDT', '1h', limit=2)
            self.btc_change_1h = (ohlcv[-1][4] - ohlcv[-2][4]) / ohlcv[-2][4] * 100
            return True
        except:
            return False

    def analyze_coin(self, exch_name, symbol):
        """核心选币逻辑"""
        try:
            exch = self.exchanges[exch_name]
            # 获取 100 小时数据
            bars = exch.fetch_ohlcv(symbol, '1h', limit=100)
            if len(bars) < 60: return None
            
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # 1. 计算技术指标
            df['sma20'] = df['c'].rolling(20).mean()
            df['sma50'] = df['c'].rolling(50).mean()
            
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            
            # --- 选币策略维度 ---
            # A. 趋势强度 (1h 多头排列)
            is_uptrend = curr['c'] > curr['sma20'] > curr['sma50']
            
            # B. 相对强度 (是否跑赢 BTC)
            change_1h = (curr['c'] - prev['c']) / prev['c'] * 100
            is_outperforming_btc = change_1h > self.btc_change_1h
            
            # C. 量能爆发 (当前量 vs 24小时均量)
            vol_ratio = curr['v'] / df['v'].tail(24).mean()
            
            # D. 位置判断 (偏离度：离 20 线多远)
            bias = (curr['c'] - curr['sma20']) / curr['sma20'] * 100
            
            # --- 评分系统 ---
            score = 0
            tags = []
            if is_uptrend: 
                score += 2
                tags.append("趋势向上")
            if is_outperforming_btc: 
                score += 3
                tags.append("强于大盘")
            if vol_ratio > 2.0: 
                score += 3
                tags.append("放量启动")
            if 0 < bias < 2.0: 
                score += 2
                tags.append("回踩均线") # 入场风险低

            # 24小时涨幅
            change_24h = (curr['c'] - df['c'].iloc[-24]) / df['c'].iloc[-24] * 100

            return {
                "来源": exch_name,
                "交易对": symbol,
                "评分": score,
                "信号": " | ".join(tags),
                "24h涨幅%": round(change_24h, 2),
                "1h涨幅%": round(change_1h, 2),
                "量比": round(vol_ratio, 2),
                "偏离度%": round(bias, 2),
                "成交额(h)": round(curr['c'] * curr['v'], 0)
            }
        except:
            return None

def main():
    st.title("🎯 OKX & Gate 狙击手选币器")
    st.caption("不再看已涨飞的币，只看“趋势刚起、有量、且在支撑位”的潜力品种")
    
    with st.sidebar:
        st.header("筛选过滤")
        min_score = st.slider("最低评分要求", 0, 10, 5)
        min_vol = st.number_input("最小时成交额 (USDT)", value=30000)
        target_exchanges = st.multiselect("选择交易所", ["OKX", "Gate"], default=["OKX", "Gate"])
        run = st.button("开始全市场选币", type="primary", use_container_width=True)

    if run:
        scanner = SimpleScanner()
        if not scanner.get_btc_status():
            st.error("大盘数据获取失败，请检查网络连接。")
            return

        st.info(f"📊 基准：BTC 过去 1 小时表现 {scanner.btc_change_1h:.2f}%")
        
        all_tasks = []
        with ThreadPoolExecutor(max_workers=30) as executor:
            for name in target_exchanges:
                st.write(f"正在加载 {name} 市场列表...")
                try:
                    markets = scanner.exchanges[name].load_markets()
                    symbols = [s for s, m in markets.items() if s.endswith('/USDT') and m.get('spot') and m.get('active')]
                    for s in symbols:
                        all_tasks.append(executor.submit(scanner.analyze_coin, name, s))
                except:
                    st.error(f"{name} 访问受限")

            # 收集结果
            results = []
            progress_bar = st.progress(0)
            for i, f in enumerate(all_tasks):
                res = f.result()
                if res and res['评分'] >= min_score and res['成交额(h)'] >= min_vol:
                    results.append(res)
                if i % 50 == 0:
                    progress_bar.progress(i / len(all_tasks))

        if results:
            df = pd.DataFrame(results).sort_values(by='评分', ascending=False)
            st.subheader(f"✅ 发现 {len(df)} 个符合条件的信号")
            
            # 展示表格
            st.dataframe(df, use_container_width=True, height=600)
            
            st.success("选币建议：优先关注【评分 >= 8】且【偏离度 < 2.5%】的币种，这些属于强势且未涨飞。")
        else:
            st.warning("当前没有高评分币种，建议降低筛选标准或等待行情变化。")

if __name__ == "__main__":
    main()
