#!/usr/bin/env python3
"""
回调交易策略 (策略A4)
核心思想: 在上涨趋势的小幅回撤中买入，或在下跌趋势的反弹中卖出
使用斐波那契回撤、趋势识别、回撤确认等技术手段
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class A4PullbackStrategy(BaseStrategy):
    """回调交易策略"""
    
    def _default_config(self) -> Dict:
        """默认配置"""
        return {
            # 资金管理
            'initial_capital': 40000.0,
            'risk_per_trade': 0.02,
            'max_position_size': 0.1,
            'per_trade_notional_cap': 4000.0,  # 单笔交易美元上限
            'max_position_notional': 60000.0,  # 单股总仓位上限（美元）
            
            # 趋势识别参数
            'trend_ma_period': 50,           # 长期趋势均线周期
                'trend_confirmation_bars': 3,   # 趋势确认所需K线数
                'strong_trend_threshold': 0.0065, # 强势趋势阈值（1%）
            
            # 回撤识别参数
            'pullback_lookback': 78,         # 回撤识别窗口（扩大到100根K线）
            'fibonacci_levels': [0.236, 0.382, 0.5, 0.618, 0.786],  # 斐波那契回撤位
                'pullback_threshold': 0.01,    # 回撤至少要到的幅度（1%）
            
            # 买卖条件
            'pullback_buy_ratio': [0.15, 0.8],  # 回撤到这些位置买入 (min, max)
            'pullback_sell_ratio': [0.1, 0.8], # 反弹到这些位置卖出 (min, max)
            'volume_confirmation': True,    # 需要成交量确认
            'min_volume_ratio': 1.0,        # 最小成交量比率
            
            # 出场条件
            'stop_loss_pct': 0.03,         # 止损百分比
            'take_profit_pct': 0.05,       # 止盈百分比
            'max_holding_days': 5,         # 最大持有天数
            'trailing_stop_pct': 0.02,     # 追踪止损
            
            # 时间过滤
            'trading_start_time': '09:30',
            'trading_end_time': '16:00',
            'avoid_open_hour': True,       # 避开开盘波动
            'avoid_close_hour': True,      # 避开收盘波动
            
            # 防重复交易
            'signal_cooldown_minutes': 5,
            
            # IB交易参数
            'ib_order_type': 'MKT',
            'ib_limit_offset': 0.01,
        }
    
    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return "A4 Pullback Trading (斐波那契回撤)"
    
    def identify_trend(self, data: pd.DataFrame) -> Tuple[str, float, float]:
        """
        识别趋势方向和强度
        
        返回:
            (趋势方向: 'UPTREND'/'DOWNTREND'/'NO_TREND', 趋势强度, 最新价格)
        """
        if len(data) < self.config['trend_ma_period']:
            logger.info(f"数据不足识别趋势: {len(data)} < {self.config['trend_ma_period']}")
            return 'NO_TREND', 0.0, data['Close'].iloc[-1]
        
        # 计算长期均线
        ma_long = data['Close'].rolling(window=self.config['trend_ma_period']).mean().iloc[-1]
        current_price = data['Close'].iloc[-1]
        
        # 计算短期均线确认
        ma_short = data['Close'].rolling(window=20).mean().iloc[-1]
        
        # 计算价格相对均线的偏离度（趋势强度）
        trend_strength = abs(current_price - ma_long) / ma_long
        
        # 识别趋势
        if current_price > ma_long and ma_short > ma_long:
            trend = 'UPTREND'
        elif current_price < ma_long and ma_short < ma_long:
            trend = 'DOWNTREND'
        else:
            trend = 'NO_TREND'
        
        logger.info(f"📊 趋势识别: {trend}, 强度: {trend_strength:.2%}, 价格: {current_price:.2f}, MA50: {ma_long:.2f}, MA20: {ma_short:.2f}")
        return trend, trend_strength, current_price
    
    def calculate_fibonacci_levels(self, high: float, low: float) -> Dict[float, float]:
        """
        计算斐波那契回撤位
        
        参数:
            high: 近期高点
            low: 近期低点
        
        返回:
            {回撤率: 价格水平}
        """
        diff = high - low
        levels = {}
        
        for ratio in self.config['fibonacci_levels']:
            if high > low:
                # 上升趋势：从高点向下回撤
                level_price = high - (diff * ratio)
            else:
                # 下降趋势：从低点向上反弹
                level_price = low + (diff * ratio)
            levels[ratio] = level_price
        
        return levels
    
    def detect_pullback_in_uptrend(self, symbol: str, data: pd.DataFrame,
                                  indicators: Dict) -> Optional[Dict]:
        """
        在上升趋势中检测回撤买入信号
        """
        if symbol in self.positions:
            logger.info(f"{symbol} 已有持仓，跳过买入信号")
            return None
        
        # if len(data) < self.config['pullback_lookback'] + self.config['trend_ma_period']:
        #     logger.info(f"{symbol} 数据不足: {len(data)} < {self.config['pullback_lookback'] + self.config['trend_ma_period']}")
        #     return None
        
        # 识别趋势
        trend, trend_strength, current_price = self.identify_trend(data)
        if trend != 'UPTREND':
            logger.info(f"{symbol} 非上升趋势 ({trend})")
            return None
        # 要求趋势强度达到阈值，避免在非常弱的波动中入场
        if trend_strength < self.config.get('strong_trend_threshold', 0.01):
            logger.info(f"{symbol} 趋势强度不足 ({trend_strength:.2%} < {self.config['strong_trend_threshold']:.2%})")
            return None
        
        # 找出近期高低点
        lookback = self.config['pullback_lookback']
        recent_high = data['High'].iloc[-lookback:].max()
        recent_low = data['Low'].iloc[-lookback:].min()
        
        # 计算斐波那契回撤位
        fib_levels = self.calculate_fibonacci_levels(recent_high, recent_low)
        swing_range = recent_high - recent_low
        
        # 检查当前价格是否处于回撤位
        pullback_amount = recent_high - current_price
        pullback_ratio = pullback_amount / swing_range if swing_range > 0 else 0
        
        min_ratio, max_ratio = self.config['pullback_buy_ratio']
        
        logger.info(f"  {symbol} 上升趋势回撤分析: 高{recent_high:.2f} 低{recent_low:.2f} 当前{current_price:.2f} 回撤幅度{pullback_ratio:.1%} (目标{min_ratio:.1%}-{max_ratio:.1%})")
        
        # 确认回撤到目标位置
        if not (min_ratio <= pullback_ratio <= max_ratio):
            logger.info(f"{symbol} 回撤幅度不在目标范围: {pullback_ratio:.1%}")
            return None
        
        # 确认回撤幅度最小要求
        if pullback_ratio < self.config['pullback_threshold'] / swing_range:
            logger.info(f"{symbol} 回撤幅度小于最小要求")
            return None
        
        # 成交量确认
        if self.config['volume_confirmation']:
            if len(data) >= 10:
                avg_volume = data['Volume'].iloc[-10:].mean()
                current_volume = data['Volume'].iloc[-1]
                volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
                if volume_ratio < self.config['min_volume_ratio']:
                    logger.info(f"{symbol} 成交量不足: {volume_ratio:.2f}x --min_volume_ratio {self.config['min_volume_ratio']}")
                    return None
        
        # 计算信号强度（回撤到 0.618 的效果最好）
        distance_to_golden = abs(pullback_ratio - 0.618)
        confidence = max(0.3, 0.8 - distance_to_golden * 2)
        
        logger.info(
            f"🟢 {symbol} 上升趋势回撤买入信号"
            f" | 近期高: {recent_high:.2f}, 当前: {current_price:.2f}, 回撤幅度: {pullback_ratio:.1%}"
            f" | 趋势强度: {trend_strength:.2%}, 置信度: {confidence:.1%}"
        )
        # 置信度门槛过滤，避免过多低质量信号
        if confidence < self.config.get('min_confidence', 0.29):
            logger.info(f"{symbol} 信号置信度过低: {confidence:.1%} < {self.config.get('min_confidence', 0.5):.1%}")
            return None
        
        signal = {
            'symbol': symbol,
            'signal_type': 'PULLBACK_BUY_UPTREND',
            'action': 'BUY',
            'price': current_price,
            'reason': f"上升趋势回撤 ({pullback_ratio:.1%}) @ {current_price:.2f}",
            'confidence': confidence,
            'recent_high': recent_high,
            'recent_low': recent_low,
            'pullback_ratio': pullback_ratio,
            'fib_levels': fib_levels,
        }
        
        return signal
    
    def detect_pullback_in_downtrend(self, symbol: str, data: pd.DataFrame,
                                    indicators: Dict) -> Optional[Dict]:
        """
        在下降趋势中检测反弹卖出信号
        """
        if symbol in self.positions:
            logger.info(f"{symbol} 已有持仓，跳过卖出信号")
            return None
        
        # if len(data) < self.config['pullback_lookback'] + self.config['trend_ma_period']:
        #     logger.info(f"{symbol} 数据不足: {len(data)} < {self.config['pullback_lookback'] + self.config['trend_ma_period']}")
        #     return None
        
        # 识别趋势
        trend, trend_strength, current_price = self.identify_trend(data)
        if trend != 'DOWNTREND':
            logger.info(f"{symbol} 非下降趋势 ({trend})")
            return None
        # 要求趋势强度达到阈值，避免在非常弱的波动中开空
        if trend_strength < self.config.get('strong_trend_threshold', 0.01):
            logger.debug(f"{symbol} 趋势强度不足 ({trend_strength:.2%} < {self.config['strong_trend_threshold']:.2%})")
            return None
        
        # 找出近期高低点
        lookback = self.config['pullback_lookback']
        recent_high = data['High'].iloc[-lookback:].max()
        recent_low = data['Low'].iloc[-lookback:].min()
        
        # 计算斐波那契反弹位
        fib_levels = self.calculate_fibonacci_levels(recent_high, recent_low)
        swing_range = recent_high - recent_low
        
        # 检查当前价格是否处于反弹位
        rebound_amount = current_price - recent_low
        rebound_ratio = rebound_amount / swing_range if swing_range > 0 else 0
        
        min_ratio, max_ratio = self.config['pullback_sell_ratio']
        
        logger.info(f"  {symbol} 下降趋势反弹分析: 高{recent_high:.2f} 低{recent_low:.2f} 当前{current_price:.2f} 反弹幅度{rebound_ratio:.1%} (目标{min_ratio:.1%}-{max_ratio:.1%})")
        
        # 确认反弹到目标位置
        if not (min_ratio <= rebound_ratio <= max_ratio):
            logger.info(f"{symbol} 反弹幅度不在目标范围:min_ratio--{min_ratio:.1%} rebound_ratio--{rebound_ratio:.1%} max_ratio--{max_ratio:.1%}")
            return None
        
        # 确认反弹幅度最小要求
        if rebound_ratio < self.config['pullback_threshold'] / swing_range:
            logger.info(f"{symbol} 反弹幅度小于最小要求")
            return None
        
        # 成交量确认
        if self.config['volume_confirmation']:
            if len(data) >= 10:
                avg_volume = data['Volume'].iloc[-10:].mean()
                current_volume = data['Volume'].iloc[-1]
                volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
                if volume_ratio < self.config['min_volume_ratio']:
                    logger.info(f"{symbol} 成交量不足: {volume_ratio:.2f}x--min_volume_ratio {self.config['min_volume_ratio']}")
                    return None
        
        # 计算信号强度
        distance_to_golden = abs(rebound_ratio - 0.618)
        confidence = max(0.3, 0.8 - distance_to_golden * 2)
        
        logger.info(
            f"🔴 {symbol} 下降趋势反弹卖出信号"
            f" | 近期低: {recent_low:.2f}, 当前: {current_price:.2f}, 反弹幅度: {rebound_ratio:.1%}"
            f" | 趋势强度: {trend_strength:.2%}, 置信度: {confidence:.1%}"
        )
        # 置信度门槛过滤，避免过多低质量信号
        if confidence < self.config.get('min_confidence', 0.5):
            logger.info(f"{symbol} 信号置信度过低: {confidence:.1%} < {self.config.get('min_confidence', 0.5):.1%}")
            return None
        
        signal = {
            'symbol': symbol,
            'signal_type': 'PULLBACK_SELL_DOWNTREND',
            'action': 'SELL',
            'price': current_price,
            'reason': f"下降趋势反弹 ({rebound_ratio:.1%}) @ {current_price:.2f}",
            'confidence': confidence,
            'recent_high': recent_high,
            'recent_low': recent_low,
            'rebound_ratio': rebound_ratio,
            'fib_levels': fib_levels,
        }
        
        return signal
    
    def generate_signals(self, symbol: str, data: pd.DataFrame,
                        indicators: Dict) -> List[Dict]:
        """生成交易信号"""
        signals = []
        # 基本数据检查
        if data.empty:
            logger.info(f"{symbol} 数据不足，无法生成信号")
            return signals
            
        # if len(data) < self.config['pullback_lookback'] + self.config['trend_ma_period']:
        #     logger.info(f"{symbol} 数据不足，无法生成信号- len(){len(data)}-需要至少 {self.config['pullback_lookback'] + self.config['trend_ma_period']} 根K线")
        #     return signals
        # 获取ATR用于仓位管理
        atr = indicators.get('ATR', data['Close'].std() * 0.01)
        
        # 检查是否有持仓需要卖出
        if symbol in self.positions:
            current_price = data['Close'].iloc[-1]
            exit_signal = self.check_exit_conditions(symbol, current_price)
            if exit_signal:
                exit_signal['position_size'] = abs(self.positions[symbol]['size'])
                logger.info(f"🔴 {symbol} 卖出信号: {exit_signal['reason']}")
                signals.append(exit_signal)
        
        # 只在没有持仓时生成入场信号
        if symbol not in self.positions:
            # 上升趋势回撤买入
            buy_signal = self.detect_pullback_in_uptrend(symbol, data, indicators)
            if buy_signal:
                signal_hash = self._generate_signal_hash(buy_signal)
                if not self._is_signal_cooldown(signal_hash) and signal_hash not in self.executed_signals:
                    buy_signal['position_size'] = self.calculate_position_size(buy_signal, atr)
                    buy_signal['signal_hash'] = signal_hash
                    if buy_signal['position_size'] > 0:
                        logger.info(f"✅ {symbol} 生成买入信号: 数量 {buy_signal['position_size']}")
                        signals.append(buy_signal)
                        self.executed_signals.add(signal_hash)
                else:
                    logger.info(f"{symbol} 信号在冷却期或已执行")
            
            # 下降趋势反弹卖出（做空）
            sell_signal = self.detect_pullback_in_downtrend(symbol, data, indicators)
            if sell_signal:
                signal_hash = self._generate_signal_hash(sell_signal)
                if not self._is_signal_cooldown(signal_hash) and signal_hash not in self.executed_signals:
                    sell_signal['position_size'] = self.calculate_position_size(sell_signal, atr)
                    sell_signal['signal_hash'] = signal_hash
                    if sell_signal['position_size'] > 0:
                        logger.info(f"✅ {symbol} 生成卖出信号: 数量 {sell_signal['position_size']}")
                        signals.append(sell_signal)
                        self.executed_signals.add(signal_hash)
                else:
                    logger.info(f"{symbol} 信号在冷却期或已执行")
        
        # 记录信号统计
        if signals:
            self.signals_generated += len(signals)
            logger.info(f"📊 {symbol} 共生成 {len(signals)} 个信号")
        
        return signals
    
    def check_exit_conditions(self, symbol: str, current_price: float,
                             current_time: datetime = None) -> Optional[Dict]:
        """检查卖出条件"""
        # if symbol not in self.positions:
        #     logger.info(f"{symbol} 无持仓，无法检查卖出条件")
        #     return None
        
        if current_time is None:
            current_time = datetime.now()
        
        position = self.positions[symbol]
        avg_cost = position['avg_cost']
        position_size = position['size']
        entry_time = position.get('entry_time', current_time - timedelta(days=1))
        
        # 计算盈亏
        if position_size > 0:
            price_change_pct = (current_price - avg_cost) / avg_cost
        else:
            price_change_pct = (avg_cost - current_price) / avg_cost
        
        # 止损
        if price_change_pct <= -self.config['stop_loss_pct']:
            return {
                'symbol': symbol,
                'signal_type': 'STOP_LOSS',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"止损: 亏损{price_change_pct*100:.1f}%",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100
            }
        
        # 止盈
        if price_change_pct >= self.config['take_profit_pct']:
            return {
                'symbol': symbol,
                'signal_type': 'TAKE_PROFIT',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"止盈: 盈利{price_change_pct*100:.1f}%",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100
            }
        
        # 最大持仓时间
        holding_days = (current_time - entry_time).total_seconds() / (24 * 3600)
        if holding_days > self.config['max_holding_days']:
            return {
                'symbol': symbol,
                'signal_type': 'MAX_HOLDING',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"超时平仓: 持仓{holding_days:.1f}天",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100
            }
        
        # 追踪止损
        trailing_stop_pct = self.config.get('trailing_stop_pct', 0.02)
        
        if position_size > 0:
            # 多头追踪止损
            # 更新最高价 (初始化默认为0，确保第一时间更新)
            highest_price = position.get('highest_price', 0.0)
            if current_price > highest_price:
                self.positions[symbol]['highest_price'] = current_price
                highest_price = current_price
            
            # 检查回撤
            # 注意: 只有当价格高于成本价(有盈利)一定幅度后才激活追踪止损，或者直接全程追踪
            # 这里简化为：只要回撤达到比例就止损，不管是否盈利（保护利润 + 限制亏损）
            # 但通常追踪止损是为了锁住利润。如果为了限制亏损，已有 stop_loss_pct
            # 改进：如果当前最高价 > 平均成本，才触发追踪逻辑，避免在水下波动时过早止损（水下由硬止损负责）
            if highest_price > avg_cost * 1.01: # 至少有1%利润后才开始追踪
                 drawdown = (highest_price - current_price) / highest_price
                 if drawdown >= trailing_stop_pct:
                    return {
                        'symbol': symbol,
                        'signal_type': 'TRAILING_STOP',
                        'action': 'SELL',
                        'price': current_price,
                        'reason': f"追踪止损:最高{highest_price:.2f}回撤{drawdown*100:.1f}%",
                        'position_size': abs(position_size),
                        'profit_pct': price_change_pct * 100
                    }
        else:
            # 空头追踪止损
            # 更新最低价 (初始化默认为无穷大)
            lowest_price = position.get('lowest_price', float('inf'))
            if current_price < lowest_price:
                self.positions[symbol]['lowest_price'] = current_price
                lowest_price = current_price
            
            # 检查反弹
            if lowest_price < avg_cost * 0.99: # 至少有1%利润后才开始追踪
                rebound = (current_price - lowest_price) / lowest_price
                if rebound >= trailing_stop_pct:
                    return {
                        'symbol': symbol,
                        'signal_type': 'TRAILING_STOP',
                        'action': 'BUY',
                        'price': current_price,
                        'reason': f"追踪止损:最低{lowest_price:.2f}反弹{rebound*100:.1f}%",
                        'position_size': abs(position_size),
                        'profit_pct': price_change_pct * 100
                    }
        
        return None
