#!/usr/bin/env python3
"""
A29: Stochastic Oscillator策略 (Stochastic Oscillator Strategy)
基于Stochastic Oscillator动量指标的交易策略
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy
from strategies import indicators

logger = logging.getLogger(__name__)

class A29StochasticOscillatorStrategy(BaseStrategy):
    """Stochastic Oscillator策略 - A29"""

    def _default_config(self) -> Dict:
        """默认配置"""
        from config import CONFIG
        strategy_key = 'strategy_a29'
        if strategy_key in CONFIG:
            return CONFIG[strategy_key]
        else:
            return {
                # 资金管理
                'initial_capital': 50000.0,
                'risk_per_trade': 0.015,  # 1.5% 单笔风险
                'max_position_size': 0.08,  # 8% 最大仓位
                'per_trade_notional_cap': 5000.0,
                'max_position_notional': 40000.0,

                # Stochastic Oscillator参数
                'k_period': 14,  # %K周期
                'd_period': 3,   # %D周期
                'overbought_level': 80,  # 超买水平
                'oversold_level': 20,   # 超卖水平

                # 风险管理
                'stop_loss_pct': 0.03,  # 3% 止损
                'take_profit_pct': 0.06,  # 6% 止盈
                'max_holding_days': 10,  # 最大持有10天
                'trailing_stop_pct': 0.02,  # 2% 追踪止损

                # 交易过滤
                'trading_hours_only': True,
                'avoid_earnings': True,
                'min_volume_threshold': 5000,  # 最小成交量（放宽限制）
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
        return "A29 Stochastic Oscillator Strategy"

    def detect_buy_signal(self, symbol: str, data: pd.DataFrame,
                          indicators_dict: Dict) -> Optional[Dict]:
        """检测买入信号"""
        min_required = self.config['k_period'] + self.config['d_period'] + 10
        if len(data) < min_required:
            return None

        if symbol in self.positions:
            return None

        current_price = data['Close'].iloc[-1]

        # 计算Stochastic Oscillator
        stoch_k, stoch_d = indicators.calculate_stochastic_oscillator(
            data['High'], data['Low'], data['Close'],
            self.config['k_period'], self.config['d_period']
        )

        current_k = stoch_k.iloc[-1]
        current_d = stoch_d.iloc[-1]
        prev_k = stoch_k.iloc[-2]
        prev_d = stoch_d.iloc[-2]

        # 买入信号: Stochastic Oscillator从超卖区域向上突破
        # %K和%D都在超卖水平以下，且%D向上穿越%K (黄金交叉)
        buy_signal = (prev_k <= self.config['oversold_level'] and
                     prev_d <= self.config['oversold_level'] and
                     current_k > prev_k and current_d > prev_d)

        if not buy_signal:
            return None

        # 额外的动量确认
        price_change_3d = (current_price - data['Close'].iloc[-4]) / data['Close'].iloc[-4]
        if price_change_3d < 0.005:  # 3日价格至少上涨0.5%
            return None

        # 成交量确认
        from config import CONFIG
        skip_volume_check = CONFIG.get('trading', {}).get('skip_volume_check', False)
        if not skip_volume_check and 'Volume' in data.columns:
            avg_volume = data['Volume'].rolling(10).mean().iloc[-1]
            current_volume = data['Volume'].iloc[-1]
            if current_volume < avg_volume * 1.1:  # 成交量至少放大10%
                return None

        # 价格过滤
        if current_price < self.config['min_price']:
            return None
        if self.config['max_price'] and current_price > self.config['max_price']:
            return None

        # 计算置信度 - 基于Stochastic强度和价格动量
        stoch_strength = min(abs(current_k - 50) / 50, 1.0)  # 距离50线的距离
        confidence = min(0.5 + stoch_strength * 0.3 + price_change_3d * 8, 0.9)

        logger.info(f"🟢 {symbol} A29买入信号 - %K:{current_k:.2f}, %D:{current_d:.2f}, 价格:{current_price:.2f}, 置信度:{confidence:.2f}")

        signal = {
            'symbol': symbol,
            'signal_type': 'STOCHASTIC_BUY',
            'action': 'BUY',
            'price': current_price,
            'confidence': confidence,
            'reason': f'Stochastic买入: %K={current_k:.2f}, %D={current_d:.2f}',
            'stoch_k': current_k,
            'stoch_d': current_d,
            'timestamp': datetime.now()
        }

        # 计算仓位大小
        position_size = self.calculate_position_size(signal, 0.02)  # 使用固定ATR

        if position_size <= 0:
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

        # 计算Stochastic Oscillator
        stoch_k, stoch_d = indicators.calculate_stochastic_oscillator(
            data['High'], data['Low'], data['Close'],
            self.config['k_period'], self.config['d_period']
        )

        current_k = stoch_k.iloc[-1]
        current_d = stoch_d.iloc[-1]
        prev_k = stoch_k.iloc[-2]
        prev_d = stoch_d.iloc[-2]

        # 卖出信号: Stochastic Oscillator从超买区域向下突破
        # %K和%D都在超买水平以上，且%D向下穿越%K (死亡交叉)
        sell_signal = (prev_k >= self.config['overbought_level'] and
                      prev_d >= self.config['overbought_level'] and
                      current_k < prev_k and current_d < prev_d)

        if sell_signal:
            confidence = 0.8
            reason = f'Stochastic卖出: %K={current_k:.2f}, %D={current_d:.2f}'

            logger.info(f"🔴 {symbol} A29卖出信号 - %K:{current_k:.2f}, %D:{current_d:.2f}, 价格:{current_price:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'STOCHASTIC_SELL',
                'action': 'SELL',
                'price': current_price,
                'confidence': confidence,
                'reason': reason,
                'position_size': abs(self.positions[symbol]['size']),
                'stoch_k': current_k,
                'stoch_d': current_d,
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