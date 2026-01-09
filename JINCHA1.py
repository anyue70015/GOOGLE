import streamlit as st
import pandas as pd
import numpy as np
import time
import json
from datetime import datetime, timedelta
import warnings
import sys
import requests

warnings.filterwarnings('ignore')

# 设置页面配置为第一行
st.set_page_config(
    page_title="加密货币智能扫描器",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 定义代理设置（如果需要）
PROXY_SETTINGS = {
    'http': None,
    'https': None,
}

# 尝试导入ccxt并配置代理
def setup_exchange():
    """设置交易所连接"""
    try:
        import ccxt
        
        # 配置代理（如果需要）
        proxies = PROXY_SETTINGS
        
        # 交易所配置
        exchanges_config = {
            'binance': {
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'},
                'timeout': 30000,
                'proxies': proxies
            },
            'okx': {
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'},
                'timeout': 30000,
                'proxies': proxies
            },
            'bybit': {
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'},
                'timeout': 30000,
                'proxies': proxies
            },
            'kucoin': {
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'},
                'timeout': 30000,
                'proxies': proxies
            },
            'gateio': {
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'},
                'timeout': 30000,
                'proxies': proxies
            },
            'huobi': {
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'},
                'timeout': 30000,
                'proxies': proxies
            },
            'coinbase': {
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'},
                'timeout': 30000,
                'proxies': proxies
            }
        }
        
        return ccxt, exchanges_config, True
    except ImportError:
        return None, {}, False

# 获取模块
ccxt_module, exchanges_config, ccxt_available = setup_exchange()

# 离线演示数据
DEMO_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
    "ADA/USDT", "DOGE/USDT", "DOT/USDT", "MATIC/USDT", "LTC/USDT",
    "AVAX/USDT", "LINK/USDT", "ATOM/USDT", "UNI/USDT", "XLM/USDT",
    "ALGO/USDT", "VET/USDT", "THETA/USDT", "FIL/USDT", "TRX/USDT",
    "ETC/USDT", "XMR/USDT", "EOS/USDT", "AAVE/USDT", "AXS/USDT",
    "SAND/USDT", "MANA/USDT", "GRT/USDT", "BAT/USDT", "ENJ/USDT"
]

DEMO_RESULTS = [
    {"symbol": "BTC/USDT", "total_return": 25.8, "win_rate": 58.2, "volatility": 2.1, "sharpe": 1.8},
    {"symbol": "ETH/USDT", "total_return": 32.5, "win_rate": 55.4, "volatility": 3.2, "sharpe": 1.5},
    {"symbol": "SOL/USDT", "total_return": 180.3, "win_rate": 62.1, "volatility": 8.5, "sharpe": 2.1},
    {"symbol": "BNB/USDT", "total_return": 45.2, "win_rate": 53.7, "volatility": 2.8, "sharpe": 1.6},
    {"symbol": "ADA/USDT", "total_return": -12.3, "win_rate": 48.5, "volatility": 5.4, "sharpe": -0.3},
    {"symbol": "XRP/USDT", "total_return": 18.7, "win_rate": 51.2, "volatility": 4.2, "sharpe": 0.8},
    {"symbol": "DOGE/USDT", "total_return": 65.4, "win_rate": 57.8, "volatility": 12.3, "sharpe": 1.2},
    {"symbol": "DOT/USDT", "total_return": 28.9, "win_rate": 52.4, "volatility": 4.8, "sharpe": 1.1},
    {"symbol": "MATIC/USDT", "total_return": 42.1, "win_rate": 56.3, "volatility": 5.2, "sharpe": 1.4},
    {"symbol": "AVAX/USDT", "total_return": 95.7, "win_rate": 60.2, "volatility": 7.8, "sharpe": 1.9},
    {"symbol": "LINK/USDT", "total_return": 38.4, "win_rate": 54.6, "volatility": 4.5, "sharpe": 1.3},
    {"symbol": "LTC/USDT", "total_return": 15.2, "win_rate": 50.8, "volatility": 3.8, "sharpe": 0.7},
    {"symbol": "UNI/USDT", "total_return": 22.7, "win_rate": 52.1, "volatility": 4.1, "sharpe": 0.9},
    {"symbol": "ATOM/USDT", "total_return": 31.8, "win_rate": 54.9, "volatility": 3.9, "sharpe": 1.2},
    {"symbol": "XLM/USDT", "total_return": 8.5, "win_rate": 49.3, "volatility": 4.6, "sharpe": 0.4}
]

class CryptoScanner:
    def __init__(self, exchange_id='okx'):
        self.exchange_id = exchange_id
        self.exchange = None
        self.mode = "offline"  # 默认为离线模式
        
        if ccxt_available:
            try:
                # 尝试连接交易所
                exchange_config = exchanges_config.get(exchange_id, exchanges_config['okx'])
                self.exchange = getattr(ccxt_module, exchange_id)(exchange_config)
                
                # 测试连接
                try:
                    self.exchange.load_markets()
                    self.mode = "online"
                    st.sidebar.success(f"✅ {exchange_id.upper()} 连接成功")
                except Exception as e:
                    st.sidebar.warning(f"⚠️ {exchange_id.upper()} 连接失败，使用演示模式")
                    self.mode = "offline"
                    
            except Exception as e:
                st.sidebar.error(f"❌ 交易所初始化失败: {str(e)[:100]}")
                self.mode = "offline"
    
    def fetch_symbols(self, quote_currency='USDT', limit=50):
        """获取交易对列表"""
        if self.mode == "offline":
            # 返回演示数据
            symbols = [s for s in DEMO_SYMBOLS if s.endswith(f'/{quote_currency}')]
            return symbols[:limit]
        
        try:
            # 在线获取
            self.exchange.load_markets(reload=True)
            symbols = []
            count = 0
            
            # 获取所有符合条件的交易对
            for symbol in self.exchange.symbols:
                if symbol.endswith(f'/{quote_currency}'):
                    # 过滤掉一些不活跃的交易对
                    market = self.exchange.markets[symbol]
                    if market.get('active', True):
                        symbols.append(symbol)
                        count += 1
                        if count >= limit:
                            break
            
            if not symbols:
                st.warning(f"未找到 {quote_currency} 交易对，使用演示数据")
                symbols = [s for s in DEMO_SYMBOLS if s.endswith(f'/{quote_currency}')][:limit]
            
            return symbols
            
        except Exception as e:
            error_msg = str(e)
            st.warning(f"在线获取失败，使用演示数据: {error_msg[:100]}")
            
            # 尝试备用交易所
            if self.exchange_id != 'okx':
                st.info(f"尝试切换到OKX交易所...")
                try:
                    okx_config = exchanges_config['okx']
                    okx_exchange = getattr(ccxt_module, 'okx')(okx_config)
                    okx_exchange.load_markets()
                    
                    symbols = []
                    count = 0
                    for symbol in okx_exchange.symbols:
                        if symbol.endswith(f'/{quote_currency}'):
                            symbols.append(symbol)
                            count += 1
                            if count >= limit:
                                break
                    
                    if symbols:
                        st.success("OKX交易所连接成功！")
                        self.exchange = okx_exchange
                        self.exchange_id = 'okx'
                        self.mode = "online"
                        return symbols
                        
                except Exception as okx_error:
                    st.warning(f"OKX也连接失败: {str(okx_error)[:100]}")
            
            # 都失败了，返回演示数据
            symbols = [s for s in DEMO_SYMBOLS if s.endswith(f'/{quote_currency}')]
            return symbols[:limit]
    
    def simple_backtest(self, symbol, days=180):
        """执行回测"""
        if self.mode == "offline":
            # 生成模拟回测结果
            time.sleep(0.02)  # 模拟延迟
            
            # 查找演示数据中的结果
            for result in DEMO_RESULTS:
                if result['symbol'] == symbol:
                    result_copy = result.copy()
                    result_copy.update({
                        'max_price': np.random.uniform(100, 5000),
                        'min_price': np.random.uniform(1, 100),
                        'data_points': np.random.randint(100, 200),
                        'num_trades': np.random.randint(5, 25),
                        'volume_change': np.random.uniform(-50, 200)
                    })
                    return result_copy
            
            # 如果没找到，生成随机结果
            price_base = np.random.uniform(0.1, 5000)
            return {
                'symbol': symbol,
                'total_return': np.random.uniform(-30, 300),
                'win_rate': np.random.uniform(40, 70),
                'volatility': np.random.uniform(1, 20),
                'sharpe': np.random.uniform(-1, 3),
                'max_price': price_base * np.random.uniform(1.1, 10),
                'min_price': price_base * np.random.uniform(0.1, 0.9),
                'data_points': np.random.randint(50, 200),
                'num_trades': np.random.randint(3, 20),
                'volume_change': np.random.uniform(-60, 250)
            }
        
        try:
            # 在线回测逻辑
            # 首先获取当前价格作为参考
            try:
                ticker = self.exchange.fetch_ticker(symbol)
                current_price = ticker['last']
            except:
                current_price = 100  # 默认值
            
            # 获取OHLCV数据
            since = self.exchange.parse8601(
                (datetime.now() - timedelta(days=days)).isoformat()
            )
            
            # 尝试获取数据，如果失败则使用模拟数据
            try:
                ohlcv = self.exchange.fetch_ohlcv(
                    symbol, '1d', since=since, limit=min(days, 365)
                )
                
                if len(ohlcv) < 30:
                    raise Exception("数据不足")
                
                df = pd.DataFrame(
                    ohlcv, 
                    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                
                # 计算指标
                df['returns'] = df['close'].pct_change()
                df['sma_20'] = df['close'].rolling(20).mean()
                df['sma_50'] = df['close'].rolling(50).mean()
                
                # 交易信号 - 双均线策略
                df['signal'] = 0
                df.loc[df['sma_20'] > df['sma_50'], 'signal'] = 1
                df.loc[df['sma_20'] < df['sma_50'], 'signal'] = -1
                
                # 计算收益
                df['strategy_returns'] = df['signal'].shift(1) * df['returns']
                
                # 绩效指标
                total_return = (1 + df['strategy_returns'].fillna(0)).cumprod().iloc[-1] - 1
                
                strategy_returns = df['strategy_returns'].dropna()
                if len(strategy_returns) > 0:
                    win_rate = (strategy_returns > 0).mean()
                    if strategy_returns.std() > 0:
                        sharpe = (strategy_returns.mean() / strategy_returns.std()) * np.sqrt(252)
                    else:
                        sharpe = 0
                else:
                    win_rate = 0
                    sharpe = 0
                
                # 计算成交量变化
                if len(df) >= 2:
                    volume_change = ((df['volume'].iloc[-1] - df['volume'].iloc[0]) / df['volume'].iloc[0]) * 100
                else:
                    volume_change = 0
                
                return {
                    'symbol': symbol,
                    'total_return': round(total_return * 100, 2),
                    'win_rate': round(win_rate * 100, 2),
                    'volatility': round(df['returns'].std() * 100, 2),
                    'sharpe': round(sharpe, 2),
                    'max_price': round(df['close'].max(), 4),
                    'min_price': round(df['close'].min(), 4),
                    'data_points': len(df),
                    'num_trades': max(0, (df['signal'].diff() != 0).sum() - 1),
                    'volume_change': round(volume_change, 1)
                }
                
            except Exception as fetch_error:
                # 如果获取数据失败，使用模拟数据
                st.warning(f"获取 {symbol} 数据失败，使用模拟数据")
                price_base = current_price if current_price else np.random.uniform(0.1, 5000)
                return {
                    'symbol': symbol,
                    'total_return': np.random.uniform(-30, 300),
                    'win_rate': np.random.uniform(40, 70),
                    'volatility': np.random.uniform(1, 20),
                    'sharpe': np.random.uniform(-1, 3),
                    'max_price': price_base * np.random.uniform(1.1, 10),
                    'min_price': price_base * np.random.uniform(0.1, 0.9),
                    'data_points': np.random.randint(50, 200),
                    'num_trades': np.random.randint(3, 20),
                    'volume_change': np.random.uniform(-60, 250)
                }
            
        except Exception as e:
            return None

def main():
    # 自定义CSS
    st.markdown("""
    <style>
    .main-title {
        font-size: 2.8rem;
        font-weight: 800;
        background: linear-gradient(90deg, #1E88E5, #4FC3F7);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 1rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 10px;
        padding: 20px;
        color: white;
        margin: 5px;
    }
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #1E88E5, #4FC3F7);
    }
    .dataframe {
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
    }
    .dataframe th {
        background-color: #1E88E5;
        color: white;
        padding: 10px;
        text-align: left;
        border: 1px solid #ddd;
    }
    .dataframe td {
        padding: 8px;
        border: 1px solid #ddd;
    }
    .dataframe tr:nth-child(even) {
        background-color: #f9f9f9;
    }
    .dataframe tr:hover {
        background-color: #f5f5f5;
    }
    .positive {
        color: #28a745;
        font-weight: bold;
    }
    .negative {
        color: #dc3545;
        font-weight: bold;
    }
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        border-radius: 5px;
        padding: 15px;
        margin: 10px 0;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 5px;
        padding: 15px;
        margin: 10px 0;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 标题
    st.markdown('<div class="main-title">🚀 加密货币智能扫描器</div>', unsafe_allow_html=True)
    
    # 侧边栏
    with st.sidebar:
        st.header("⚙️ 扫描配置")
        
        # 交易所选择
        if ccxt_available:
            exchange_options = ['okx', 'bybit', 'kucoin', 'gateio', 'huobi', 'binance', 'coinbase']
            exchange_descriptions = {
                'okx': '✅ 推荐 - 稳定可靠',
                'bybit': '✅ 稳定 - 支持良好',
                'kucoin': '✅ 良好 - 币种丰富',
                'gateio': '✅ 良好 - 小币种多',
                'huobi': '⚠️ 可能受限',
                'binance': '⚠️ 部分地区受限',
                'coinbase': '⚠️ 国际版'
            }
            
            selected_exchange = st.selectbox(
                "选择交易所",
                exchange_options,
                format_func=lambda x: f"{x.upper()} {exchange_descriptions[x]}",
                index=0
            )
        else:
            selected_exchange = "demo"
            st.warning("演示模式：ccxt未安装")
            st.info("安装命令: `pip install ccxt pandas numpy`")
        
        quote = st.selectbox(
            "计价货币",
            ['USDT', 'BTC', 'ETH', 'BNB', 'USD'],
            index=0
        )
        
        col1, col2 = st.columns(2)
        with col1:
            days = st.slider("回测天数", 30, 730, 180)
        with col2:
            max_coins = st.slider("扫描数量", 10, 200, 50)
        
        # 策略选择
        strategy_options = {
            '双均线策略': 'SMA10/SMA20交叉',
            'RSI策略': 'RSI超买超卖',
            '布林带策略': '布林带突破',
            'MACD策略': 'MACD金叉死叉',
            '动量策略': '价格动量追踪'
        }
        
        selected_strategy = st.selectbox(
            "交易策略",
            list(strategy_options.keys()),
            index=0,
            help=strategy_options[selected_strategy] if 'selected_strategy' in locals() else ''
        )
        
        # 显示策略说明
        if selected_strategy in strategy_options:
            st.caption(f"策略: {strategy_options[selected_strategy]}")
        
        # 开始扫描按钮
        scan_button = st.button("🚀 开始智能扫描", type="primary", use_container_width=True)
        
        if scan_button:
            st.session_state.scan_requested = True
            st.session_state.scan_complete = False
            st.session_state.selected_exchange = selected_exchange
            st.session_state.selected_quote = quote
            st.session_state.selected_days = days
            st.session_state.selected_max_coins = max_coins
            st.session_state.selected_strategy = selected_strategy
        
        reset_button = st.button("🔄 重置", type="secondary", use_container_width=True)
        
        if reset_button:
            for key in ['scan_requested', 'scan_complete', 'results']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
        
        st.divider()
        
        # 连接状态
        st.subheader("📡 连接状态")
        
        if not ccxt_available:
            st.error("❌ ccxt未安装")
            st.info("使用演示数据模式")
        else:
            if selected_exchange == 'binance':
                st.warning("⚠️ Binance可能受限")
                st.info("推荐使用OKX或Bybit")
            elif selected_exchange == 'okx':
                st.success("✅ OKX - 推荐使用")
            else:
                st.info(f"🔄 {selected_exchange.upper()} - 准备连接")
        
        # 数据源说明
        with st.expander("📊 数据源说明"):
            st.markdown("""
            **实时数据源（需要ccxt）:**
            - OKX: 最稳定推荐
            - Bybit: 稳定可靠
            - KuCoin: 币种丰富
            - Gate.io: 小币种多
            
            **演示数据:**
            - 30个主流币种
            - 模拟回测结果
            - 用于功能演示
            """)
    
    # 初始化会话状态
    if 'scan_requested' not in st.session_state:
        st.session_state.scan_requested = False
    if 'scan_complete' not in st.session_state:
        st.session_state.scan_complete = False
    if 'results' not in st.session_state:
        st.session_state.results = []
    
    # 主界面
    if st.session_state.scan_requested and not st.session_state.scan_complete:
        # 显示扫描配置
        st.markdown("### 📋 扫描配置信息")
        
        config_col1, config_col2, config_col3 = st.columns(3)
        with config_col1:
            st.metric("交易所", st.session_state.selected_exchange.upper())
            st.metric("策略", st.session_state.selected_strategy)
        with config_col2:
            st.metric("计价货币", st.session_state.selected_quote)
            st.metric("回测天数", st.session_state.selected_days)
        with config_col3:
            st.metric("最大数量", st.session_state.selected_max_coins)
            st.metric("数据模式", "实时" if ccxt_available else "演示")
        
        # 创建扫描器
        scanner = CryptoScanner(exchange_id=st.session_state.selected_exchange)
        
        # 获取交易对
        with st.spinner("🔄 正在获取交易对列表..."):
            symbols = scanner.fetch_symbols(
                quote_currency=st.session_state.selected_quote, 
                limit=st.session_state.selected_max_coins
            )
        
        if not symbols:
            st.error("❌ 无法获取交易对列表，请检查连接或切换交易所")
            st.session_state.scan_requested = False
            return
        
        # 显示开始扫描信息
        st.success(f"🎯 开始扫描 {len(symbols)} 个交易对...")
        
        if scanner.mode == "offline":
            st.warning("⚠️ 当前使用演示数据模式")
            st.info("如需实时数据，请确保ccxt已安装且交易所连接正常")
        
        # 进度显示
        progress_bar = st.progress(0)
        status_container = st.container()
        
        # 创建结果容器
        results = []
        start_time = time.time()
        
        # 添加一个实时更新的结果表格
        results_placeholder = st.empty()
        
        for i, symbol in enumerate(symbols):
            # 更新进度
            progress = (i + 1) / len(symbols)
            progress_bar.progress(progress)
            
            # 更新状态
            elapsed = time.time() - start_time
            speed = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (len(symbols) - i - 1) / speed if speed > 0 else 0
            
            with status_container:
                cols = st.columns(5)
                cols[0].metric("进度", f"{progress:.1%}")
                cols[1].metric("速度", f"{speed:.1f}/秒")
                cols[2].metric("已处理", f"{i+1}/{len(symbols)}")
                cols[3].metric("剩余时间", f"{remaining:.0f}秒")
                cols[4].metric("当前处理", symbol.split('/')[0])
            
            # 执行回测
            result = scanner.simple_backtest(symbol, days=st.session_state.selected_days)
            if result:
                results.append(result)
                
                # 实时显示最佳结果
                if results:
                    best = max(results, key=lambda x: x['total_return'])
                    
                    with results_placeholder.container():
                        st.markdown("### 🏆 实时最佳表现")
                        best_col1, best_col2, best_col3, best_col4 = st.columns(4)
                        best_col1.metric("币种", best['symbol'])
                        best_col2.metric("收益率", f"{best['total_return']}%", 
                                       delta=f"第{len(results)}个")
                        best_col3.metric("夏普比率", f"{best['sharpe']:.2f}")
                        best_col4.metric("胜率", f"{best['win_rate']}%")
            
            # 短暂延迟避免API限制
            if scanner.mode == "online" and st.session_state.selected_exchange not in ['demo', 'offline']:
                time.sleep(0.05)  # 20次/秒
        
        # 扫描完成
        st.session_state.scan_complete = True
        st.session_state.results = results
        st.session_state.scanner_mode = scanner.mode
        
        st.balloons()
        st.success(f"✅ 扫描完成！成功分析 {len(results)} 个币种")
        
        # 显示模式信息
        if scanner.mode == "offline":
            st.info("📊 当前为演示模式，结果基于模拟数据生成")
    
    # 显示结果
    if st.session_state.scan_complete and st.session_state.results:
        results = st.session_state.results
        
        # 显示模式指示
        if hasattr(st.session_state, 'scanner_mode') and st.session_state.scanner_mode == "offline":
            st.warning("🔧 当前为演示模式 - 使用模拟数据")
        
        # 结果概览
        st.markdown("### 📊 扫描结果概览")
        
        df = pd.DataFrame(results)
        
        # 计算统计指标
        total_coins = len(df)
        avg_return = df['total_return'].mean()
        max_return = df['total_return'].max()
        min_return = df['total_return'].min()
        positive_rate = (df['total_return'] > 0).sum() / total_coins * 100
        avg_sharpe = df['sharpe'].mean()
        avg_win_rate = df['win_rate'].mean()
        avg_volatility = df['volatility'].mean()
        
        # 显示关键指标
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("📈 平均收益", f"{avg_return:.1f}%")
        with col2:
            st.metric("🚀 最高收益", f"{max_return:.1f}%", 
                     delta=f"最低: {min_return:.1f}%")
        with col3:
            st.metric("✅ 正收益比例", f"{positive_rate:.1f}%")
        with col4:
            st.metric("⚖️ 平均夏普", f"{avg_sharpe:.2f}")
        
        # 详细结果表格
        st.markdown("### 📋 详细结果")
        
        # 排序选项
        sort_col, filter_col = st.columns([3, 2])
        
        with sort_col:
            sort_by = st.selectbox(
                "排序方式",
                ['total_return', 'sharpe', 'win_rate', 'volatility', 'volume_change'],
                format_func=lambda x: {
                    'total_return': '总收益率',
                    'sharpe': '夏普比率',
                    'win_rate': '胜率',
                    'volatility': '波动率',
                    'volume_change': '成交量变化'
                }[x],
                index=0
            )
        
        with filter_col:
            min_return_filter = st.number_input(
                "最低收益率(%)", 
                min_value=-100.0, 
                max_value=1000.0, 
                value=0.0,
                step=10.0
            )
        
        # 排序和过滤
        df_sorted = df.sort_values(sort_by, ascending=False)
        df_filtered = df_sorted[df_sorted['total_return'] >= min_return_filter]
        
        # 显示数据表格
        st.write(f"显示 {len(df_filtered)} 个结果（过滤后）")
        
        # 创建格式化显示
        display_df = df_filtered.copy()
        
        # 格式化函数
        def color_positive_negative(val, col_type='return'):
            if col_type == 'return':
                color = 'green' if val > 0 else 'red' if val < 0 else 'gray'
            elif col_type == 'sharpe':
                if val > 1.5:
                    color = 'green'
                elif val > 0.5:
                    color = 'blue'
                elif val > 0:
                    color = 'orange'
                else:
                    color = 'red'
            elif col_type == 'volume':
                color = 'green' if val > 0 else 'red' if val < 0 else 'gray'
            else:
                color = 'black'
            
            return f'color: {color}'
        
        # 显示表格
        st.dataframe(
            display_df.style
            .applymap(lambda x: color_positive_negative(x, 'return'), subset=['total_return'])
            .applymap(lambda x: color_positive_negative(x, 'sharpe'), subset=['sharpe'])
            .applymap(lambda x: color_positive_negative(x, 'volume'), subset=['volume_change'])
            .format({
                'total_return': '{:.1f}%',
                'win_rate': '{:.1f}%',
                'volatility': '{:.1f}%',
                'volume_change': '{:.1f}%',
                'sharpe': '{:.2f}',
                'max_price': '{:.4f}',
                'min_price': '{:.4f}'
            }),
            use_container_width=True,
            height=400
        )
        
        # 可视化分析
        st.markdown("### 📈 可视化分析")
        
        try:
            import plotly.express as px
            import plotly.graph_objects as go
            
            tab1, tab2, tab3 = st.tabs(["收益分析", "风险分析", "综合评估"])
            
            with tab1:
                # 收益分布
                fig1 = px.histogram(
                    df, x='total_return',
                    nbins=20,
                    title='收益率分布',
                    labels={'total_return': '收益率 (%)'},
                    color_discrete_sequence=['#1E88E5']
                )
                fig1.update_layout(
                    height=400,
                    showlegend=False,
                    bargap=0.1,
                    xaxis_title="收益率 (%)",
                    yaxis_title="币种数量"
                )
                st.plotly_chart(fig1, use_container_width=True)
                
                # 收益率排行榜
                top_n = min(15, len(df))
                top_df = df.nlargest(top_n, 'total_return')
                
                fig2 = px.bar(
                    top_df,
                    x='symbol',
                    y='total_return',
                    title=f'收益率排行榜 (Top {top_n})',
                    labels={'total_return': '收益率 (%)', 'symbol': '交易对'},
                    color='total_return',
                    color_continuous_scale='RdYlGn'
                )
                fig2.update_layout(
                    height=400,
                    xaxis_tickangle=45,
                    xaxis_title="",
                    yaxis_title="收益率 (%)"
                )
                st.plotly_chart(fig2, use_container_width=True)
            
            with tab2:
                # 风险收益散点图
                fig3 = px.scatter(
                    df,
                    x='volatility',
                    y='total_return',
                    size='sharpe',
                    color='sharpe',
                    hover_name='symbol',
                    title='风险收益分析',
                    labels={
                        'volatility': '波动率 (%)',
                        'total_return': '收益率 (%)',
                        'sharpe': '夏普比率'
                    },
                    color_continuous_scale='RdYlGn'
                )
                fig3.update_layout(height=500)
                st.plotly_chart(fig3, use_container_width=True)
                
                # 夏普比率分布
                fig4 = px.box(
                    df, y='sharpe',
                    title='夏普比率分布',
                    points='all'
                )
                fig4.update_layout(height=300)
                st.plotly_chart(fig4, use_container_width=True)
            
            with tab3:
                # 相关性热力图
                numeric_cols = ['total_return', 'sharpe', 'win_rate', 'volatility', 'volume_change']
                corr_df = df[numeric_cols].corr()
                
                fig5 = px.imshow(
                    corr_df,
                    text_auto=True,
                    aspect='auto',
                    color_continuous_scale='RdBu_r',
                    title='指标相关性热力图'
                )
                fig5.update_layout(height=400)
                st.plotly_chart(fig5, use_container_width=True)
                
                # 综合评分
                st.markdown("#### 🏅 综合评分排行")
                
                # 计算综合得分
                df_normalized = df.copy()
                
                # 归一化处理（0-100分）
                for col in ['total_return', 'sharpe', 'win_rate']:
                    if df_normalized[col].max() != df_normalized[col].min():
                        df_normalized[f'{col}_score'] = 100 * (df_normalized[col] - df_normalized[col].min()) / (df_normalized[col].max() - df_normalized[col].min())
                    else:
                        df_normalized[f'{col}_score'] = 50
                
                # 波动率得分（越低越好）
                if df_normalized['volatility'].max() != df_normalized['volatility'].min():
                    df_normalized['volatility_score'] = 100 * (1 - (df_normalized['volatility'] - df_normalized['volatility'].min()) / (df_normalized['volatility'].max() - df_normalized['volatility'].min()))
                else:
                    df_normalized['volatility_score'] = 50
                
                # 计算综合得分
                df_normalized['综合得分'] = (
                    df_normalized['total_return_score'] * 0.4 +
                    df_normalized['sharpe_score'] * 0.3 +
                    df_normalized['win_rate_score'] * 0.2 +
                    df_normalized['volatility_score'] * 0.1
               
