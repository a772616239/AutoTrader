#!/usr/bin/env python3
"""
A25: 协整配对交易策略 (Cointegration Pairs Trading Strategy)
基于协整检验的统计套利策略
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from statsmodels.tsa.stattools import coint
from strategies.base_strategy import BaseStrategy
from strategies import indicators

logger = logging.getLogger(__name__)

class A25PairsTradingStrategy(BaseStrategy):
    """协整配对交易策略 - A25"""

    def _default_config(self) -> Dict:
        """默认配置"""
        from config import CONFIG
        strategy_key = 'strategy_a25'
        if strategy_key in CONFIG:
            return CONFIG[strategy_key]
        else:
            return {
                # 资金管理
                'initial_capital': 50000.0,
                'risk_per_trade': 0.02,  # 2% 单笔风险
                'max_position_size': 0.1,  # 10% 最大仓位
                'per_trade_notional_cap': 10000.0,
                'max_position_notional': 50000.0,

                # 协整参数
                'coint_period': 252,  # 协整检验期间 (1年)
                'pvalue_threshold': 0.05,  # p值阈值
                'zscore_entry': 2.0,  # 入场Z分数
                'zscore_exit': 0.5,   # 出场Z分数

                # 风险管理
                'stop_loss_pct': 0.05,  # 5% 止损
                'take_profit_pct': 0.10,  # 10% 止盈
                'max_holding_days': 30,  # 最大持有30天
                'trailing_stop_pct': 0.03,  # 3% 追踪止损

                # 交易过滤
                'trading_hours_only': True,
                'avoid_earnings': True,
                'min_volume_threshold': 500000,  # 最小成交量
                'min_price': 10.0,
                'max_price': None,

                # 防重复交易
                'signal_cooldown_minutes': 60,  # 60分钟冷却

                # IB交易参数
                'ib_order_type': 'MKT',
                'ib_limit_offset': 0.01,
            }

    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return "A25 Cointegration Pairs Trading Strategy"

    def find_cointegrated_pair(self, symbol1: str, symbol2: str, data1: pd.DataFrame,
                              data2: pd.DataFrame) -> Optional[Dict]:
        """检查两只股票是否协整"""
        try:
            # 确保数据长度一致
            min_len = min(len(data1), len(data2))
            if min_len < self.config['coint_period']:
                return None

            prices1 = data1['Close'].tail(min_len)
            prices2 = data2['Close'].tail(min_len)

            # 执行协整检验
            _, pvalue, _ = coint(prices1, prices2)

            if pvalue > self.config['pvalue_threshold']:
                return None  # 不协整

            # 计算价差
            spread = prices1 - prices2

            # 计算Z分数
            zscore = indicators.calculate_zscore(spread, window=20)

            return {
                'symbol1': symbol1,
                'symbol2': symbol2,
                'pvalue': pvalue,
                'spread': spread,
                'zscore': zscore,
                'current_spread': spread.iloc[-1],
                'current_zscore': zscore.iloc[-1]
            }

        except Exception as e:
            logger.warning(f"协整检验失败 {symbol1}-{symbol2}: {e}")
            return None

    def detect_buy_signal(self, symbol: str, data: pd.DataFrame,
                          indicators_dict: Dict) -> Optional[Dict]:
        """检测买入信号 - 寻找协整对并检查交易机会"""
        # 这个策略需要两只股票的数据，这里简化处理
        # 在实际应用中，需要从indicators_dict获取配对信息
        return None

    def detect_sell_signal(self, symbol: str, data: pd.DataFrame,
                          indicators_dict: Dict) -> Optional[Dict]:
        """检测卖出信号"""
        if symbol not in self.positions:
            return None

        current_price = data['Close'].iloc[-1]

        # 检查传统退出条件
        position = self.positions[symbol]
        avg_cost = position['avg_cost']

        # 计算Z分数退出条件（需要配对信息）
        # 这里简化处理，使用传统退出条件

        # 止损
        price_change_pct = (current_price - avg_cost) / avg_cost
        if abs(price_change_pct) >= self.config['stop_loss_pct']:
            return {
                'symbol': symbol,
                'signal_type': 'PAIRS_STOP_LOSS',
                'action': 'SELL',
                'price': current_price,
                'confidence': 0.9,
                'reason': f'配对交易止损: {price_change_pct*100:.1f}%',
                'position_size': abs(self.positions[symbol]['size']),
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

        # 这个策略主要用于配对交易，需要特殊的配对发现机制
        # 这里返回空信号，实际使用时需要扩展

        return signals

    def check_pair_trading_opportunity(self, symbol1: str, symbol2: str,
                                     data1: pd.DataFrame, data2: pd.DataFrame) -> List[Dict]:
        """检查配对交易机会"""
        signals = []

        try:
            pair_info = self.find_cointegrated_pair(symbol1, symbol2, data1, data2)

            if not pair_info:
                return signals

            current_zscore = pair_info['current_zscore']

            # 检查买入机会 (做空高估，买入低估)
            if current_zscore >= self.config['zscore_entry']:
                # 卖出symbol1，买入symbol2
                signal1 = {
                    'symbol': symbol1,
                    'signal_type': 'PAIRS_SELL',
                    'action': 'SELL',
                    'price': data1['Close'].iloc[-1],
                    'confidence': min(0.5 + abs(current_zscore) / 4, 0.9),
                    'reason': f'配对交易: {symbol1}-{symbol2}, Z分数={current_zscore:.2f}',
                    'pair_symbol': symbol2,
                    'zscore': current_zscore,
                    'timestamp': datetime.now()
                }
                signals.append(signal1)

                signal2 = {
                    'symbol': symbol2,
                    'signal_type': 'PAIRS_BUY',
                    'action': 'BUY',
                    'price': data2['Close'].iloc[-1],
                    'confidence': min(0.5 + abs(current_zscore) / 4, 0.9),
                    'reason': f'配对交易: {symbol2}-{symbol1}, Z分数={current_zscore:.2f}',
                    'pair_symbol': symbol1,
                    'zscore': current_zscore,
                    'timestamp': datetime.now()
                }
                signals.append(signal2)

            # 检查卖出机会 (做多高估，做空低估)
            elif current_zscore <= -self.config['zscore_entry']:
                # 买入symbol1，卖出symbol2
                signal1 = {
                    'symbol': symbol1,
                    'signal_type': 'PAIRS_BUY',
                    'action': 'BUY',
                    'price': data1['Close'].iloc[-1],
                    'confidence': min(0.5 + abs(current_zscore) / 4, 0.9),
                    'reason': f'配对交易: {symbol1}-{symbol2}, Z分数={current_zscore:.2f}',
                    'pair_symbol': symbol2,
                    'zscore': current_zscore,
                    'timestamp': datetime.now()
                }
                signals.append(signal1)

                signal2 = {
                    'symbol': symbol2,
                    'signal_type': 'PAIRS_SELL',
                    'action': 'SELL',
                    'price': data2['Close'].iloc[-1],
                    'confidence': min(0.5 + abs(current_zscore) / 4, 0.9),
                    'reason': f'配对交易: {symbol2}-{symbol1}, Z分数={current_zscore:.2f}',
                    'pair_symbol': symbol1,
                    'zscore': current_zscore,
                    'timestamp': datetime.now()
                }
                signals.append(signal2)

        except Exception as e:
            logger.warning(f"配对交易机会检查失败 {symbol1}-{symbol2}: {e}")

        return signals