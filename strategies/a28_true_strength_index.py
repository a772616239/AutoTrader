#!/usr/bin/env python3
"""
A28: True Strength Index策略 (True Strength Index Strategy)
基于True Strength Index动量指标的交易策略
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy
from strategies import indicators

logger = logging.getLogger(__name__)

class A28TrueStrengthIndexStrategy(BaseStrategy):
    """True Strength Index策略 - A28"""

    def _default_config(self) -> Dict:
        """默认配置"""
        from config import CONFIG
        strategy_key = 'strategy_a28'
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

                # True Strength Index参数
                'tsi_r_period': 25,  # 第一次平滑周期
                'tsi_s_period': 13,  # 第二次平滑周期
                'overbought_level': 25,  # 超买水平
                'oversold_level': -25,  # 超卖水平

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
        return "A28 True Strength Index Strategy"

    def detect_buy_signal(self, symbol: str, data: pd.DataFrame,
                          indicators_dict: Dict) -> Optional[Dict]:
        """检测买入信号"""
        min_required = self.config['tsi_r_period'] + self.config['tsi_s_period'] + 10
        if len(data) < min_required:
            return None

        if symbol in self.positions:
            return None

        current_price = data['Close'].iloc[-1]

        # 计算True Strength Index
        tsi = indicators.calculate_true_strength_index(
            data['Close'], self.config['tsi_r_period'], self.config['tsi_s_period']
        )

        current_tsi = tsi.iloc[-1]
        prev_tsi = tsi.iloc[-2]

        # 买入信号: TSI从超卖区域向上突破
        buy_signal = (prev_tsi <= self.config['oversold_level'] and
                     current_tsi > self.config['oversold_level'])

        if not buy_signal:
            return None

        # 检查TSI动量 - 确保是强势突破
        tsi_change = current_tsi - prev_tsi
        if tsi_change < 2:  # TSI至少上涨2点
            return None

        # 价格动量确认
        price_change_5d = (current_price - data['Close'].iloc[-6]) / data['Close'].iloc[-6]
        if price_change_5d < 0.01:  # 5日价格至少上涨1%
            return None

        # 成交量确认
        if 'Volume' in data.columns:
            avg_volume = data['Volume'].rolling(10).mean().iloc[-1]
            current_volume = data['Volume'].iloc[-1]
            if current_volume < avg_volume * 1.2:  # 成交量至少放大20%
                return None

        # 价格过滤
        if current_price < self.config['min_price']:
            return None
        if self.config['max_price'] and current_price > self.config['max_price']:
            return None

        # 计算置信度 - 基于TSI强度和价格动量
        tsi_strength = abs(current_tsi) / 50  # 标准化到0-1
        confidence = min(0.5 + tsi_strength * 0.3 + price_change_5d * 5, 0.9)

        logger.info(f"🟢 {symbol} A28买入信号 - TSI:{current_tsi:.2f}, 价格:{current_price:.2f}, 置信度:{confidence:.2f}")

        signal = {
            'symbol': symbol,
            'signal_type': 'TSI_BUY',
            'action': 'BUY',
            'price': current_price,
            'confidence': confidence,
            'reason': f'TSI买入: 从{prev_tsi:.2f}突破到{current_tsi:.2f}',
            'true_strength_index': current_tsi,
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

        # 计算True Strength Index
        tsi = indicators.calculate_true_strength_index(
            data['Close'], self.config['tsi_r_period'], self.config['tsi_s_period']
        )

        current_tsi = tsi.iloc[-1]
        prev_tsi = tsi.iloc[-2]

        # 卖出信号: TSI从超买区域向下突破
        sell_signal = (prev_tsi >= self.config['overbought_level'] and
                      current_tsi < self.config['overbought_level'])

        if sell_signal:
            confidence = 0.8
            reason = f'TSI卖出: 从{prev_tsi:.2f}跌破到{current_tsi:.2f}'

            logger.info(f"🔴 {symbol} A28卖出信号 - TSI:{current_tsi:.2f}, 价格:{current_price:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'TSI_SELL',
                'action': 'SELL',
                'price': current_price,
                'confidence': confidence,
                'reason': reason,
                'position_size': abs(self.positions[symbol]['size']),
                'true_strength_index': current_tsi,
                'timestamp': datetime.now()
            }

        return None

    def generate_signals(self, symbol: str, data: pd.DataFrame,
                        indicators: Dict) -> List[Dict]:
        """生成交易信号"""
        signals = []

        # 基本数据检查
        if data.empty or len(data) < 50:
            return signals

        # 优先检查持仓的退出条件
        if symbol in self.positions:
            exit_signal = self.detect_sell_signal(symbol, data, indicators)
            if exit_signal:
                signals.append(exit_signal)
                return signals  # 触发卖出直接返回

            # 检查传统退出条件
            current_price = data['Close'].iloc[-1]
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