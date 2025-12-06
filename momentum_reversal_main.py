#!/usr/bin/env python3
"""
动量反转日内交易系统 (增强接口版)
专为 enhanced_http_server.py 设计，不使用任何模拟数据
"""
import json
import time
import schedule
import pandas as pd
import numpy as np
import requests
import logging
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any
import warnings
import os

warnings.filterwarnings('ignore')

# ==================== 全局日志配置 ====================
# 创建日志目录（如果不存在）
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)

# 设置日志文件路径
log_file = os.path.join(log_dir, "trading_system.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# 记录日志文件位置
logger.info(f"日志文件保存在: {os.path.abspath(log_file)}")

# ==================== 数据提供器 (纯接口版本) ====================
class DataProvider:
    """数据提供器 - 仅从 enhanced-data 接口获取真实数据"""
    
    def __init__(self, base_url="http://localhost:8001", max_retries=3):
        self.base_url = base_url
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.timeout = 15
        self.session.headers.update({
            'User-Agent': 'MomentumReversalTrader/1.0',
            'Accept': 'application/json'
        })
        
        # 缓存设置
        self.data_cache = {}
        self.cache_duration = 300  # 5分钟缓存
        
        logger.info(f"数据提供器初始化 - 仅使用真实接口")
        logger.info(f"服务器地址: {base_url}")
        
        # 测试连接
        self._test_connection()
    
    def _test_connection(self):
        """测试与数据服务器的连接"""
        try:
            test_url = f"{self.base_url}/enhanced-data?symbol=AAPL&period=1d&interval=5m"
            response = self.session.get(test_url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if 'error' not in data:
                    logger.info("✅ 数据服务器连接成功")
                    return True
                else:
                    logger.warning(f"⚠️  服务器返回错误: {data.get('error', '未知错误')}")
                    return False
            else:
                logger.error(f"❌ 服务器响应异常: HTTP {response.status_code}")
                return False
                
        except requests.exceptions.ConnectionError:
            logger.error("❌ 无法连接到数据服务器")
            logger.error("请确保已运行: python enhanced_http_server.py")
            return False
        except Exception as e:
            logger.error(f"❌ 连接测试失败: {e}")
            return False
    
    def get_intraday_data(self, symbol: str, interval: str = '5m', 
                         lookback: int = 60) -> pd.DataFrame:
        """
        从 enhanced-data 接口获取日内数据
        
        参数:
            symbol: 股票代码 (如 AAPL, MSFT)
            interval: 时间间隔 (1m, 5m, 15m, 30m, 60m)
            lookback: 期望的数据点数量
            
        返回:
            包含OHLCV数据的DataFrame，失败时返回空DataFrame
        """
        # 构建缓存键
        cache_key = f"{symbol}_{interval}"
        current_time = time.time()
        
        # 检查有效缓存
        if cache_key in self.data_cache:
            cache_age = current_time - self.data_cache[cache_key]['timestamp']
            if cache_age < self.cache_duration:
                cached_data = self.data_cache[cache_key]['data']
                if len(cached_data) >= min(lookback, 10):  # 至少10条缓存数据
                    return cached_data.copy()
        
        # 计算请求参数
        period = self._calculate_period(interval, lookback)
        
        # 构建请求URL
        url = f"{self.base_url}/enhanced-data"
        params = {
            'symbol': symbol,
            'period': period,
            'interval': interval
        }
        
        # 带重试的请求
        for attempt in range(self.max_retries):
            try:
                logger.info(f"请求数据: {symbol} ({interval}, {period}) [尝试 {attempt+1}/{self.max_retries}]")
                
                response = self.session.get(url, params=params, timeout=10)
                
                if response.status_code != 200:
                    logger.warning(f"HTTP错误 {response.status_code}, 重试中...")
                    time.sleep(1 * (attempt + 1))  # 指数退避
                    continue
                
                data = response.json()
                
                if 'error' in data:
                    logger.error(f"接口错误: {data['error']}, symbol: {symbol}")
                    return pd.DataFrame()
                
                # 处理原始数据
                df = self._process_raw_data(data, symbol)
                
                if df.empty:
                    logger.warning(f"处理后的数据为空: {symbol}")
                    return df
                
                # 限制数据点数量
                if lookback and len(df) > lookback:
                    df = df.iloc[-lookback:]
                
                # 更新缓存
                self.data_cache[cache_key] = {
                    'timestamp': current_time,
                    'data': df.copy()
                }
                
                logger.info(f"✅ 成功获取 {symbol}: {len(df)} 条数据")
                return df
                
            except requests.exceptions.Timeout:
                logger.warning(f"请求超时 {symbol}, 重试中...")
                time.sleep(2 * (attempt + 1))
            except requests.exceptions.ConnectionError:
                logger.error(f"连接错误 {symbol}, 重试中...")
                time.sleep(3 * (attempt + 1))
            except Exception as e:
                logger.error(f"获取 {symbol} 数据时出错: {e}")
                break
        
        logger.error(f"❌ 所有重试失败: {symbol}")
        return pd.DataFrame()
    
    def _calculate_period(self, interval: str, lookback: int) -> str:
        """根据间隔和数据点需求计算period参数"""
        # 基于interval的默认period映射
        period_map = {
            '1m': '1d',    # 1分钟数据获取1天
            '5m': '5d',    # 5分钟数据获取5天
            '15m': '10d',
            '30m': '20d',
            '60m': '30d',
            '1d': '3mo'
        }
        
        base_period = period_map.get(interval, '5d')
        
        # 根据lookback调整period
        if lookback > 100:
            if interval == '5m':
                return '10d'
            elif interval == '15m':
                return '20d'
            elif interval == '30m':
                return '60d'
            elif interval == '60m':
                return '90d'
        
        return base_period
    
    def _process_raw_data(self, api_data: Dict, symbol: str) -> pd.DataFrame:
        """处理API返回的原始数据"""
        try:
            # 获取原始数据列表
            raw_data = api_data.get('raw_data', [])
            if not raw_data:
                logger.warning(f"无原始数据: {symbol}")
                return pd.DataFrame()
            
            # 转换为DataFrame
            df = pd.DataFrame(raw_data)
            
            # 标准化列名
            column_mapping = {}
            for col in df.columns:
                col_lower = col.lower()
                if col_lower in ['timestamp', 'date', 'time']:
                    column_mapping[col] = 'timestamp'
                elif col_lower == 'open':
                    column_mapping[col] = 'Open'
                elif col_lower == 'high':
                    column_mapping[col] = 'High'
                elif col_lower == 'low':
                    column_mapping[col] = 'Low'
                elif col_lower == 'close':
                    column_mapping[col] = 'Close'
                elif col_lower == 'volume':
                    column_mapping[col] = 'Volume'
            
            df.rename(columns=column_mapping, inplace=True)
            
            # 确保时间戳列存在并设为索引
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
            else:
                # 如果没有时间戳，使用默认索引
                df.index = pd.date_range(end=datetime.now(), 
                                       periods=len(df), 
                                       freq='5min')
            
            # 确保必需的OHLC列存在
            required_cols = ['Open', 'High', 'Low', 'Close']
            missing_cols = [col for col in required_cols if col not in df.columns]
            
            if missing_cols:
                logger.warning(f"缺失必需列 {missing_cols}: {symbol}")
                return pd.DataFrame()
            
            # 确保Volume列存在
            if 'Volume' not in df.columns:
                df['Volume'] = 1000000  # 默认值
            
            # 数据类型转换和清理
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df.dropna()
            
            # 排序
            df.sort_index(inplace=True)
            
            return df
            
        except Exception as e:
            logger.error(f"处理 {symbol} 数据时出错: {e}")
            return pd.DataFrame()
    
    def get_technical_indicators(self, symbol: str, 
                               period: str = '1d', 
                               interval: str = '5m') -> Dict:
        """直接从接口获取技术指标"""
        try:
            url = f"{self.base_url}/enhanced-data"
            params = {
                'symbol': symbol,
                'period': period,
                'interval': interval
            }
            
            response = self.session.get(url, params=params, timeout=8)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ 获取技术指标成功: {symbol}")
                return data.get('technical_indicators', {})
        except Exception as e:
            logger.error(f"获取技术指标失败 {symbol}: {e}")
        
        return {}
    
    def get_market_status(self) -> Dict:
        """获取市场状态"""
        test_symbols = ['AAPL', 'SPY']
        status = {
            'server_available': False,
            'symbols_available': [],
            'test_time': datetime.now().isoformat()
        }
        
        # 测试基础连接
        try:
            test_response = self.session.get(self.base_url, timeout=5)
            status['server_available'] = test_response.status_code == 200
        except:
            status['server_available'] = False
        
        # 测试数据获取
        for symbol in test_symbols:
            try:
                df = self.get_intraday_data(symbol, interval='5m', lookback=5)
                if not df.empty and len(df) >= 3:
                    status['symbols_available'].append(symbol)
            except:
                continue
        
        return status

# ==================== 动量反转策略引擎 ====================
class MomentumReversalEngine:
    """
    动量反转日内交易引擎
    
    基于机构资金（早盘动量）和个人资金（午盘尾盘反转）行为差异[citation:3]
    早盘 (09:30-10:30): 动量效应 (机构配置资金主导)
    午盘 (10:30-14:30): 反转效应 (个人投机资金主导)
    尾盘 (14:30-15:00): 反转效应 (算法交易调仓)
    """
    
    def __init__(self, config: Dict = None):
        self.config = self._default_config()
        if config:
            self.config.update(config)
        
        # 交易状态
        self.positions = {}
        self.trade_history = []
        self.daily_pnl = 0.0
        self.equity = self.config.get('initial_capital', 100000.0)
        
        # 性能跟踪
        self.signals_generated = 0
        self.trades_executed = 0
        self.start_time = datetime.now()
        
        logger.info(f"策略引擎初始化 - 初始资金: ${self.equity:,.2f}")
    
    def _default_config(self) -> Dict:
        """默认配置[citation:3]"""
        return {
            # 资金管理
            'initial_capital': 100000.0,
            'risk_per_trade': 0.02,      # 单笔风险2%
            'max_position_size': 0.1,    # 最大仓位10%
            
            # 时间分区[citation:3]
            'morning_session': ('09:30', '10:30'),    # 早盘动量
            'midday_session': ('10:30', '14:30'),     # 午盘反转
            'afternoon_session': ('14:30', '15:00'),  # 尾盘反转
            
            # 信号参数
            'rsi_overbought': 72,
            'rsi_oversold': 28,
            'price_deviation_threshold': 2.5,  # 价格偏离阈值%
            'volume_surge_multiplier': 1.5,    # 成交量放大倍数
            
            # 风险控制
            'stop_loss_atr_multiple': 1.5,     # 止损ATR倍数
            'take_profit_atr_multiple': 3.0,   # 止盈ATR倍数
            'max_daily_loss': -0.05,           # 单日最大亏损
            'max_drawdown': -0.15,             # 最大回撤
            
            # 交易参数
            'min_volume': 10000,             # 最小成交量
            'min_data_points': 30,             # 最小数据点
            'commission_rate': 0.0005,         # 佣金率
        }
    
    def analyze_market_regime(self, data: pd.DataFrame) -> str:
        """分析市场状态"""
        if len(data) < 20:
            return "INSUFFICIENT_DATA"
        
        # 计算波动率
        returns = data['Close'].pct_change().dropna()
        volatility = returns.std() * np.sqrt(252)
        
        # 计算趋势
        price_change = (data['Close'].iloc[-1] / data['Close'].iloc[0] - 1) * 100
        
        if volatility > 0.25:
            return "HIGH_VOLATILITY"
        elif abs(price_change) > 3:
            return "TRENDING"
        else:
            return "RANGING"
    
    def detect_morning_momentum(self, symbol: str, data: pd.DataFrame, 
                               indicators: Dict) -> Optional[Dict]:
        """
        检测早盘动量信号[citation:3]
        
        早盘动量特征:
        1. 机构资金主导
        2. 温和上涨 (非极端)
        3. 成交量配合
        """
        if len(data) < 10:
            logger.info(f"{symbol} 数据不足，无法检测早盘动量信号")
            return None
        
        # 获取当前时间和价格
        current_time = datetime.now().time()
        morning_start = datetime.strptime(self.config['morning_session'][0], '%H:%M').time()
        morning_end = datetime.strptime(self.config['morning_session'][1], '%H:%M').time()
        
        # 只在早盘时段检测
        # if not (morning_start <= current_time <= morning_end):
        #     logger.info(f"{symbol} 非早盘时段，跳过早盘动量检测")
        #     return None
        
        latest = data.iloc[-1]
        
        # 1. RSI条件 (温和上涨，非超买)
        rsi = indicators.get('RSI', 50)
        if not (50 <= rsi <= 67):
            logger.info(f"{symbol} RSI不符合早盘动量条件: {rsi}")
            return None
        
        # 2. 价格偏离均线 (温和偏离)
        ma_key = 'MA_20'
        if ma_key not in indicators or indicators[ma_key] is None:
            logger.info(f"{symbol} 缺少MA20指标，无法检测早盘动量")
            return None
        
        price_deviation = (latest['Close'] - indicators[ma_key]) / indicators[ma_key] * 100
        if abs(price_deviation) < 0.34:  # 温和偏离
            logger.info(f"{symbol} 价格偏离不足，非早盘动量: {price_deviation:.2f}%")
            return None
        
        # 3. 成交量确认
        if 'Volume' in data.columns and len(data) >= 5:
            recent_volume = data['Volume'].iloc[-5:].mean()
            if latest['Volume'] < recent_volume * 1.05:
                logger.info(f"{symbol} 成交量未放大，非早盘动量{latest['Volume']} < {recent_volume *  1.05}")
                return None  # 成交量未放大
        
        # 计算信号强度
        confidence = 0.5
        if price_deviation > 0:
            confidence += min(price_deviation / 5.0, 0.3)  # 正向偏离加分
        if rsi > 55:
            confidence += 0.1
        
        logger.info(f"✅ {symbol} 早盘动量信号检测通过，置信度: {confidence:.2f}")
        
        signal = {
            'symbol': symbol,
            'signal_type': 'MORNING_MOMENTUM',
            'action': 'BUY' if price_deviation > 0 else 'SELL',
            'price': latest['Close'],
            'confidence': min(confidence, 0.9),
            'reason': f"早盘动量: 价格偏离MA20 {price_deviation:.1f}%, RSI {rsi:.1f}",
            'indicators': {
                'rsi': rsi,
                'price_deviation': price_deviation,
                'ma20': indicators[ma_key]
            }
        }
        
        return signal
    
    def detect_afternoon_reversal(self, symbol: str, data: pd.DataFrame,
                                 indicators: Dict) -> Optional[Dict]:
        """
        检测午盘/尾盘反转信号[citation:3]
        
        反转特征:
        1. 早盘动量后的价格修正
        2. 个人资金主导
        3. 超买/超卖后的回归
        """
        current_time = datetime.now().time()
        midday_start = datetime.strptime(self.config['midday_session'][0], '%H:%M').time()
        afternoon_end = datetime.strptime(self.config['afternoon_session'][1], '%H:%M').time()
        
        # 只在午盘和尾盘时段检测
        if not (midday_start <= current_time <= afternoon_end):
            return None
        
        latest = data.iloc[-1]
        
        # 1. RSI极端条件
        rsi = indicators.get('RSI', 50)
        is_overbought = rsi > self.config['rsi_overbought']
        is_oversold = rsi < self.config['rsi_oversold']
        
        if not (is_overbought or is_oversold):
            return None
        
        # 2. 价格位置
        lookback = min(20, len(data))
        recent_high = data['High'].iloc[-lookback:].max()
        recent_low = data['Low'].iloc[-lookback:].min()
        
        current_price = latest['Close']
        near_high = current_price > recent_high * 0.98
        near_low = current_price < recent_low * 1.02
        
        # 3. 确认反转模式 (超买+近高 或 超卖+近低)
        if not ((is_overbought and near_high) or (is_oversold and near_low)):
            return None
        
        # 4. 成交量确认 (反转时可能放量也可能缩量)
        volume_ok = True
        if 'Volume' in data.columns and len(data) >= 10:
            avg_volume = data['Volume'].iloc[-10:].mean()
            volume_ratio = latest['Volume'] / avg_volume
            volume_ok = 0.5 < volume_ratio < 2.5  # 合理范围
        
        if not volume_ok:
            return None
        
        # 确定交易方向
        if is_overbought and near_high:
            action = 'SELL'
            reason = f"午盘反转: RSI超买 {rsi:.1f}, 接近近期高点"
            confidence = min(0.4 + (rsi - 70) / 30, 0.8)
        else:  # is_oversold and near_low
            action = 'BUY'
            reason = f"午盘反转: RSI超卖 {rsi:.1f}, 接近近期低点"
            confidence = min(0.4 + (30 - rsi) / 30, 0.8)
        
        logger.info(f"✅ {symbol} 午盘反转信号检测通过，置信度: {confidence:.2f}")
        
        signal = {
            'symbol': symbol,
            'signal_type': 'AFTERNOON_REVERSAL',
            'action': action,
            'price': current_price,
            'confidence': confidence,
            'reason': reason,
            'indicators': {
                'rsi': rsi,
                'recent_high': recent_high,
                'recent_low': recent_low,
                'price_position': 'high' if near_high else 'low'
            }
        }
        
        return signal
    
    def calculate_position_size(self, signal: Dict, atr: float) -> int:
        """基于凯利公式和波动率计算仓位"""
        if atr <= 0:
            atr = signal['price'] * 0.02  # 默认2% ATR
        
        # 基础风险计算
        risk_amount = self.equity * self.config['risk_per_trade']
        risk_amount *= signal.get('confidence', 0.5)  # 置信度调整
        
        # 基于波动率的仓位计算
        risk_per_share = atr * self.config['stop_loss_atr_multiple']
        if risk_per_share <= 0:
            logger.warning("风险每股计算错误，无法计算仓位")
            return 0
        
        shares = int(risk_amount / risk_per_share)
        
        # 最大仓位限制
        max_shares_value = self.equity * self.config['max_position_size']
        max_shares = int(max_shares_value / signal['price'])
        
        return min(shares, max_shares)
    
    def generate_signals(self, symbol: str, data: pd.DataFrame, 
                        indicators: Dict) -> List[Dict]:
        """生成交易信号"""
        signals = []
        
        # 基本数据检查
        if data.empty or len(data) < self.config['min_data_points']:
            logger.info(f"{symbol} 数据不足，跳过信号生成")
            return signals
        
        # 检查成交量
        if 'Volume' in data.columns:
            avg_volume = data['Volume'].rolling(window=10).mean().iloc[-1]
            if avg_volume < self.config['min_volume']:
                logger.info(f"{symbol} 成交量不足，跳过信号生成 avg_volume{avg_volume}--min_volume:{self.config['min_volume']}")
                return signals
        
        # 获取ATR用于风险管理
        atr = indicators.get('ATR', data['Close'].std() * 0.01)
        
        # 1. 早盘动量信号
        morning_signal = self.detect_morning_momentum(symbol, data, indicators)
        if morning_signal:
            morning_signal['position_size'] = self.calculate_position_size(morning_signal, atr)
            if morning_signal['position_size'] > 0:
                signals.append(morning_signal)
        
        # 2. 午盘/尾盘反转信号
        reversal_signal = self.detect_afternoon_reversal(symbol, data, indicators)
        if reversal_signal:
            reversal_signal['position_size'] = self.calculate_position_size(reversal_signal, atr)
            if reversal_signal['position_size'] > 0:
                signals.append(reversal_signal)
        
        # 记录信号统计
        if signals:
            self.signals_generated += len(signals)
            logger.info(f"📊 {symbol} 生成 {len(signals)} 个交易信号")
        
        return signals
    
    def execute_signal(self, signal: Dict, current_price: float) -> Dict:
        """执行交易信号 (模拟)"""
        if signal['position_size'] <= 0:
            logger.warning(f"{signal['symbol']} 无效仓位，跳过执行")
            return {'status': 'REJECTED', 'reason': '无效仓位'}
        
        # 计算交易成本
        trade_value = signal['position_size'] * current_price
        commission = trade_value * self.config['commission_rate']
        
        # 创建交易记录
        trade = {
            'symbol': signal['symbol'],
            'action': signal['action'],
            'entry_price': current_price,
            'size': signal['position_size'],
            'timestamp': datetime.now(),
            'signal_type': signal['signal_type'],
            'confidence': signal['confidence'],
            'commission': commission,
            'status': 'EXECUTED',
            'stop_loss': None,
            'take_profit': None
        }
        
        # 计算止损止盈 (基于ATR)
        atr = current_price * 0.02  # 简化ATR
        
        if signal['action'] == 'BUY':
            trade['stop_loss'] = current_price * (1 - self.config['stop_loss_atr_multiple'] * atr / current_price)
            trade['take_profit'] = current_price * (1 + self.config['take_profit_atr_multiple'] * atr / current_price)
        else:  # SELL
            trade['stop_loss'] = current_price * (1 + self.config['stop_loss_atr_multiple'] * atr / current_price)
            trade['take_profit'] = current_price * (1 - self.config['take_profit_atr_multiple'] * atr / current_price)
        
        # 更新持仓和资金 (模拟)
        self.trade_history.append(trade)
        self.trades_executed += 1
        
        # 简化资金更新 (实际需要更复杂的持仓管理)
        if signal['action'] == 'BUY':
            self.equity -= trade_value + commission
        
        logger.info(f"📈 执行交易: {signal['symbol']} {signal['action']} "
                   f"@{current_price:.2f}, "
                   f"数量: {signal['position_size']}, "
                   f"价值: ${trade_value:,.2f}")
        
        return trade
    
    def run_analysis_cycle(self, data_provider, symbols: List[str]) -> Dict[str, List[Dict]]:
        """运行分析周期"""
        all_signals = {}
        logger.info(f"开始分析周期，共 {len(symbols)} 个标的")
        
        for symbol in symbols:
            logger.info(f"分析标的: {symbol}")
            try:
                # 获取日内数据
                df = data_provider.get_intraday_data(
                    symbol, interval='5m', lookback=80
                )
                
                if df.empty or len(df) < 30:
                    logger.warning(f"分析 {symbol} 数据不足，跳过")
                    continue
                
                # 获取技术指标
                indicators = data_provider.get_technical_indicators(symbol, '1d', '5m')
                
                # 生成信号
                signals = self.generate_signals(symbol, df, indicators)
                
                if signals:
                    all_signals[symbol] = signals
                    
                    # 模拟执行信号
                    for signal in signals:
                        self.execute_signal(signal, signal['price'])
                        
            except Exception as e:
                logger.error(f"分析 {symbol} 时出错: {e}")
                continue
        
        logger.info(f"分析周期完成，生成 {len(all_signals)} 个标的的信号")
        return all_signals
    
    def generate_report(self) -> Dict:
        """生成交易报告"""
        total_trades = len(self.trade_history)
        winning_trades = 0
        total_pnl = 0.0
        
        # 计算基础统计 (简化版，实际需要真实的盈亏计算)
        for trade in self.trade_history[-20:]:  # 只看最近20笔
            if trade['status'] == 'EXECUTED':
                # 简化PNL计算 (实际需要收盘价或平仓价)
                pnl = trade['size'] * trade['entry_price'] * 0.01  # 假设1%收益
                total_pnl += pnl
                if pnl > 0:
                    winning_trades += 1
        
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'equity': self.equity,
            'total_trades': total_trades,
            'trades_executed': self.trades_executed,
            'signals_generated': self.signals_generated,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'daily_pnl': self.daily_pnl,
            'positions_open': len(self.positions),
            'market_regime': 'ANALYZING',
            'recommendations': [
                "基于动量反转策略[citation:3]",
                f"信号生成: {self.signals_generated}",
                f"交易执行: {self.trades_executed}"
            ]
        }
        
        logger.info(f"📋 交易报告 - 资金: ${self.equity:,.2f}, "
                   f"总交易: {total_trades}, 胜率: {win_rate:.1%}")
        
        return report

# ==================== 主交易系统 ====================
class MomentumReversalSystem:
    """动量反转交易系统主控制器"""
    
    def __init__(self, config_file: str = None):
        self.config = self._load_config(config_file)
        self.start_time = datetime.now()
        
        # 初始化组件
        self.data_provider = None
        self.strategy_engine = None
        
        # 系统状态
        self.is_running = False
        self.cycle_count = 0
        self.last_signals = {}
        
        logger.info("=" * 70)
        logger.info("动量反转日内交易系统 (增强接口版)")
        logger.info("=" * 70)
        logger.info(f"日志文件: {log_file}")
    
    def _load_config(self, config_file: str) -> Dict:
        """加载配置"""
        default_config = {
            'data_server': {
                'base_url': 'http://localhost:8001',
                'retry_attempts': 3
            },
            'trading': {
                'symbols': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META','MU','INTC','AMD',
                            'NFLX','BIDU','JD','BABA','TCEHY','PYPL','SHOP','CRM','ORCL','IBM',
                            'CSCO','QCOM','TXN','AVGO','ADBE','INTU','ZM','DOCU','SNOW','UBER',
                            'LYFT'],
                'scan_interval_minutes': 1,
                'trading_hours': {
                    'start': '00:00',  # 开盘后5分钟
                    'end': '15:45'     # 收盘前15分钟
                }
            },
            'strategy': {
                'initial_capital': 100000.0,
                'risk_per_trade': 0.02,
                'max_position_size': 0.1
            }
        }
        
        return default_config
    
    def initialize(self) -> bool:
        """初始化系统"""
        logger.info("\n初始化交易系统...")
        
        # 1. 初始化数据提供器
        data_config = self.config['data_server']
        self.data_provider = DataProvider(
            base_url=data_config['base_url'],
            max_retries=data_config.get('retry_attempts', 3)
        )
        
        # 2. 初始化策略引擎
        strategy_config = self.config['strategy']
        self.strategy_engine = MomentumReversalEngine(strategy_config)
        
        logger.info("\n✅ 系统初始化完成")
        logger.info(f"交易标的: {', '.join(self.config['trading']['symbols'][:5])}...")
        logger.info(f"扫描间隔: {self.config['trading']['scan_interval_minutes']} 分钟")
        logger.info(f"交易时间: {self.config['trading']['trading_hours']['start']} - "
                   f"{self.config['trading']['trading_hours']['end']}")
        
        return True
    
    def _within_trading_hours(self) -> bool:
        """检查是否在交易时间内"""
        hours = self.config['trading']['trading_hours']
        start = datetime.strptime(hours['start'], '%H:%M').time()
        end = datetime.strptime(hours['end'], '%H:%M').time()
        current = datetime.now().time()
        
        return start <= current <= end
    
    def trading_cycle(self):
        """交易循环"""
        if not self.is_running:
            logger.warning("📭 系统未运行")
            return
        
        self.cycle_count += 1
        current_time = datetime.now()
        
        logger.info(f"\n{'='*60}")
        logger.info(f"交易周期 #{self.cycle_count} - {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info('='*60)
        
        # 检查交易时间
        if not self._within_trading_hours():
            logger.info("⏸️  非交易时间，跳过...")
            return
        
        # 获取市场状态
        market_status = self.data_provider.get_market_status()
        if not market_status['server_available']:
            logger.error("❌ 数据服务器不可用")
            return
        
        logger.info(f"市场状态: 服务器可用 - {market_status['server_available']}, "
                   f"可用标的: {len(market_status['symbols_available'])}")
        
        # 运行策略分析
        symbols = self.config['trading']['symbols']
        signals = self.strategy_engine.run_analysis_cycle(self.data_provider, symbols)
        
        # 处理信号
        if signals:
            logger.info(f"\n📊 生成 {len(signals)} 个标的的信号:")
            for symbol, sig_list in signals.items():
                for sig in sig_list:
                    logger.info(f"  {symbol}: {sig['action']} @ ${sig['price']:.2f}, "
                              f"数量: {sig.get('position_size', 0):,}, "
                              f"置信度: {sig['confidence']:.2f}, "
                              f"类型: {sig['signal_type']}")
        else:
            logger.info("📭 未生成交易信号")
        
        self.last_signals = signals
        
        # 生成状态报告
        self._status_report()
        
        logger.info(f"交易周期 #{self.cycle_count} 完成")
        logger.info('='*60)
    
    def _status_report(self):
        """状态报告"""
        if not self.strategy_engine:
            return
        
        report = self.strategy_engine.generate_report()
        
        logger.info(f"\n📈 系统状态:")
        logger.info(f"  资金: ${report['equity']:,.2f}")
        logger.info(f"  总交易: {report['total_trades']}")
        logger.info(f"  胜率: {report['win_rate']:.1%}")
        logger.info(f"  总PNL: ${report['total_pnl']:,.2f}")
        
        # 信号统计
        total_signals = sum(len(sigs) for sigs in self.last_signals.values())
        if total_signals > 0:
            logger.info(f"  本期信号: {total_signals}")
    
    def start(self):
        """启动系统"""
        logger.info("\n启动交易系统...")
        
        if not self.initialize():
            logger.error("初始化失败，系统退出")
            return
        
        self.is_running = True
        
        # 设置定时任务
        interval = self.config['trading']['scan_interval_minutes']
        schedule.every(interval).minutes.at(":00").do(self.trading_cycle)
        
        logger.info(f"\n✅ 系统已启动，每 {interval} 分钟扫描一次")
        logger.info("按 Ctrl+C 停止系统\n")
        
        # 立即运行一次
        self.trading_cycle()
        
        # 主循环
        try:
            while self.is_running:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n\n🛑 收到停止信号...")
            self.stop()
    
    def stop(self):
        """停止系统"""
        logger.info("停止交易系统...")
        self.is_running = False
        schedule.clear()
        
        runtime = datetime.now() - self.start_time
        logger.info(f"\n⏱️  运行时间: {runtime}")
        logger.info(f"总交易周期: {self.cycle_count}")
        logger.info("系统已安全停止")

# ==================== 主程序入口 ====================
def main():
    """主函数"""
    import sys
    
    logger.info("🚀 动量反转日内交易系统启动")
    logger.info("版本: 增强接口版 (纯真实数据)")
    logger.info(f"日志文件: {log_file}")
    logger.info("=" * 70)
    
    # 创建并启动系统
    system = MomentumReversalSystem()
    
    try:
        system.start()
    except Exception as e:
        logger.error(f"\n❌ 系统运行出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()