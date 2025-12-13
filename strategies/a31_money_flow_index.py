#!/usr/bin/env python3
"""
A31: Money Flow Index策略 (Money Flow Index Strategy)
基于Money Flow Index动量指标的交易策略
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy
from strategies import indicators

logger = logging.getLogger(__name__)

class A31MoneyFlowIndexStrategy(BaseStrategy):
    """Money Flow Index策略 - A31"""

    def _default_config(self) -> Dict:
        """默认配置"""
        from config import CONFIG
        strategy_key = 'strategy_a31'
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

                # Money Flow Index参数
                'mfi_period': 14,  # MFI周期
                'overbought_level': 75,  # 超买水平（放宽限制）
                'oversold_level': 25,   # 超卖水平（放宽限制）

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
        return "A31 Money Flow Index Strategy"

    def detect_buy_signal(self, symbol: str, data: pd.DataFrame,
                          indicators_dict: Dict) -> Optional[Dict]:
        """检测买入信号"""
        min_required = self.config['mfi_period'] + 10
        if len(data) < min_required:
            return None

        if symbol in self.positions:
            return None

        current_price = data['Close'].iloc[-1]

        # 计算Money Flow Index
        mfi = indicators.calculate_money_flow_index(
            data['High'], data['Low'], data['Close'], data['Volume'], self.config['mfi_period']
        )

        current_mfi = mfi.iloc[-1]
        prev_mfi = mfi.iloc[-2]

        # 买入信号: MFI从超卖区域向上突破
        buy_signal = (prev_mfi <= self.config['oversold_level'] and
                     current_mfi > self.config['oversold_level'])

        if not buy_signal:
            return None

        # 额外的动量确认
        price_change_3d = (current_price - data['Close'].iloc[-4]) / data['Close'].iloc[-4]
        if price_change_3d < 0.005:  # 3日价格至少上涨0.5%
            return None

        # 成交量确认 - MFI本身就是成交量指标，这里检查成交量变化
        from config import CONFIG
        skip_volume_check = CONFIG.get('trading', {}).get('skip_volume_check', False)
        if not skip_volume_check:
            volume_change = (data['Volume'].iloc[-1] - data['Volume'].iloc[-5:-1].mean()) / data['Volume'].iloc[-5:-1].mean()
            if volume_change < 0.1:  # 成交量至少增加10%
                return None

        # 价格过滤
        if current_price < self.config['min_price']:
            return None
        if self.config['max_price'] and current_price > self.config['max_price']:
            return None

        # 计算置信度 - 基于MFI强度和成交量确认
        mfi_strength = min(abs(current_mfi - 50) / 50, 1.0)  # 距离50线的距离
        confidence = min(0.5 + mfi_strength * 0.3 + volume_change * 2, 0.9)

        logger.info(f"🟢 {symbol} A31买入信号 - MFI:{current_mfi:.2f}, 价格:{current_price:.2f}, 成交量变化:{volume_change:.2%}, 置信度:{confidence:.2f}")

        signal = {
            'symbol': symbol,
            'signal_type': 'MFI_BUY',
            'action': 'BUY',
            'price': current_price,
            'confidence': confidence,
            'reason': f'MFI买入: 从{prev_mfi:.2f}突破到{current_mfi:.2f}',
            'money_flow_index': current_mfi,
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

        # 计算Money Flow Index
        mfi = indicators.calculate_money_flow_index(
            data['High'], data['Low'], data['Close'], data['Volume'], self.config['mfi_period']
        )

        current_mfi = mfi.iloc[-1]
        prev_mfi = mfi.iloc[-2]

        # 卖出信号: MFI从超买区域向下突破
        sell_signal = (prev_mfi >= self.config['overbought_level'] and
                      current_mfi < self.config['overbought_level'])

        if sell_signal:
            confidence = 0.8
            reason = f'MFI卖出: 从{prev_mfi:.2f}跌破到{current_mfi:.2f}'

            logger.info(f"🔴 {symbol} A31卖出信号 - MFI:{current_mfi:.2f}, 价格:{current_price:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'MFI_SELL',
                'action': 'SELL',
                'price': current_price,
                'confidence': confidence,
                'reason': reason,
                'position_size': abs(self.positions[symbol]['size']),
                'money_flow_index': current_mfi,
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