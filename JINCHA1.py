import streamlit as st
import pandas as pd
import ccxt
from concurrent.futures import ThreadPoolExecutor
import time

# --- 页面配置 ---
st.set_page_config(page_title="多交易所小时级强势币扫描器", layout="wide")

class MultiExchangeScanner:
    def __init__(self, proxy_url=None):
        self.proxy = proxy_url
        self.exchanges = {}
        
        # 初始化交易所配置
        # 注意：币安连不上通常是因为代理没写对。这里使用了 ccxt 的 socksProxy/httpProxy 强制注入
        common_config = {
            'timeout': 30000,
            'enableRateLimit': True,
        }
        
        if proxy_url:
            # 针对币安这种“难搞”的，尝试多重代理注入
            common_config.update({
                'httpProxy': proxy_url,
                'httpsProxy': proxy_url,
                'socksProxy': proxy_url.replace('http', 'socks5') if 'http' in proxy_url else proxy_url
            })

        self.exchanges['Binance'] = ccxt.binance(common_config)
        self.exchanges['OKX'] = ccxt.okx(common_config)
        self.exchanges['Gate'] = ccxt.gateio(common_config)

    def fetch_data(self, exchange_name, symbol):
        """分析单个币种"""
        try:
            exch = self.exchanges[exchange_name]
            # 统一小时线 '1h'
            bars = exch.fetch_ohlcv(symbol, timeframe='1h', limit=100)
            if len(bars) < 50: return None
            
            df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            
            # 计算小时均线
            df['sma20'] = df['c'].rolling(20).mean()
            df['sma50'] = df['c'].rolling(50).mean()
            
            curr = df.iloc[-1]
            prev_24 = df.iloc[-24] if len(df) >= 24 else df.iloc[0]
            
            # 判断逻辑
            is_strong = curr['c'] > curr['sma20'] > curr['sma50']
            change_24h = (curr['c'] - prev_24['c']) / prev_24['c'] * 100
            
            return {
                "来源": exchange_name,
                "交易对": symbol,
                "当前价": curr['c'],
                "24h涨幅%": round(change_24h, 2),
                "状态": "🔥强力多头" if is_strong else "☁️弱势/调整",
                "偏离度%": round((curr['c'] - curr['sma20']) / curr['sma20'] * 100, 2),
                "成交量(h)": round(curr['v'], 2)
            }
        except:
            return None

def main():
    st.title("🛰️ 全球主流交易所 - 小时级实时扫描")
    
    with st.sidebar:
        st.header("1. 连接设置")
        # 如果你用的是 Clash，通常是 http://127.0.0.1:7890
        user_proxy = st.text_input("代理地址", value="http://127.0.0.1:7890", help="国内务必填写代理，否则币安大概率超时")
        
        st.header("2. 筛选设置")
        target_exchanges = st.multiselect("选择交易所", ["Binance", "OKX", "Gate"], default=["Binance", "OKX", "Gate"])
        scan_btn = st.button("开始全市场大扫描", type="primary")

    if scan_btn:
        scanner = MultiExchangeScanner(user_proxy)
        all_results = []
        
        for name in target_exchanges:
            st.write(f"正在读取 {name} 币种列表...")
            try:
                markets = scanner.exchanges[name].load_markets()
                # 只选 USDT 计价的 现货
                symbols = [s for s, m in markets.items() if s.endswith('/USDT') and m.get('spot', True) and m.get('active', True)]
                st.info(f"{name} 共有 {len(symbols)} 个交易对")
                
                # 开始并发扫描该交易所
                with st.spinner(f"正在扫描 {name}..."):
                    with ThreadPoolExecutor(max_workers=40) as executor:
                        tasks = [executor.submit(scanner.fetch_data, name, s) for s in symbols]
                        for f in tasks:
                            res = f.result()
                            if res: all_results.append(res)
            except Exception as e:
                st.error(f"{name} 连接失败: {e}")

        if all_results:
            final_df = pd.DataFrame(all_results)
            # 排序：先看状态，再看涨幅
            final_df = final_df.sort_values(by=['状态', '24h涨幅%'], ascending=[False, False])
            
            st.success(f"扫描完成！全市场共找到 {len(final_df)} 个活跃币种")
            
            # 显示结果表格
            st.dataframe(final_df, use_container_width=True, height=800)
        else:
            st.warning("未找到有效数据，请检查代理设置或网络。")

if __name__ == "__main__":
    main()
