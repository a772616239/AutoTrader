import pandas as pd
import numpy as np
from datetime import time, datetime

class ShortTermStrategyEngine:
    def __init__(self, initial_capital=100000.0):
        self.initial_capital = initial_capital
        self.position = 0  # 当前持仓数量
        self.cash = initial_capital  # 现金
        self.orders = []  # 交易记录
        
    def fetch_intraday_data(self, symbol, interval='5m', period='1d'):
        """
        从你的增强数据服务器获取日内数据
        返回 pandas DataFrame
        """
        import requests
        import pandas as pd
        from io import StringIO
        
        try:
            # 调用本地增强数据API
            url = f"http://localhost:8001/enhanced-data"
            params = {
                'symbol': symbol,
                'period': period,
                'interval': interval
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if 'error' in data:
                print(f"获取 {symbol} 数据失败: {data['error']}")
                # 返回一个空的DataFrame，避免后续错误
                return pd.DataFrame()
            
            # 从增强数据中提取原始行情列表
            raw_data_list = data.get('raw_data', [])
            if not raw_data_list:
                print(f"未找到 {symbol} 的原始数据")
                return pd.DataFrame()
            
            # 将列表转换为DataFrame
            df = pd.DataFrame(raw_data_list)
            
            # 确保列名正确，并设置时间索引
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
            
            # 确保必需的列存在（Open, High, Low, Close, Volume）
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            # 转换列名为首字母大写以匹配策略中的引用方式
            column_mapping = {}
            for col in df.columns:
                if col.lower() in required_cols:
                    column_mapping[col] = col.lower().capitalize()
            
            df.rename(columns=column_mapping, inplace=True)
            
            print(f"成功获取 {symbol} 数据: {len(df)} 条, 周期 {interval}")
            return df
            
        except requests.exceptions.ConnectionError:
            print(f"无法连接到数据服务器，请确保 enhanced_http_server.py 正在运行")
            # 返回模拟数据供测试（没有服务器时使用）
            return self._generate_mock_data(symbol, interval)
        except Exception as e:
            print(f"获取数据时发生错误: {e}")
            return pd.DataFrame()

    def _generate_mock_data(self, symbol, interval):
        """
        生成模拟日内数据（仅用于测试，无真实服务器时）
        """
        import pandas as pd
        import numpy as np
        from datetime import datetime, timedelta
        
        print(f"为 {symbol} 生成模拟数据用于测试")
        
        # 生成最近24小时的模拟数据
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=24)
        
        if interval == '5m':
            periods = 288  # 24小时 * 12个5分钟
        elif interval == '15m':
            periods = 96
        elif interval == '1h':
            periods = 24
        else:
            periods = 100
        
        dates = pd.date_range(start=start_time, periods=periods, freq=interval)
        
        # 生成随机价格数据（基于正态随机游走）
        np.random.seed(42)  # 固定种子使结果可重现
        base_price = 150 if symbol == 'AAPL' else 300 if symbol == 'MSFT' else 100
        returns = np.random.randn(periods) * 0.002  # 日波动率约3%
        prices = base_price * (1 + returns).cumprod()
        
        # 生成OHLCV数据
        df = pd.DataFrame(index=dates)
        df['Close'] = prices
        df['Open'] = prices * (1 + np.random.randn(periods) * 0.001)
        df['High'] = df[['Open', 'Close']].max(axis=1) * (1 + abs(np.random.randn(periods) * 0.0015))
        df['Low'] = df[['Open', 'Close']].min(axis=1) * (1 - abs(np.random.randn(periods) * 0.0015))
        df['Volume'] = np.random.randint(1000000, 5000000, size=periods)
        
        # 确保 High >= Low
        df['High'] = df[['High', 'Low']].max(axis=1)
        df['Low'] = df[['High', 'Low']].min(axis=1)
        
        return df
        
    def momentum_breakout_strategy(self, intraday_data, indicators):
        """
        日内动量突破策略
        逻辑：结合价格突破、成交量放大和RSI强度
        """
        signals = []
        latest = intraday_data.iloc[-1]
        prev = intraday_data.iloc[-2] if len(intraday_data) > 1 else latest
        
        # 条件1: 价格突破 - 当前价创N分钟新高
        lookback = min(20, len(intraday_data))
        recent_high = intraday_data['High'][-lookback:-1].max()
        price_breakout = latest['Close'] > recent_high
        
        # 条件2: 成交量显著放大（超过均量50%）
        avg_volume = intraday_data['Volume'][-lookback:-1].mean()
        volume_surge = latest['Volume'] > avg_volume * 1.5
        
        # 条件3: RSI处于强势区但非极端超买
        rsi = indicators.get('RSI', 50)
        rsi_ok = 55 < rsi < 75
        
        # 条件4: 日内趋势 - 价格位于VWAP之上
        vwap = self.calculate_vwap(intraday_data)
        above_vwap = latest['Close'] > vwap
        
        # 综合信号生成
        if price_breakout and volume_surge and rsi_ok and above_vwap:
            # 计算风险调整后的头寸
            atr = indicators.get('ATR', 0)
            if atr > 0:
                # 基于ATR计算止损幅度， 确保单笔损失不超过资本的1%
                risk_per_share = atr * 1.5  # 止损设在1.5倍ATR外
                risk_capital = self.cash * 0.01  # 愿意冒险的资金
                position_size = int(risk_capital / risk_per_share)
                
                signals.append({
                    'action': 'BUY',
                    'price': latest['Close'],
                    'size': position_size,
                    'reason': f'动量突破: 价格创新高{recent_high:.2f}, 量增{latest["Volume"]/avg_volume:.1f}倍, RSI:{rsi:.1f}',
                    'stop_loss': latest['Close'] - risk_per_share,
                    'take_profit': latest['Close'] + (2 * risk_per_share)  # 盈亏比2:1
                })
        
        # 持仓管理：止损或止盈检查
        if self.position > 0:
            latest_low = latest['Low']
            # 检查是否触及止损（这里需要访问你的持仓成本记录，简化处理）
            # 实际中需要跟踪每笔交易的成本价
            
        return signals
    
    def mean_reversion_strategy(self, intraday_data, indicators):
        """
        均值回归策略（与动量策略形成互补）
        逻辑：在价格过度偏离均线且RSI超卖时买入
        """
        signals = []
        latest = intraday_data.iloc[-1]
        
        # 计算价格与均线的偏离度
        ma20 = indicators.get('MA_20', latest['Close'])
        deviation = (latest['Close'] - ma20) / ma20 * 100
        
        # 条件：价格显著低于均线且RSI超卖
        if deviation < -3 and indicators.get('RSI', 50) < 35:
            # 成交量确认：下跌缩量或开始放量
            lookback = min(10, len(intraday_data))
            avg_volume = intraday_data['Volume'][-lookback:-1].mean()
            
            signals.append({
                'action': 'BUY',
                'price': latest['Close'],
                'size': int(self.cash * 0.1 / latest['Close']),  # 使用10%资金
                'reason': f'均值回归: 价格低于20日均线{abs(deviation):.1f}%, RSI超卖{indicators.get("RSI", 0):.1f}',
                'stop_loss': latest['Close'] * 0.95,  # 5%止损
                'take_profit': latest['Close'] * 1.08  # 8%止盈
            })
        
        return signals
    
    def calculate_vwap(self, intraday_data):
        """计算成交量加权平均价（VWAP），重要的日内基准"""
        if len(intraday_data) == 0:
            return 0
        typical_price = (intraday_data['High'] + intraday_data['Low'] + intraday_data['Close']) / 3
        vwap = (typical_price * intraday_data['Volume']).sum() / intraday_data['Volume'].sum()
        return vwap
    
    def execute_order(self, order, current_price):
        """模拟订单执行"""
        cost = order['size'] * current_price
        if order['action'] == 'BUY' and self.cash >= cost:
            self.cash -= cost
            self.position += order['size']
            order['executed_price'] = current_price
            order['timestamp'] = datetime.now()
            self.orders.append(order)
            print(f"执行买入: {order['size']}股, 价格:{current_price:.2f}, 理由:{order['reason']}")
            
    def run_daily_simulation(self, symbol, date):
        """
        模拟单日交易
        """
        print(f"\n=== {date} {symbol} 日内交易模拟 ===")
        
        # 1. 获取日内数据
        intraday_data = self.fetch_intraday_data(symbol, interval='5m', period='1d')
        
        if intraday_data.empty or len(intraday_data) < 30:
            print(f"数据不足（仅{len(intraday_data)}条），跳过{symbol}今日交易")
            return
        
        # 2. 计算技术指标（如果服务器已提供，可跳过此步）
        # 这里假设增强服务器已返回技术指标，直接从API获取
        import requests
        try:
            response = requests.get(
                f"http://localhost:8001/enhanced-data",
                params={'symbol': symbol, 'period':'1d', 'interval':'5m'},
                timeout=5
            )
            enhanced_data = response.json()
            indicators = enhanced_data.get('technical_indicators', {})
        except:
            # 如果无法获取增强数据，计算基础指标
            print(f"无法获取{symbol}增强数据，将计算基础指标")
            indicators = self.calculate_basic_indicators(intraday_data)
        
        # 3. 运行多个策略
        all_signals = []
        all_signals.extend(self.momentum_breakout_strategy(intraday_data, indicators))
        all_signals.extend(self.mean_reversion_strategy(intraday_data, indicators))

        
        # 4. 信号过滤与排序（避免过度交易）
        if all_signals:
            # 按信心度排序（这里简化，实际可根据更多因子评分）
            sorted_signals = sorted(all_signals, 
                                   key=lambda x: abs(x.get('size', 0)), 
                                   reverse=True)
            
            # 每日最多执行2笔交易
            for signal in sorted_signals[:2]:
                self.execute_order(signal, signal['price'])
        
        # 5. 收盘前平仓（日内策略不过夜）
        self.close_all_positions(intraday_data.iloc[-1]['Close'])
        
        print(f"交易日结束，现金: {self.cash:.2f}, 总资产: {self.cash + self.position * intraday_data.iloc[-1]['Close']:.2f}")
    
    def close_all_positions(self, close_price):
        """收盘前平仓所有头寸"""
        if self.position > 0:
            value = self.position * close_price
            self.cash += value
            print(f"平仓: {self.position}股, 价格:{close_price:.2f}, 释放资金:{value:.2f}")
            self.position = 0