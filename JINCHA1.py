import streamlit as st
import pandas as pd
import ccxt
import time
from concurrent.futures import ThreadPoolExecutor

# --- 页面配置 ---
st.set_page_config(page_title="AI 智能选币狙击镜", layout="wide")

class ProfessionalScanner:
    def __init__(self, proxy=None):
        config = {'timeout': 20000, 'enableRateLimit': True}
        if proxy:
            config.update({'httpProxy': proxy, 'httpsProxy': proxy})
        
        self.binance = ccxt.binance(config)
        self.btc_change_1h = 0.0

    def get_btc_status(self):
        """先获取大盘（BTC）的走势作为基准"""
        try:
            ohlcv = self.binance.fetch_ohlcv('BTC/USDT', '1h', limit=2)
            self.btc_change_1h = (ohlcv[-1][4] - ohlcv[-2][4]) / ohlcv[-2][4] * 100
            return True
        except: return False

    def analyze_coin(self, symbol):
        """核心选币逻辑"""
        try:
            # 获取 100 小时数据
            bars = self.binance.fetch_ohlcv(symbol, '1h', limit=100)
            if len(bars) < 60: return None
            
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # 1. 计算均线
            df['sma20'] = df['c'].rolling(20).mean()
            df['sma50'] = df['c'].rolling(50).mean()
            df['vol_ma'] = df['v'].rolling(20).mean()
            
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            
            # --- 选币策略维度 ---
            # A. 趋势强度 (1h 多头排列)
            is_uptrend = curr['c'] > curr['sma20'] > curr['sma50']
            
            # B. 相对强度 (是否跑赢 BTC)
            change_1h = (curr['c'] - prev['c']) / prev['c'] * 100
            is_outperforming_btc = change_1h > self.btc_change_1h
            
            # C. 量能爆发 (量比)
            vol_ratio = curr['v'] / df['v'].tail(24).mean()
            
            # D. 位置判断 (偏离度：离 20 线多远)
            bias = (curr['c'] - curr['sma20']) / curr['sma20'] * 100
            
            # --- 智能评分系统 (Score) ---
            score = 0
            tags = []
            if is_uptrend: 
                score += 2
                tags.append("趋势向上")
            if is_outperforming_btc: 
                score += 3
                tags.append("强于大盘")
            if vol_ratio > 2.5: 
                score += 3
                tags.append("放量突破")
            if 0 < bias < 2.5: 
                score += 2
                tags.append("回踩支撑") # 离均线近，风险收益比高
            
            # 24小时涨幅
            change_24h = (curr['c'] - df['c'].iloc[-24]) / df['c'].iloc[-24] * 100

            return {
                "交易对": symbol,
                "评分": score,
                "标签": " | ".join(tags),
                "24h涨幅%": round(change_24h, 2),
                "1h涨幅%": round(change_1h, 2),
                "量比": round(vol_ratio, 2),
                "偏离度%": round(bias, 2),
                "成交额(h)": round(curr['c'] * curr['v'], 0)
            }
        except: return None

# --- Streamlit UI ---
def main():
    st.title("🎯 币安狙击手：寻找强势起爆币")
    
    with st.sidebar:
        proxy = st.text_input("代理设置", value="http://127.0.0.1:7890")
        min_score = st.slider("最低评分要求", 0, 10, 5)
        min_vol = st.number_input("最小成交额 (USDT/小时)", value=100000)
        run = st.button("开始精准扫描", type="primary")

    if run:
        scanner = ProfessionalScanner(proxy)
        if not scanner.get_btc_status():
            st.error("连接失败！请检查代理是否开启。")
            return

        st.info(f"当前 BTC 1h 表现: {scanner.btc_change_1h:.2f}% (所有结果将以此为基准对比)")
        
        markets = scanner.binance.load_markets()
        symbols = [s for s, m in markets.items() if s.endswith('/USDT') and m['spot'] and m['active']]
        
        results = []
        progress = st.progress(0)
        
        with ThreadPoolExecutor(max_workers=30) as executor:
            futures = [executor.submit(scanner.analyze_coin, s) for s in symbols]
            for i, f in enumerate(futures):
                res = f.result()
                if res and res['评分'] >= min_score and res['成交额(h)'] > min_vol:
                    results.append(res)
                if i % 20 == 0: progress.progress(i / len(symbols))

        if results:
            df = pd.DataFrame(results).sort_values(by='评分', ascending=False)
            
            # 使用颜色高亮
            st.subheader("💎 筛选出的潜力币种")
            st.dataframe(df, use_container_width=True)
            
            st.markdown("""
            ### 💡 怎么看结果？
            1. **评分 > 8 且 偏离度 < 2%**：这就是**最佳入场点**。说明它很强、在放量，但价格还没飞，就在均线支撑位。
            2. **量比 > 5**：这种币有突发消息，适合短线追逐。
            3. **强于大盘**：如果大盘在跌，这个标签就是你的救命稻草。
            """)
        else:
            st.warning("没找到高分币种，当前市场可能比较平淡或大盘太差。")

if __name__ == "__main__":
    main()
