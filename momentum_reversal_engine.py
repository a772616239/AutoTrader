import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime, time, timedelta
import warnings
warnings.filterwarnings('ignore')

@dataclass
class TradeSignal:
    """交易信号数据结构"""
    symbol: str
    action: str  # 'BUY' or 'SELL'
    entry_price: float
    size: int
    timestamp: datetime
    stop_loss: float
    take_profit: float
    confidence: float  # 0.0-1.0
    signal_type: str  # 'MOMENTUM_REVERSAL', 'BREAKOUT', etc.
    metadata: Dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

@dataclass
class PerformanceMetrics:
    """绩效指标"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    calmar_ratio: float = 0.0
    sortino_ratio: float = 0.0

class MomentumReversalEngine:
    """
    动量反转日内交易引擎
    
    核心逻辑：
    1. 识别短期动量极端（RSI超买/超卖 + 价格偏离均线）
    2. 等待动量衰竭信号（成交量萎缩 + 价格形态）
    3. 确认反转开始（背离出现 + 关键价位突破）
    """
    
    def __init__(self, config: Dict = None):
        self.config = self._load_default_config()
        if config:
            self.config.update(config)
        
        # 状态变量
        self.positions = {}
        self.trade_history = []
        self.daily_pnl = 0.0
        self.cumulative_pnl = 0.0
        self.max_drawdown = 0.0
        self.equity_curve = []
        
        # 性能指标
        self.metrics = PerformanceMetrics()
        
        # 市场状态跟踪
        self.market_regime = "NEUTRAL"  # TRENDING, MEAN_REVERTING, VOLATILE
        
    def _load_default_config(self) -> Dict:
        """加载默认参数配置"""
        return {
            # 信号参数
            'rsi_overbought': 72,
            'rsi_oversold': 28,
            'ma_period': 20,
            'deviation_threshold': 2.5,  # 价格偏离均线的百分比阈值
            'volume_ratio_threshold': 0.7,  # 成交量萎缩阈值
            
            # 风险参数
            'max_position_size': 0.1,  # 最大仓位比例
            'risk_per_trade': 0.02,  # 单笔交易风险
            'daily_loss_limit': -0.05,  # 单日亏损上限
            'max_drawdown_limit': -0.15,  # 最大回撤上限
            
            # 交易参数
            'min_volume': 1000000,  # 最小成交量要求
            'min_price': 5.0,  # 最低价格要求
            'max_slippage': 0.001,  # 最大滑点
            
            # 时间参数
            'trade_start_time': time(9, 45),  # 交易开始时间
            'trade_end_time': time(15, 45),  # 交易结束时间
            'position_close_time': time(15, 55),  # 强制平仓时间
            
            # 过滤器参数
            'min_data_points': 30,
            'volatility_filter': True,
            'market_cap_filter': False,
        }
    
    def detect_momentum_extremes(self, symbol: str, data: pd.DataFrame,
                                indicators: Dict) -> Dict:
        """
        检测动量极端点
        
        返回:
        {
            'is_extreme': bool,
            'extreme_type': 'OVERBOUGHT' or 'OVERSOLD',
            'strength': float,  # 极端强度 0-1
            'confidence': float, # 信号置信度 0-1
            'indicators': dict   # 使用的指标值
        }
        """
        if len(data) < self.config['min_data_points']:
            return {'is_extreme': False, 'confidence': 0.0}
        
        # 获取最新数据点
        latest = data.iloc[-1]
        prev = data.iloc[-2] if len(data) > 1 else latest
        
        result = {
            'is_extreme': False,
            'extreme_type': None,
            'strength': 0.0,
            'confidence': 0.0,
            'indicators': {}
        }
        
        # 1. RSI极端判断
        rsi = indicators.get('RSI', 50)
        rsi_extreme = False
        
        if rsi > self.config['rsi_overbought']:
            rsi_extreme = True
            extreme_type = 'OVERBOUGHT'
            rsi_strength = min((rsi - self.config['rsi_overbought']) / 30, 1.0)
        elif rsi < self.config['rsi_oversold']:
            rsi_extreme = True
            extreme_type = 'OVERSOLD'
            rsi_strength = min((self.config['rsi_oversold'] - rsi) / 30, 1.0)
        else:
            rsi_strength = 0.0
            
        # 2. 价格偏离均线程度
        ma_key = f"MA_{self.config['ma_period']}"
        if ma_key in indicators and indicators[ma_key] is not None:
            ma_value = indicators[ma_key]
            price_deviation = (latest['Close'] - ma_value) / ma_value * 100
            deviation_extreme = abs(price_deviation) > self.config['deviation_threshold']
            deviation_strength = min(abs(price_deviation) / (self.config['deviation_threshold'] * 2), 1.0)
        else:
            deviation_extreme = False
            deviation_strength = 0.0
            
        # 3. 成交量确认
        if 'Volume' in data.columns:
            volume_latest = latest['Volume']
            volume_avg = data['Volume'].rolling(window=20).mean().iloc[-1]
            volume_ratio = volume_latest / volume_avg if volume_avg > 0 else 1.0
            
            # 动量极端时成交量萎缩是反转前兆
            volume_confirmation = volume_ratio < self.config['volume_ratio_threshold']
            volume_strength = 1.0 - min(volume_ratio / self.config['volume_ratio_threshold'], 1.0)
        else:
            volume_confirmation = False
            volume_strength = 0.0
            
        # 4. 动量衰竭信号（价格创新高但动量指标下降）
        momentum_divergence = self._detect_divergence(data, indicators)
        divergence_strength = 0.5 if momentum_divergence else 0.0
        
        # 综合判断
        if rsi_extreme and deviation_extreme:
            result['is_extreme'] = True
            result['extreme_type'] = extreme_type
            result['strength'] = (rsi_strength * 0.4 + 
                                deviation_strength * 0.3 + 
                                volume_strength * 0.2 +
                                divergence_strength * 0.1)
            
            # 置信度计算
            confidence_factors = []
            if rsi_extreme:
                confidence_factors.append(0.3)
            if deviation_extreme:
                confidence_factors.append(0.25)
            if volume_confirmation:
                confidence_factors.append(0.25)
            if momentum_divergence:
                confidence_factors.append(0.2)
                
            result['confidence'] = min(sum(confidence_factors), 1.0)
            
        result['indicators'] = {
            'rsi': rsi,
            'price_deviation': price_deviation if 'price_deviation' in locals() else 0,
            'volume_ratio': volume_ratio if 'volume_ratio' in locals() else 1.0,
            'has_divergence': momentum_divergence
        }
        
        return result
    
    def _detect_divergence(self, data: pd.DataFrame, indicators: Dict) -> bool:
        """检测价格与动量指标的背离"""
        if len(data) < 10:
            return False
        
        # 价格创新高但RSI未创新高（顶背离）
        price_highs = data['High'].rolling(window=5).max()
        latest_price_high = price_highs.iloc[-1]
        prev_price_high = price_highs.iloc[-2] if len(price_highs) > 1 else latest_price_high
        
        # 简化处理：假设可以获取RSI历史序列
        # 实际中需要从indicators或重新计算
        try:
            rsi_values = indicators.get('rsi_history', [])
            if len(rsi_values) >= 5:
                latest_rsi_high = max(rsi_values[-5:])
                prev_rsi_high = max(rsi_values[-10:-5]) if len(rsi_values) >= 10 else latest_rsi_high
                
                # 顶背离：价格创新高但RSI未创新高
                if (latest_price_high > prev_price_high and 
                    latest_rsi_high <= prev_rsi_high * 1.02):  # 允许2%误差
                    return True
        except:
            pass
            
        return False
    
    def generate_reversal_signals(self, symbol: str, data: pd.DataFrame,
                                 indicators: Dict) -> List[TradeSignal]:
        """
        生成动量反转交易信号
        
        核心逻辑：
        1. 检测动量极端
        2. 等待确认信号（价格行为 + 成交量）
        3. 生成具体交易信号
        """
        signals = []
        
        # 1. 检查交易时间
        current_time = datetime.now().time()
        if (current_time < self.config['trade_start_time'] or 
            current_time > self.config['trade_end_time']):
            return signals
            
        # 2. 检测动量极端
        extreme_analysis = self.detect_momentum_extremes(symbol, data, indicators)
        
        if not extreme_analysis['is_extreme']:
            return signals
            
        # 3. 风险检查
        if not self._risk_checks_passed(symbol, data):
            return signals
            
        # 4. 根据极端类型生成信号
        if extreme_analysis['extreme_type'] == 'OVERSOLD':
            signal = self._generate_buy_signal(
                symbol, data, indicators, extreme_analysis
            )
            if signal:
                signals.append(signal)
                
        elif extreme_analysis['extreme_type'] == 'OVERBOUGHT':
            signal = self._generate_sell_signal(
                symbol, data, indicators, extreme_analysis
            )
            if signal:
                signals.append(signal)
                
        return signals
    
    def _generate_buy_signal(self, symbol: str, data: pd.DataFrame,
                            indicators: Dict, extreme_analysis: Dict) -> Optional[TradeSignal]:
        """生成买入信号（超卖反转）"""
        latest = data.iloc[-1]
        
        # 确认条件：开始出现看涨价格行为
        # 1. 下影线较长（显示买盘支撑）
        candle_range = latest['High'] - latest['Low']
        lower_shadow = latest['Close'] - latest['Low']
        has_long_lower_shadow = lower_shadow > candle_range * 0.3
        
        # 2. 收盘价在顶部1/3（显示强势）
        close_position = (latest['Close'] - latest['Low']) / candle_range
        close_strong = close_position > 0.66
        
        # 3. 成交量开始放大
        volume_increasing = False
        if 'Volume' in data.columns and len(data) > 3:
            recent_volumes = data['Volume'].iloc[-3:].values
            volume_increasing = recent_volumes[-1] > recent_volumes[-2]
        
        if not (has_long_lower_shadow or close_strong or volume_increasing):
            return None
            
        # 计算仓位大小
        position_size = self._calculate_position_size(
            symbol, latest['Close'], extreme_analysis['confidence']
        )
        
        if position_size <= 0:
            return None
            
        # 设置止损止盈
        atr = indicators.get('ATR', latest['Close'] * 0.02)  # 默认2% ATR
        
        # 止损：入场价下方1.5倍ATR或关键支撑位
        stop_loss = latest['Close'] - (atr * 1.5)
        
        # 止盈：风险回报比至少2:1
        take_profit = latest['Close'] + (atr * 3.0)
        
        return TradeSignal(
            symbol=symbol,
            action='BUY',
            entry_price=latest['Close'],
            size=position_size,
            timestamp=datetime.now(),
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=extreme_analysis['confidence'],
            signal_type='MOMENTUM_REVERSAL',
            metadata={
                'extreme_type': 'OVERSOLD',
                'rsi': indicators.get('RSI', 0),
                'atr': atr,
                'risk_reward_ratio': 2.0
            }
        )
    
    def _generate_sell_signal(self, symbol: str, data: pd.DataFrame,
                             indicators: Dict, extreme_analysis: Dict) -> Optional[TradeSignal]:
        """生成卖出信号（超买反转）"""
        # 类似_buy_signal的逻辑，方向相反
        # 实际实现中需要处理卖空规则
        pass  # 限于篇幅，具体实现省略
    
    def _calculate_position_size(self, symbol: str, price: float, 
                                confidence: float) -> int:
        """基于凯利公式和波动率调整计算仓位大小"""
        
        # 1. 基础风险计算
        account_size = 100000  # 假设账户规模
        risk_amount = account_size * self.config['risk_per_trade']
        
        # 2. 基于置信度调整
        adjusted_risk = risk_amount * confidence
        
        # 3. 计算基于波动率的仓位
        # 实际中需要获取历史波动率
        daily_volatility = 0.02  # 假设2%日波动率
        position_value = adjusted_risk / (daily_volatility * 2.5)  # 保守系数
        
        # 4. 转换为股数
        shares = int(position_value / price)
        
        # 5. 应用最大仓位限制
        max_shares = int((account_size * self.config['max_position_size']) / price)
        shares = min(shares, max_shares)
        
        return max(shares, 0)
    
    def _risk_checks_passed(self, symbol: str, data: pd.DataFrame) -> bool:
        """风险检查"""
        checks = []
        
        # 1. 日亏损限制
        if self.daily_pnl < self.config['daily_loss_limit'] * 100000:  # 假设账户规模
            print(f"达到日亏损限制: {self.daily_pnl}")
            return False
            
        # 2. 回撤限制
        if self.max_drawdown < self.config['max_drawdown_limit']:
            print(f"达到最大回撤限制: {self.max_drawdown}")
            return False
            
        # 3. 流动性检查
        latest_volume = data['Volume'].iloc[-1] if 'Volume' in data.columns else 0
        if latest_volume < self.config['min_volume']:
            return False
            
        # 4. 价格检查
        latest_price = data['Close'].iloc[-1]
        if latest_price < self.config['min_price']:
            return False
            
        # 5. 波动率过滤
        if self.config['volatility_filter']:
            returns = data['Close'].pct_change().dropna()
            if len(returns) > 20:
                volatility = returns.std() * np.sqrt(252)
                if volatility > 0.5:  # 过滤过高波动率股票
                    return False
        
        return True
    
    def execute_trade(self, signal: TradeSignal, market_data: pd.DataFrame) -> Dict:
        """执行交易（模拟或实盘）"""
        
        execution = {
            'signal': signal,
            'executed_price': signal.entry_price,
            'slippage': 0.0,
            'commission': 0.0,
            'timestamp': datetime.now(),
            'status': 'FILLED'  # 或 'PARTIAL', 'REJECTED'
        }
        
        # 模拟滑点和佣金
        slippage = signal.entry_price * self.config['max_slippage'] * np.random.randn()
        execution['executed_price'] += slippage
        execution['slippage'] = slippage
        
        # 固定佣金
        execution['commission'] = max(1.0, signal.size * signal.entry_price * 0.0005)
        
        # 记录交易
        self._record_trade(execution)
        
        # 更新持仓
        self._update_position(signal, execution)
        
        return execution
    
    def _record_trade(self, execution: Dict):
        """记录交易到历史"""
        self.trade_history.append(execution)
        
        # 更新绩效指标
        self._update_performance_metrics()
    
    def _update_performance_metrics(self):
        """更新绩效指标"""
        if not self.trade_history:
            return
            
        # 计算基础指标
        trades = [t for t in self.trade_history if t['status'] == 'FILLED']
        if not trades:
            return
            
        # 这里需要实现具体的绩效计算逻辑
        # 限于篇幅，简化处理
        self.metrics.total_trades = len(trades)
        self.metrics.total_pnl = sum(t.get('pnl', 0) for t in trades)
    
    def run_intraday_cycle(self, symbols: List[str], 
                          data_provider) -> Dict[str, List[TradeSignal]]:
        """
        运行日内交易循环
        
        参数:
        data_provider: 数据提供对象，需有get_intraday_data方法
        
        返回:
        每个标的的信号列表
        """
        all_signals = {}
        
        for symbol in symbols:
            try:
                # 获取日内数据
                data = data_provider.get_intraday_data(
                    symbol, interval='5m', lookback=60
                )
                
                if data is None or len(data) < 20:
                    continue
                    
                # 计算技术指标
                indicators = self._calculate_indicators(data)
                
                # 生成信号
                signals = self.generate_reversal_signals(symbol, data, indicators)
                
                if signals:
                    all_signals[symbol] = signals
                    
                    # 执行信号
                    for signal in signals:
                        if self._should_execute_signal(signal):
                            self.execute_trade(signal, data)
                            
            except Exception as e:
                print(f"处理{symbol}时出错: {e}")
                continue
                
        return all_signals
    
    def _calculate_indicators(self, data: pd.DataFrame) -> Dict:
        """计算技术指标"""
        # 这里可以集成你的enhanced_stock_data.py
        # 或者直接调用本地HTTP服务
        import requests
        
        try:
            # 调用本地增强数据API
            # 注意：实际中需要调整参数
            pass
        except:
            # 本地计算简化版本
            return self._calculate_basic_indicators(data)
    
    def _calculate_basic_indicators(self, data: pd.DataFrame) -> Dict:
        """基础指标计算"""
        closes = data['Close'].values.astype(np.float64)
        
        indicators = {}
        
        # 移动平均线
        if len(closes) >= 5:
            indicators['MA_5'] = np.mean(closes[-5:])
        if len(closes) >= 20:
            indicators['MA_20'] = np.mean(closes[-20:])
            
        # RSI
        if len(closes) >= 15:
            deltas = np.diff(closes[-15:])
            gains = deltas[deltas > 0].sum() / 14
            losses = -deltas[deltas < 0].sum() / 14
            if losses != 0:
                rs = gains / losses
                indicators['RSI'] = 100 - (100 / (1 + rs))
            else:
                indicators['RSI'] = 100
                
        # ATR (简化版)
        if len(data) >= 14:
            high = data['High'].values[-14:].astype(np.float64)
            low = data['Low'].values[-14:].astype(np.float64)
            close_prev = closes[-15:-1]
            
            tr1 = high - low
            tr2 = np.abs(high - close_prev)
            tr3 = np.abs(low - close_prev)
            
            true_range = np.maximum.reduce([tr1, tr2, tr3])
            indicators['ATR'] = np.mean(true_range)
        
        return indicators
    
    def generate_daily_report(self) -> Dict:
        """生成日报"""
        report = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'total_trades': self.metrics.total_trades,
            'total_pnl': self.metrics.total_pnl,
            'daily_pnl': self.daily_pnl,
            'win_rate': self.metrics.win_rate,
            'max_drawdown': self.max_drawdown,
            'signals_generated': len([s for s in self.trade_history]),
            'positions_open': len(self.positions),
            'market_regime': self.market_regime,
            'recommendations': self._generate_recommendations()
        }
        
        return report
    
    def _generate_recommendations(self) -> List[str]:
        """基于当日表现生成建议"""
        recommendations = []
        
        if self.metrics.total_trades > 10:
            if self.metrics.win_rate < 0.4:
                recommendations.append("胜率偏低，考虑调整策略参数或减少交易频率")
                
        if self.max_drawdown < -0.08:
            recommendations.append("回撤较大，建议降低仓位或加强止损")
            
        if len(self.trade_history) < 3:
            recommendations.append("今日信号较少，市场可能处于震荡期")
            
        return recommendations