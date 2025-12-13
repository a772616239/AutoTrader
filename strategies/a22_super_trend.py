#!/usr/bin/env python3
"""
A22: 超级趋势策略 (Super Trend Strategy)
基于ATR的趋势跟踪策略，特别适用于趋势市场
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy
from strategies import indicators

logger = logging.getLogger(__name__)

class A22SuperTrendStrategy(BaseStrategy):
    """超级趋势策略 - A22"""

    def _default_config(self) -> Dict:
        """默认配置"""
        from config import CONFIG
        strategy_key = 'strategy_a22'
        if strategy_key in CONFIG:
            return CONFIG[strategy_key]
        else:
            # 降级到硬编码默认值
            return {
                # 资金管理
                'initial_capital': 50000.0,
                'risk_per_trade': 0.015,  # 1.5% 单笔风险
                'max_position_size': 0.08,  # 8% 最大仓位
                'per_trade_notional_cap': 5000.0,
                'max_position_notional': 40000.0,

                # 超级趋势参数
                'atr_period': 14,  # ATR周期
                'factor': 3.0,  # 乘数因子
                'trend_confirmation': 2,  # 趋势确认周期
                'min_trend_strength': 0.0005,  # 最小趋势强度（放宽限制）

                # 风险管理
                'stop_loss_pct': 0.03,  # 3% 止损
                'take_profit_pct': 0.06,  # 6% 止盈
                'max_holding_days': 7,  # 最大持有7天
                'trailing_stop_pct': 0.02,  # 2% 追踪止损

                # 交易过滤
                'trading_hours_only': True,
                'avoid_earnings': True,
                'min_volume_threshold': 50000,  # 最小成交量（放宽限制）
                'min_price': 5.0,
                'max_price': None,

                # 防重复交易
                'signal_cooldown_minutes': 15,  # 15分钟冷却

                # IB交易参数
                'ib_order_type': 'MKT',
                'ib_limit_offset': 0.01,
            }

    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return "A22 Super Trend Strategy"

    def detect_buy_signal(self, symbol: str, data: pd.DataFrame,
                         indicators_dict: Dict) -> Optional[Dict]:
        """检测买入信号"""
        min_required = self.config['atr_period'] + 10
        if len(data) < min_required:
            return None

        if symbol in self.positions:
            return None

        current_price = data['Close'].iloc[-1]
        prev_price = data['Close'].iloc[-2]

        # 计算超级趋势
        super_trend, trend_direction = indicators.calculate_super_trend(
            data['High'], data['Low'], data['Close'],
            self.config['atr_period'], self.config['factor']
        )

        current_st = super_trend.iloc[-1]
        prev_st = super_trend.iloc[-2]
        current_trend = trend_direction.iloc[-1]
        prev_trend = trend_direction.iloc[-2]

        # 买入信号: 价格突破超级趋势线 (简化的突破逻辑)
        # 核心条件: 价格从ST线下方突破到ST线上方
        buy_signal = (prev_price <= prev_st and current_price > current_st)

        if not buy_signal:
            return None

        # 额外的趋势确认 (可选)
        # 如果当前趋势不是上涨，可以选择更保守
        if current_trend != 1:
            logger.info(f"⚠️ {symbol} 价格突破但趋势未确认 (趋势:{current_trend})")
            # 暂时允许突破信号，即使趋势未确认

        # 成交量确认
        from config import CONFIG
        skip_volume_check = CONFIG.get('trading', {}).get('skip_volume_check', False)
        if not skip_volume_check and 'Volume' in data.columns:
            avg_volume = data['Volume'].rolling(10).mean().iloc[-1]
            current_volume = data['Volume'].iloc[-1]
            if current_volume < avg_volume * 1.1:  # 成交量至少放大10%（放宽限制）
                return None

        # 价格过滤
        if current_price < self.config['min_price']:
            return None
        if self.config['max_price'] and current_price > self.config['max_price']:
            return None

        # 计算趋势强度
        trend_strength = abs(current_st - prev_st) / current_price
        if trend_strength < self.config['min_trend_strength']:
            return None

        # 计算置信度
        confidence = min(0.5 + trend_strength * 50, 0.9)  # 基于趋势强度

        logger.info(f"🟢 {symbol} A22买入信号 - 价格:{current_price:.2f}, 超级趋势:{current_st:.2f}, 强度:{trend_strength:.4f}")

        signal = {
            'symbol': symbol,
            'signal_type': 'SUPER_TREND_BUY',
            'action': 'BUY',
            'price': current_price,
            'confidence': confidence,
            'reason': f'超级趋势突破买入: ST={current_st:.2f}, 强度={trend_strength:.4f}',
            'trend_strength': trend_strength,
            'super_trend': current_st,
            'timestamp': datetime.now()
        }

        # 计算仓位大小
        atr = indicators.calculate_atr(data['High'], data['Low'], data['Close']).iloc[-1]
        signal['position_size'] = self.calculate_position_size(signal, atr)

        if signal['position_size'] <= 0:
            return None

        signal_hash = self._generate_signal_hash(signal)
        signal['signal_hash'] = signal_hash

        return signal

    def detect_sell_signal(self, symbol: str, data: pd.DataFrame,
                         indicators_dict: Dict) -> Optional[Dict]:
        """检测卖出信号"""
        if symbol not in self.positions:
            return None

        current_price = data['Close'].iloc[-1]
        prev_price = data['Close'].iloc[-2]

        # 计算超级趋势
        super_trend, trend_direction = indicators.calculate_super_trend(
            data['High'], data['Low'], data['Close'],
            self.config['atr_period'], self.config['factor']
        )

        current_st = super_trend.iloc[-1]
        prev_st = super_trend.iloc[-2]
        current_trend = trend_direction.iloc[-1]
        prev_trend = trend_direction.iloc[-2]

        # 卖出信号: 价格跌破超级趋势线 (简化的跌破逻辑)
        # 核心条件: 价格从ST线上方跌破到ST线下方
        sell_signal = (prev_price >= prev_st and current_price < current_st)

        if sell_signal:
            confidence = 0.8  # 趋势反转信号较高置信度
            reason = f'超级趋势突破卖出: ST={current_st:.2f}'

            logger.info(f"🔴 {symbol} A22卖出信号 - 价格:{current_price:.2f}, 超级趋势:{current_st:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'SUPER_TREND_SELL',
                'action': 'SELL',
                'price': current_price,
                'confidence': confidence,
                'reason': reason,
                'position_size': abs(self.positions[symbol]['size']),
                'super_trend': current_st,
                'timestamp': datetime.now()
            }

        return None

    def generate_signals(self, symbol: str, data: pd.DataFrame,
                        indicators: Dict) -> List[Dict]:
        """生成交易信号"""
        signals = []

        # 基本数据检查
        if data.empty or len(data) < 30:
            return signals

        # 优先检查持仓的退出条件
        if symbol in self.positions:
            current_time = datetime.now()
            current_price = data['Close'].iloc[-1]

            # 优先检查强制止损止盈
            forced_exit = self.check_forced_exit_conditions(symbol, current_price, current_time, data)
            if forced_exit:
                signals.append(forced_exit)
                return signals  # 强制退出直接返回

            exit_signal = self.detect_sell_signal(symbol, data, indicators)
            if exit_signal:
                signals.append(exit_signal)
                return signals  # 触发卖出直接返回

            # 检查传统退出条件
            traditional_exit = self.check_exit_conditions(symbol, current_price)
            if traditional_exit:
                signals.append(traditional_exit)
                return signals

        # 没有持仓时检查买入信号
        else:
            buy_signal = self.detect_buy_signal(symbol, data, indicators)
            if buy_signal:
                signals.append(buy_signal)

        # 记录信号统计
        if signals:
            self.signals_generated += len(signals)

        return signals

    def check_exit_conditions(self, symbol: str, current_price: float,
                            current_time: datetime = None) -> Optional[Dict]:
        """
        检查传统退出条件
        """
        if symbol not in self.positions:
            return None

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

        # 最大持有时间
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

        return None