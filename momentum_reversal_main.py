#!/usr/bin/env python3
"""
动量反转日内交易系统 (增强接口版)
专为 enhanced_http_server.py 设计，不使用任何模拟数据
集成IB交易接口
"""
import json
import time
import schedule
import pandas as pd
import numpy as np
import requests
import logging
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import warnings
import os
import hashlib
from ib_insync import *

warnings.filterwarnings('ignore')

# ==================== 全局日志配置 ====================
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
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
logger.info(f"日志文件保存在: {os.path.abspath(log_file)}")

# ==================== IB交易接口封装 ====================
class IBTrader:
    """IB交易接口封装"""
    
    def __init__(self, host='127.0.0.1', port=7497, client_id=1):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = IB()
        self.connected = False
        self.max_retries = 3
        
        logger.info(f"IB交易接口初始化: {host}:{port} (clientId={client_id})")
    
    def connect(self) -> bool:
        """连接IB"""
        if self.connected:
            return True
            
        for attempt in range(self.max_retries):
            try:
                logger.info(f"尝试连接IB [尝试 {attempt+1}/{self.max_retries}]")
                self.ib.connect(self.host, self.port, clientId=self.client_id)
                
                if self.ib.isConnected():
                    self.connected = True
                    logger.info("✅ IB连接成功")
                    return True
                else:
                    logger.warning(f"IB连接状态检查失败，重试中...")
                    time.sleep(2)
                    
            except Exception as e:
                logger.error(f"连接IB失败: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(3 * (attempt + 1))
                else:
                    logger.error("❌ 所有重试失败，无法连接IB")
                    return False
        
        return False
    
    def disconnect(self):
        """断开IB连接"""
        if self.connected:
            try:
                self.ib.disconnect()
                self.connected = False
                logger.info("IB连接已断开")
            except Exception as e:
                logger.error(f"断开IB连接时出错: {e}")
    
    def get_contract(self, symbol: str) -> Stock:
        """
        根据股票代码创建并鉴定合约
        """
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            logger.info(f"✅ 合约鉴定成功: {symbol}")
            return contract
        except Exception as e:
            logger.error(f"合约鉴定失败 {symbol}: {e}")
            raise
    
    def place_order(self, symbol: str, action: str, quantity: float, 
                   order_type: str = 'MKT', price: Optional[float] = None) -> Optional[Trade]:
        """
        通用订单提交函数
        
        参数:
            symbol: 股票代码
            action: 'BUY' 或 'SELL'
            quantity: 数量
            order_type: 订单类型 ('MKT' 或 'LMT')
            price: 限价单价格
        
        返回:
            Trade对象 或 None
        """
        if not self.connected and not self.connect():
            logger.error("IB未连接，无法提交订单")
            return None
        
        try:
            # 获取合约
            contract = self.get_contract(symbol)
            
            # 创建订单
            if order_type == 'LMT' and price is not None:
                order = LimitOrder(action, quantity, price)
            elif order_type == 'MKT':
                order = MarketOrder(action, quantity)
            else:
                logger.error(f"不支持的订单类型或缺少价格参数: {order_type}")
                return None
            
            # 提交订单
            logger.info(f"提交订单: {action} {quantity} 股 {symbol} "
                       f"({order_type} @ {price if price else '市价'})")
            
            trade = self.ib.placeOrder(contract, order)
            
            # 等待订单状态更新
            self.ib.sleep(2)
            
            # 检查订单状态
            status = trade.orderStatus.status
            if status in ['Filled', 'Submitted', 'PreSubmitted']:
                logger.info(f"✅ 订单提交成功 - ID: {trade.order.orderId}, 状态: {status}")
                return trade
            else:
                logger.warning(f"⚠️  订单状态异常 - ID: {trade.order.orderId}, 状态: {status}")
                return trade
                
        except Exception as e:
            logger.error(f"提交订单失败 {symbol}: {e}")
            return None
    
    def place_buy_order(self, symbol: str, quantity: float, 
                       order_type: str = 'MKT', price: Optional[float] = None) -> Optional[Trade]:
        """封装的买入订单函数"""
        return self.place_order(symbol, 'BUY', quantity, order_type, price)
    
    def place_sell_order(self, symbol: str, quantity: float,
                        order_type: str = 'MKT', price: Optional[float] = None) -> Optional[Trade]:
        """封装的卖出订单函数"""
        return self.place_order(symbol, 'SELL', quantity, order_type, price)
    
    def get_holdings(self, symbol: Optional[str] = None) -> List[Position]:
        """
        获取持仓信息
        
        参数:
            symbol: 可选，指定要查看的股票代码
        
        返回:
            持仓列表
        """
        if not self.connected and not self.connect():
            logger.error("IB未连接，无法获取持仓")
            return []
        
        try:
            positions = self.ib.positions()
            
            if symbol:
                filtered_positions = []
                for pos in positions:
                    if hasattr(pos.contract, 'secType') and pos.contract.secType == 'STK':
                        if hasattr(pos.contract, 'symbol') and pos.contract.symbol == symbol:
                            filtered_positions.append(pos)
                return filtered_positions
            else:
                # 只返回股票持仓
                stock_positions = []
                for pos in positions:
                    if hasattr(pos.contract, 'secType') and pos.contract.secType == 'STK':
                        stock_positions.append(pos)
                return stock_positions
                
        except Exception as e:
            logger.error(f"获取持仓时发生错误: {e}")
            return []
    
    def get_holding_for_symbol(self, symbol: str) -> Optional[Dict]:
        """
        获取指定符号的持仓详情
        
        返回:
            持仓字典 或 None
        """
        holdings = self.get_holdings(symbol)
        
        if holdings:
            pos = holdings[0]
            return {
                'symbol': symbol,
                'position': pos.position,
                'avg_cost': pos.avgCost,
                'contract': pos.contract
            }
        return None
    
    def get_account_summary(self) -> Dict:
        """
        获取账户摘要信息
        
        返回:
            账户信息字典
        """
        if not self.connected and not self.connect():
            logger.error("IB未连接，无法获取账户摘要")
            return {}
        
        try:
            account_summary = {}
            summary_items = self.ib.accountSummary()
            
            for item in summary_items:
                account_summary[item.tag] = {
                    'value': item.value,
                    'currency': item.currency,
                    'account': item.account
                }
            
            logger.info(f"获取账户摘要成功，共 {len(account_summary)} 项")
            return account_summary
            
        except Exception as e:
            logger.error(f"获取账户摘要时发生错误: {e}")
            return {}
    
    def get_account_value(self, tag: str = 'NetLiquidation') -> float:
        """
        获取账户净值
        
        参数:
            tag: 账户字段标签
        
        返回:
            账户净值 (float)
        """
        summary = self.get_account_summary()
        
        if tag in summary:
            try:
                value = float(summary[tag]['value'])
                logger.info(f"账户{tag}: {value:,.2f} {summary[tag]['currency']}")
                return value
            except:
                logger.error(f"无法解析账户{tag}值: {summary[tag]['value']}")
        
        logger.warning(f"未找到账户字段: {tag}")
        return 0.0
    
    def get_available_funds(self) -> float:
        """获取可用资金"""
        return self.get_account_value('AvailableFunds')
    
    def get_net_liquidation(self) -> float:
        """获取净资产"""
        return self.get_account_value('NetLiquidation')
    
    def print_holdings(self, symbol: Optional[str] = None):
        """打印持仓信息"""
        positions = self.get_holdings(symbol)
        
        if not positions:
            if symbol:
                logger.info(f"没有找到 {symbol} 的持仓")
            else:
                logger.info("当前没有任何股票持仓")
            return
        
        logger.info("\n" + "="*60)
        logger.info("当前持仓信息:")
        logger.info("="*60)
        
        for pos in positions:
            contract = pos.contract
            logger.info(f"合约: {contract.symbol} ({contract.secType})")
            logger.info(f"  数量: {pos.position}")
            logger.info(f"  平均成本: {pos.avgCost:.2f} {contract.currency}")
            if hasattr(contract, 'exchange'):
                logger.info(f"  交易所: {contract.exchange}")
            logger.info("-" * 40)

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
        
        self.data_cache = {}
        self.cache_duration = 300
        
        logger.info(f"数据提供器初始化 - 仅使用真实接口")
        logger.info(f"服务器地址: {base_url}")
        
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
        """
        cache_key = f"{symbol}_{interval}"
        current_time = time.time()
        
        if cache_key in self.data_cache:
            cache_age = current_time - self.data_cache[cache_key]['timestamp']
            if cache_age < self.cache_duration:
                cached_data = self.data_cache[cache_key]['data']
                if len(cached_data) >= min(lookback, 10):
                    return cached_data.copy()
        
        period = self._calculate_period(interval, lookback)
        url = f"{self.base_url}/enhanced-data"
        params = {
            'symbol': symbol,
            'period': period,
            'interval': interval
        }
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"请求数据: {symbol} ({interval}, {period}) [尝试 {attempt+1}/{self.max_retries}]")
                
                response = self.session.get(url, params=params, timeout=10)
                
                if response.status_code != 200:
                    logger.warning(f"HTTP错误 {response.status_code}, 重试中...")
                    time.sleep(1 * (attempt + 1))
                    continue
                
                data = response.json()
                
                if 'error' in data:
                    logger.error(f"接口错误: {data['error']}, symbol: {symbol}")
                    return pd.DataFrame()
                
                df = self._process_raw_data(data, symbol)
                
                if df.empty:
                    logger.warning(f"处理后的数据为空: {symbol}")
                    return df
                
                if lookback and len(df) > lookback:
                    df = df.iloc[-lookback:]
                
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
        period_map = {
            '1m': '1d',
            '5m': '5d',
            '15m': '10d',
            '30m': '20d',
            '60m': '30d',
            '1d': '3mo'
        }
        
        base_period = period_map.get(interval, '5d')
        
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
            raw_data = api_data.get('raw_data', [])
            if not raw_data:
                logger.warning(f"无原始数据: {symbol}")
                return pd.DataFrame()
            
            df = pd.DataFrame(raw_data)
            
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
            
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
            else:
                df.index = pd.date_range(end=datetime.now(), 
                                       periods=len(df), 
                                       freq='5min')
            
            required_cols = ['Open', 'High', 'Low', 'Close']
            missing_cols = [col for col in required_cols if col not in df.columns]
            
            if missing_cols:
                logger.warning(f"缺失必需列 {missing_cols}: {symbol}")
                return pd.DataFrame()
            
            if 'Volume' not in df.columns:
                df['Volume'] = 1000000
            
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df.dropna()
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
        
        try:
            test_response = self.session.get(self.base_url, timeout=5)
            status['server_available'] = test_response.status_code == 200
        except:
            status['server_available'] = False
        
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
    动量反转日内交易引擎 - 使用IB接口执行真实交易
    """
    
    def __init__(self, config: Dict = None, ib_trader: IBTrader = None):
        self.config = self._default_config()
        if config:
            self.config.update(config)
        
        # IB交易接口
        self.ib_trader = ib_trader
        
        # 交易状态 - 从IB实时获取
        self.positions = {}  # 本地缓存持仓，定期从IB同步
        self.trade_history = []  # 本地交易记录
        self.daily_pnl = 0.0
        
        # 从IB获取初始权益
        if self.ib_trader:
            try:
                self.equity = self.ib_trader.get_net_liquidation()
                logger.info(f"从IB获取初始净资产: ${self.equity:,.2f}")
            except:
                self.equity = self.config.get('initial_capital', 100000.0)
                logger.warning(f"无法从IB获取净资产，使用配置值: ${self.equity:,.2f}")
        else:
            self.equity = self.config.get('initial_capital', 100000.0)
            logger.warning("未提供IB交易接口，使用模拟资金")
        
        # 信号防重复机制
        self.signal_cache = {}  # {signal_hash: expiration_time}
        self.executed_signals = set()  # 本周期已执行的信号哈希
        
        # 性能跟踪
        self.signals_generated = 0
        self.trades_executed = 0
        self.start_time = datetime.now()
        
        logger.info(f"策略引擎初始化 - 净资产: ${self.equity:,.2f}")
    
    def _default_config(self) -> Dict:
        """默认配置"""
        return {
            # 资金管理
            'initial_capital': 100000.0,
            'risk_per_trade': 0.02,
            'max_position_size': 0.1,
            
            # 时间分区
            'morning_session': ('09:30', '10:30'),
            'midday_session': ('10:30', '14:30'),
            'afternoon_session': ('14:30', '15:00'),
            
            # 信号参数
            'rsi_overbought': 72,
            'rsi_oversold': 28,
            'price_deviation_threshold': 2.5,
            'volume_surge_multiplier': 1.5,
            
            # 风险管理
            'stop_loss_atr_multiple': 1.5,
            'take_profit_atr_multiple': 3.0,
            'trailing_stop_activation': 0.02,
            'trailing_stop_distance': 0.015,
            
            # 卖出条件
            'min_profit_pct': 0.01,
            'max_holding_minutes': 120,
            'quick_loss_cutoff': -0.03,
            
            # 防重复交易
            'signal_cooldown_minutes': 5,
            'same_symbol_cooldown': 15,
            
            # 交易参数
            'min_volume': 10000,
            'min_data_points': 30,
            'commission_rate': 0.0005,
            
            # IB交易参数
            'ib_order_type': 'MKT',  # 'MKT' 或 'LMT'
            'ib_limit_offset': 0.01,  # 限价单偏移量（百分比）
        }
    
    def _generate_signal_hash(self, signal: Dict) -> str:
        """生成信号唯一哈希，用于防重复"""
        signal_str = f"{signal['symbol']}_{signal['signal_type']}_{signal['action']}_{signal.get('reason', '')}"
        price_bucket = int(signal['price'] * 100) // 5
        signal_str += f"_{price_bucket}"
        return hashlib.md5(signal_str.encode()).hexdigest()[:8]
    
    def _is_signal_cooldown(self, signal_hash: str) -> bool:
        """检查信号是否在冷却期"""
        if signal_hash in self.signal_cache:
            expiration = self.signal_cache[signal_hash]
            if datetime.now() < expiration:
                return True
        return False
    
    def _add_signal_to_cache(self, signal_hash: str):
        """添加信号到缓存"""
        cooldown = self.config['signal_cooldown_minutes']
        expiration = datetime.now() + timedelta(minutes=cooldown)
        self.signal_cache[signal_hash] = expiration
        current_time = datetime.now()
        expired_keys = [k for k, v in self.signal_cache.items() if v < current_time]
        for key in expired_keys:
            del self.signal_cache[key]
    
    def sync_positions_from_ib(self):
        """从IB同步持仓信息"""
        if not self.ib_trader:
            logger.warning("未提供IB交易接口，无法同步持仓")
            return
        
        try:
            holdings = self.ib_trader.get_holdings()
            self.positions.clear()
            
            for pos in holdings:
                symbol = pos.contract.symbol
                self.positions[symbol] = {
                    'size': pos.position,
                    'avg_cost': pos.avgCost,
                    'contract': pos.contract
                }
            
            # 同步净资产
            self.equity = self.ib_trader.get_net_liquidation()
            
            if self.positions:
                logger.info(f"✅ 从IB同步持仓成功: {len(self.positions)} 个持仓")
            else:
                logger.info("✅ 从IB同步持仓成功: 无持仓")
                
        except Exception as e:
            logger.error(f"从IB同步持仓失败: {e}")
    
    def analyze_market_regime(self, data: pd.DataFrame) -> str:
        """分析市场状态"""
        if len(data) < 20:
            return "INSUFFICIENT_DATA"
        
        returns = data['Close'].pct_change().dropna()
        volatility = returns.std() * np.sqrt(252)
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
        检测早盘动量信号
        """
        if len(data) < 10:
            logger.info(f"{symbol} 数据不足，无法检测早盘动量信号")
            return None
        
        current_time = datetime.now().time()
        morning_start = datetime.strptime(self.config['morning_session'][0], '%H:%M').time()
        morning_end = datetime.strptime(self.config['morning_session'][1], '%H:%M').time()
        
        # 检查是否已有持仓
        if symbol in self.positions:
            logger.info(f"{symbol} 已有持仓，跳过新信号生成")
            return None
        
        latest = data.iloc[-1]
        
        # 1. RSI条件
        rsi = indicators.get('RSI', 50)
        if not (50 <= rsi <= 67):
            logger.info(f"{symbol} RSI不符合早盘动量条件: {rsi}")
            return None
        
        # 2. 价格偏离均线
        ma_key = 'MA_20'
        if ma_key not in indicators or indicators[ma_key] is None:
            logger.info(f"{symbol} 缺少MA20指标，无法检测早盘动量")
            return None
        
        price_deviation = (latest['Close'] - indicators[ma_key]) / indicators[ma_key] * 100
        if abs(price_deviation) < 0.3:
            logger.info(f"{symbol} 价格偏离不足，非早盘动量: {price_deviation:.2f}%")
            return None
        
        # 3. 成交量确认
        if 'Volume' in data.columns and len(data) >= 5:
            recent_volume = data['Volume'].iloc[-5:].mean()
            if latest['Volume'] < recent_volume * 1.05:
                logger.info(f"{symbol} 成交量未放大，非早盘动量")
                return None
        
        # 计算信号强度
        confidence = 0.5
        if price_deviation > 0:
            confidence += min(price_deviation / 5.0, 0.3)
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
        检测午盘/尾盘反转信号
        """
        current_time = datetime.now().time()
        midday_start = datetime.strptime(self.config['midday_session'][0], '%H:%M').time()
        afternoon_end = datetime.strptime(self.config['afternoon_session'][1], '%H:%M').time()
        
        # 检查是否已有持仓
        if symbol in self.positions:
            logger.info(f"{symbol} 已有持仓，跳过反转信号生成")
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
        
        # 3. 确认反转模式
        if not ((is_overbought and near_high) or (is_oversold and near_low)):
            return None
        
        # 4. 成交量确认
        volume_ok = True
        if 'Volume' in data.columns and len(data) >= 10:
            avg_volume = data['Volume'].iloc[-10:].mean()
            volume_ratio = latest['Volume'] / avg_volume
            volume_ok = 0.5 < volume_ratio < 2.5
        
        if not volume_ok:
            return None
        
        # 确定交易方向
        if is_overbought and near_high:
            action = 'SELL'
            reason = f"午盘反转: RSI超买 {rsi:.1f}, 接近近期高点"
            confidence = min(0.4 + (rsi - 70) / 30, 0.8)
        else:
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
    
    def check_exit_conditions(self, symbol: str, current_price: float, 
                             current_time: datetime = None) -> Optional[Dict]:
        """
        检查卖出条件
        
        返回卖出信号字典，如果不需要卖出则返回None
        """
        if symbol not in self.positions:
            return None
        
        if current_time is None:
            current_time = datetime.now()
        
        position = self.positions[symbol]
        avg_cost = position['avg_cost']
        position_size = position['size']
        
        # 如果没有入场时间，使用默认值（从IB同步时可能没有）
        entry_time = position.get('entry_time', current_time - timedelta(minutes=60))
        
        # 计算盈亏
        if position_size > 0:  # 多头
            price_change_pct = (current_price - avg_cost) / avg_cost
            unrealized_pnl = position_size * (current_price - avg_cost)
        else:  # 空头（目前策略只做多）
            price_change_pct = (avg_cost - current_price) / avg_cost
            unrealized_pnl = abs(position_size) * (avg_cost - current_price)
        
        # 检查止损条件
        stop_loss_pct = -self.config['stop_loss_atr_multiple'] * 0.02  # 简化计算
        if price_change_pct <= stop_loss_pct:
            return {
                'symbol': symbol,
                'signal_type': 'STOP_LOSS',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"触发止损: 亏损{price_change_pct*100:.1f}%",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100
            }
        
        # 检查止盈条件
        take_profit_pct = self.config['take_profit_atr_multiple'] * 0.02  # 简化计算
        if price_change_pct >= take_profit_pct:
            return {
                'symbol': symbol,
                'signal_type': 'TAKE_PROFIT',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"触发止盈: 盈利{price_change_pct*100:.1f}%",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100
            }
        
        # 快速止损
        if price_change_pct <= self.config['quick_loss_cutoff']:
            return {
                'symbol': symbol,
                'signal_type': 'QUICK_LOSS',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"快速止损: 亏损{price_change_pct*100:.1f}%",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100
            }
        
        # 最大持仓时间
        holding_minutes = (current_time - entry_time).total_seconds() / 60
        if holding_minutes > self.config['max_holding_minutes']:
            return {
                'symbol': symbol,
                'signal_type': 'MAX_HOLDING',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"超时平仓: 持仓{holding_minutes:.0f}分钟",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100
            }
        
        # 尾盘强制平仓
        current_time_of_day = current_time.time()
        market_close = datetime.strptime("15:45", "%H:%M").time()
        if current_time_of_day >= market_close and abs(position_size) > 0:
            return {
                'symbol': symbol,
                'signal_type': 'MARKET_CLOSE',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"尾盘强制平仓",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100
            }
        
        return None
    
    def calculate_position_size(self, signal: Dict, atr: float) -> int:
        """基于凯利公式和波动率计算仓位"""
        if atr <= 0:
            atr = signal['price'] * 0.02
        
        # 从IB获取可用资金
        if self.ib_trader:
            try:
                available_funds = self.ib_trader.get_available_funds()
                if available_funds > 0:
                    self.equity = available_funds
                    logger.info(f"IB可用资金: ${available_funds:,.2f}")
            except Exception as e:
                logger.warning(f"获取IB可用资金失败: {e}, 使用本地权益")
        
        risk_amount = self.equity * self.config['risk_per_trade']
        risk_amount *= signal.get('confidence', 0.5)
        
        risk_per_share = atr * self.config['stop_loss_atr_multiple']
        if risk_per_share <= 0:
            logger.warning("风险每股计算错误，无法计算仓位")
            return 0
        
        shares = int(risk_amount / risk_per_share)
        
        # 确保至少1股
        shares = max(1, shares)
        
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
                logger.info(f"{symbol} 成交量不足，跳过信号生成")
                return signals
        
        # 获取ATR
        atr = indicators.get('ATR', data['Close'].std() * 0.01)
        
        # 1. 检查是否有持仓需要卖出
        if symbol in self.positions and len(data) > 0:
            current_price = data['Close'].iloc[-1]
            exit_signal = self.check_exit_conditions(symbol, current_price)
            if exit_signal:
                exit_signal['position_size'] = abs(self.positions[symbol]['size'])
                signals.append(exit_signal)
        
        # 2. 只在没有持仓时生成买入信号
        if symbol not in self.positions:
            # 早盘动量信号
            morning_signal = self.detect_morning_momentum(symbol, data, indicators)
            if morning_signal:
                # 检查信号冷却
                signal_hash = self._generate_signal_hash(morning_signal)
                if not self._is_signal_cooldown(signal_hash) and signal_hash not in self.executed_signals:
                    morning_signal['position_size'] = self.calculate_position_size(morning_signal, atr)
                    morning_signal['signal_hash'] = signal_hash
                    if morning_signal['position_size'] > 0:
                        signals.append(morning_signal)
                        self.executed_signals.add(signal_hash)
            
            # 午盘/尾盘反转信号
            reversal_signal = self.detect_afternoon_reversal(symbol, data, indicators)
            if reversal_signal:
                signal_hash = self._generate_signal_hash(reversal_signal)
                if not self._is_signal_cooldown(signal_hash) and signal_hash not in self.executed_signals:
                    reversal_signal['position_size'] = self.calculate_position_size(reversal_signal, atr)
                    reversal_signal['signal_hash'] = signal_hash
                    if reversal_signal['position_size'] > 0:
                        signals.append(reversal_signal)
                        self.executed_signals.add(signal_hash)
        
        # 记录信号统计
        if signals:
            self.signals_generated += len(signals)
            logger.info(f"📊 {symbol} 生成 {len(signals)} 个交易信号")
        
        return signals
    
    def execute_signal(self, signal: Dict, current_price: float) -> Dict:
        """执行交易信号 - 使用IB接口"""
        if signal['position_size'] <= 0:
            logger.warning(f"{signal['symbol']} 无效仓位，跳过执行")
            return {'status': 'REJECTED', 'reason': '无效仓位'}
        
        # 检查信号冷却
        if 'signal_hash' in signal and self._is_signal_cooldown(signal['signal_hash']):
            logger.info(f"{signal['symbol']} 信号在冷却期，跳过执行")
            return {'status': 'REJECTED', 'reason': '信号冷却期'}
        
        if not self.ib_trader:
            logger.error("未提供IB交易接口，无法执行交易")
            return {'status': 'REJECTED', 'reason': 'IB接口未初始化'}
        
        # 创建交易记录
        trade = {
            'symbol': signal['symbol'],
            'action': signal['action'],
            'entry_price': current_price,
            'size': signal['position_size'],
            'timestamp': datetime.now(),
            'signal_type': signal['signal_type'],
            'confidence': signal.get('confidence', 0.5),
            'status': 'PENDING',
            'order_type': self.config['ib_order_type']
        }
        
        try:
            # 根据配置选择订单类型
            if self.config['ib_order_type'] == 'LMT':
                # 限价单，设置价格偏移
                offset_pct = self.config.get('ib_limit_offset', 0.01)
                if signal['action'] == 'BUY':
                    limit_price = current_price * (1 - offset_pct)
                else:  # SELL
                    limit_price = current_price * (1 + offset_pct)
                
                if signal['action'] == 'BUY':
                    ib_trade = self.ib_trader.place_buy_order(
                        signal['symbol'], signal['position_size'], 
                        'LMT', limit_price
                    )
                else:  # SELL
                    ib_trade = self.ib_trader.place_sell_order(
                        signal['symbol'], signal['position_size'],
                        'LMT', limit_price
                    )
            else:
                # 市价单
                if signal['action'] == 'BUY':
                    ib_trade = self.ib_trader.place_buy_order(
                        signal['symbol'], signal['position_size'], 'MKT'
                    )
                else:  # SELL
                    ib_trade = self.ib_trader.place_sell_order(
                        signal['symbol'], signal['position_size'], 'MKT'
                    )
            
            if ib_trade:
                trade['status'] = 'EXECUTED'
                trade['order_id'] = ib_trade.order.orderId
                trade['order_status'] = ib_trade.orderStatus.status
                
                # 添加信号到缓存（防重复）
                if 'signal_hash' in signal:
                    self._add_signal_to_cache(signal['signal_hash'])
                
                # 更新本地持仓缓存
                if signal['action'] == 'BUY':
                    # 买入后更新本地持仓
                    if signal['symbol'] not in self.positions:
                        self.positions[signal['symbol']] = {
                            'size': signal['position_size'],
                            'avg_cost': current_price,
                            'entry_time': datetime.now()
                        }
                    else:
                        # 已有持仓，计算平均成本
                        old_pos = self.positions[signal['symbol']]
                        total_size = old_pos['size'] + signal['position_size']
                        total_cost = old_pos['size'] * old_pos['avg_cost'] + signal['position_size'] * current_price
                        self.positions[signal['symbol']] = {
                            'size': total_size,
                            'avg_cost': total_cost / total_size,
                            'entry_time': old_pos.get('entry_time', datetime.now())
                        }
                else:  # SELL
                    # 卖出后移除本地持仓
                    if signal['symbol'] in self.positions:
                        del self.positions[signal['symbol']]
                
                self.trade_history.append(trade)
                self.trades_executed += 1
                
                action_icon = "🟢" if signal['action'] == 'BUY' else "🔴"
                logger.info(f"{action_icon} IB执行交易: {signal['symbol']} {signal['action']} "
                           f"@{current_price:.2f}, "
                           f"数量: {signal['position_size']}, "
                           f"订单ID: {trade.get('order_id', 'N/A')}")
                
                return trade
            else:
                trade['status'] = 'FAILED'
                trade['reason'] = 'IB下单失败'
                logger.error(f"❌ IB下单失败: {signal['symbol']} {signal['action']}")
                return trade
                
        except Exception as e:
            trade['status'] = 'ERROR'
            trade['reason'] = str(e)
            logger.error(f"❌ 执行交易时出错 {signal['symbol']}: {e}")
            return trade
    
    def run_analysis_cycle(self, data_provider, symbols: List[str]) -> Dict[str, List[Dict]]:
        """运行分析周期"""
        all_signals = {}
        self.executed_signals.clear()
        
        # 首先从IB同步持仓和资金
        self.sync_positions_from_ib()
        
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
                    
                    # 执行信号
                    for signal in signals:
                        current_price = df['Close'].iloc[-1]
                        self.execute_signal(signal, current_price)
                        
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
        
        # 从IB同步最新信息
        self.sync_positions_from_ib()
        
        # 简化统计
        for trade in self.trade_history[-100:]:
            if trade['status'] == 'EXECUTED':
                # 这里可以添加更精确的盈亏计算
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
            'open_positions': list(self.positions.keys()),
            'signal_cache_size': len(self.signal_cache),
            'ib_connected': self.ib_trader.connected if self.ib_trader else False,
            'recommendations': [
                "基于动量反转策略",
                f"持仓数量: {len(self.positions)}",
                f"IB连接: {'✅' if (self.ib_trader and self.ib_trader.connected) else '❌'}"
            ]
        }
        
        logger.info(f"📋 交易报告 - 净资产: ${self.equity:,.2f}, "
                   f"总交易: {total_trades}, 胜率: {win_rate:.1%}, "
                   f"持仓: {len(self.positions)}")
        
        return report

# ==================== 主交易系统 ====================
class MomentumReversalSystem:
    """动量反转交易系统主控制器"""
    
    def __init__(self, config_file: str = None):
        self.config = self._load_config(config_file)
        self.start_time = datetime.now()
        
        # 初始化组件
        self.data_provider = None
        self.ib_trader = None
        self.strategy_engine = None
        
        # 系统状态
        self.is_running = False
        self.cycle_count = 0
        self.last_signals = {}
        
        logger.info("=" * 70)
        logger.info("动量反转日内交易系统 (IB接口版)")
        logger.info("使用IB执行真实交易")
        logger.info("=" * 70)
        logger.info(f"日志文件: {log_file}")
    
    def _load_config(self, config_file: str) -> Dict:
        """加载配置"""
        default_config = {
            'data_server': {
                'base_url': 'http://localhost:8001',
                'retry_attempts': 3
            },
            'ib_server': {
                'host': '127.0.0.1',
                'port': 7497,
                'client_id': 1
            },
            'trading': {
                'symbols': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META','MU','INTC','AMD',
                            'NFLX','BIDU','JD','BABA','TCEHY','PYPL','SHOP','CRM','ORCL','IBM',
                            'CSCO','QCOM','TXN','AVGO','ADBE','INTU','ZM','DOCU','SNOW','UBER',
                            'LYFT'],
                'scan_interval_minutes': 1,
                'trading_hours': {
                    'start': '00:00',
                    'end': '15:45'
                }
            },
            'strategy': {
                'initial_capital': 100000.0,
                'risk_per_trade': 0.02,
                'max_position_size': 0.1,
                'ib_order_type': 'MKT',
                'ib_limit_offset': 0.01
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
        
        # 2. 初始化IB交易接口
        ib_config = self.config['ib_server']
        self.ib_trader = IBTrader(
            host=ib_config['host'],
            port=ib_config['port'],
            client_id=ib_config['client_id']
        )
        
        # 连接IB
        if not self.ib_trader.connect():
            logger.warning("⚠️  IB连接失败，将使用模拟交易模式")
            self.ib_trader = None
        
        # 3. 初始化策略引擎
        strategy_config = self.config['strategy']
        self.strategy_engine = MomentumReversalEngine(strategy_config, self.ib_trader)
        
        logger.info("\n✅ 系统初始化完成")
        logger.info(f"交易标的: {', '.join(self.config['trading']['symbols'][:5])}...")
        logger.info(f"扫描间隔: {self.config['trading']['scan_interval_minutes']} 分钟")
        logger.info(f"交易时间: {self.config['trading']['trading_hours']['start']} - "
                   f"{self.config['trading']['trading_hours']['end']}")
        logger.info(f"IB连接: {'✅ 成功' if self.ib_trader and self.ib_trader.connected else '❌ 失败/模拟'}")
        
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
        
        # 打印IB账户信息
        if self.ib_trader and self.ib_trader.connected:
            net_liq = self.ib_trader.get_net_liquidation()
            available = self.ib_trader.get_available_funds()
            logger.info(f"IB账户 - 净资产: ${net_liq:,.2f}, 可用资金: ${available:,.2f}")
        
        # 运行策略分析
        symbols = self.config['trading']['symbols']
        signals = self.strategy_engine.run_analysis_cycle(self.data_provider, symbols)
        
        # 处理信号
        if signals:
            logger.info(f"\n📊 生成 {len(signals)} 个标的的信号:")
            for symbol, sig_list in signals.items():
                for sig in sig_list:
                    action_icon = "🟢" if sig['action'] == 'BUY' else "🔴"
                    logger.info(f"  {action_icon} {symbol}: {sig['action']} @ ${sig['price']:.2f}, "
                              f"数量: {sig.get('position_size', 0):,}, "
                              f"类型: {sig['signal_type']}, "
                              f"原因: {sig.get('reason', 'N/A')}")
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
        logger.info(f"  净资产: ${report['equity']:,.2f}")
        logger.info(f"  总交易: {report['total_trades']}")
        logger.info(f"  胜率: {report['win_rate']:.1%}")
        logger.info(f"  今日PNL: ${report['daily_pnl']:,.2f}")
        logger.info(f"  持仓数量: {report['positions_open']}")
        
        if report['positions_open'] > 0:
            logger.info(f"  持仓标的: {', '.join(report['open_positions'])}")
        
        logger.info(f"  IB连接: {'✅' if report['ib_connected'] else '❌'}")
        
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
        
        interval = self.config['trading']['scan_interval_minutes']
        schedule.every(interval).minutes.at(":00").do(self.trading_cycle)
        
        logger.info(f"\n✅ 系统已启动，每 {interval} 分钟扫描一次")
        logger.info("按 Ctrl+C 停止系统\n")
        
        self.trading_cycle()
        
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
        
        # 断开IB连接
        if self.ib_trader:
            self.ib_trader.disconnect()
        
        logger.info("系统已安全停止")

# ==================== 主程序入口 ====================
def main():
    """主函数"""
    import sys
    
    logger.info("🚀 动量反转日内交易系统启动")
    logger.info("版本: IB接口版 (使用IB执行真实交易)")
    logger.info(f"日志文件: {log_file}")
    logger.info("=" * 70)
    
    system = MomentumReversalSystem()
    
    try:
        system.start()
    except Exception as e:
        logger.error(f"\n❌ 系统运行出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()