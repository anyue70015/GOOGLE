import streamlit as st
import pandas as pd
import ccxt
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="全市场深度狙击镜", layout="wide")

class HyperScanner:
    def __init__(self):
        # 针对 Gate.io 这种币超多的交易所，增加超时耐受
        self.exchanges = {
            'OKX': ccxt.okx({'timeout': 30000, 'enableRateLimit': True}),
            'Gate': ccxt.gateio({'timeout': 30000, 'enableRateLimit': True})
        }
        self.btc_change_1h = 0.0

    def get_btc_status(self):
        try:
            ohlcv = self.exchanges['OKX'].fetch_ohlcv('BTC/USDT', '1h', limit=2)
            self.btc_change_1h = (ohlcv[-1][4] - ohlcv[-2][4]) / ohlcv[-2][4] * 100
            return True
        except: return False

    def analyze_coin(self, exch_name, symbol):
        try:
            exch = self.exchanges[exch_name]
            # 获取 K 线 (1h)
            bars = exch.fetch_ohlcv(symbol, '1h', limit=100)
            if len(bars) < 50: return None
            
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            df['sma20'] = df['c'].rolling(20).mean()
            df['sma50'] = df['c'].rolling(50).mean()
            
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            
            # --- 量化指标 ---
            change_1h = (curr['c'] - prev['c']) / prev['c'] * 100
            vol_ratio = curr['v'] / df['v'].tail(24).mean() if df['v'].tail(24).mean() > 0 else 0
            bias = (curr['c'] - curr['sma20']) / curr['sma20'] * 100
            is_uptrend = curr['c'] > curr['sma20'] > curr['sma50']
            
            # --- 评分逻辑 ---
            score = 0
            if is_uptrend: score += 2
            if change_1h > self.btc_change_1h: score += 3 # 强于大盘
            if vol_ratio > 2.0: score += 3                # 异动
            if 0 < bias < 3: score += 2                   # 位置好

            # --- 入场诊断 ---
            advice = "💡 观察"
            if score >= 7:
                if bias > 6: advice = "⚠️ 评分高但追高"
                elif bias < 2.5: advice = "🚀 极品起爆点"
                else: advice = "✅ 强势持仓"

            return {
                "来源": exch_name,
                "交易对": symbol,
                "评分": score,
                "入场诊断": advice,
                "量比": round(vol_ratio, 2),
                "偏离度%": round(bias, 2),
                "24h涨幅%": round((curr['c'] - df['c'].iloc[-24]) / df['c'].iloc[-24] * 100, 2),
                "成交额(h)": round(curr['c'] * curr['v'], 0)
            }
        except: return None

def main():
    st.title("🛰️ 全球币种深度扫描器 (全量版)")
    
    with st.sidebar:
        min_vol = st.number_input("过滤低成交量 (USDT/h)", value=10000)
        target_ex = st.multiselect("选择平台", ["OKX", "Gate"], default=["OKX", "Gate"])
        run = st.button("开始深度扫描", type="primary")

    if run:
        scanner = HyperScanner()
        scanner.get_btc_status()
        
        all_results = []
        for name in target_ex:
            st.write(f"正在深度解析 {name} 市场...")
            markets = scanner.exchanges[name].load_markets()
            # 强化筛选：只要带 USDT 且是现货
            symbols = [s for s, m in markets.items() if 'USDT' in s and m.get('spot')]
            st.write(f"发现 {len(symbols)} 个潜在交易对，开始并行分析...")
            
            with ThreadPoolExecutor(max_workers=50) as executor:
                futures = [executor.submit(scanner.analyze_coin, name, s) for s in symbols]
                for f in futures:
                    res = f.result()
                    if res and res['成交额(h)'] > min_vol:
                        all_results.append(res)

        if all_results:
            df = pd.DataFrame(all_results).sort_values(by='评分', ascending=False)
            st.dataframe(df, use_container_width=True, height=800)
        else:
            st.warning("未扫到币，请检查网络。")

if __name__ == "__main__":
    main()
