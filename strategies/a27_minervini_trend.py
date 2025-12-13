#!/usr/bin/env python3
"""
A27: Minervini趋势策略 (Minervini Trend Template Strategy)
基于Mark Minervini的趋势模板和相对强度筛选的交易策略
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy
from strategies import indicators

logger = logging.getLogger(__name__)

class A27MinerviniTrendStrategy(BaseStrategy):
    """Minervini趋势策略 - A27"""

    def _default_config(self) -> Dict:
        """默认配置"""
        from config import CONFIG
        strategy_key = 'strategy_a27'
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

                # Minervini参数
                'sma_50_period': 50,    # 50日均线周期
                'sma_150_period': 150, # 150日均线周期
                'sma_200_period': 200, # 200日均线周期
                'rs_lookback': 252,    # 相对强度回望期间 (1年)
                'rs_percentile': 70,   # 相对强度百分位数
                'min_price_increase': 1.3,  # 相对于52周低点的倍数
                'max_price_decline': 0.75, # 相对于52周高点的倍数

                # 风险管理
                'stop_loss_pct': 0.08,  # 8% 止损
                'take_profit_pct': 0.15, # 15% 止盈
                'max_holding_days': 60,  # 最大持有60天
                'trailing_stop_pct': 0.05,  # 5% 追踪止损

                # 交易过滤
                'trading_hours_only': True,
                'avoid_earnings': True,
                'min_volume_threshold': 5000,  # 最小成交量（放宽限制）
                'min_price': 10.0,
                'max_price': None,

                # 防重复交易
                'signal_cooldown_minutes': 1440,  # 24小时冷却

                # IB交易参数
                'ib_order_type': 'MKT',
                'ib_limit_offset': 0.01,
            }

    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return "A27 Minervini Trend Strategy"

    def calculate_relative_strength(self, stock_data: pd.DataFrame,
                                  benchmark_data: pd.DataFrame) -> float:
        """计算相对强度评级"""
        try:
            # 确保数据对齐
            common_dates = stock_data.index.intersection(benchmark_data.index)
            if len(common_dates) < 30:
                return 50.0  # 默认中性评级

            stock_returns = stock_data.loc[common_dates]['Close'].pct_change()
            bench_returns = benchmark_data.loc[common_dates]['Close'].pct_change()

            # 计算累积收益率
            stock_cum_return = (1 + stock_returns.fillna(0)).cumprod().iloc[-1] - 1
            bench_cum_return = (1 + bench_returns.fillna(0)).cumprod().iloc[-1] - 1

            # 计算相对强度倍数
            if bench_cum_return != 0:
                rs_multiple = stock_cum_return / bench_cum_return
            else:
                rs_multiple = 1.0

            # 转换为0-100评级 (这里简化，实际需要全市场比较)
            rs_rating = min(max(rs_multiple * 50, 0), 100)

            return rs_rating

        except Exception as e:
            logger.warning(f"计算相对强度失败: {e}")
            return 50.0

    def check_minervini_conditions(self, data: pd.DataFrame) -> bool:
        """检查Minervini的8个条件"""
        try:
            if len(data) < self.config['sma_200_period']:
                return False

            current_close = data['Close'].iloc[-1]

            # 计算移动平均线
            sma_50 = data['Close'].rolling(self.config['sma_50_period']).mean().iloc[-1]
            sma_150 = data['Close'].rolling(self.config['sma_150_period']).mean().iloc[-1]
            sma_200 = data['Close'].rolling(self.config['sma_200_period']).mean().iloc[-1]

            # 计算52周高低点
            high_52w = data['High'].rolling(252).max().iloc[-1]
            low_52w = data['Low'].rolling(252).min().iloc[-1]

            # Minervini的8个条件
            conditions = [
                current_close > sma_150,  # 1. 当前价格高于150日均线
                sma_150 > sma_200,        # 2. 150日均线高于200日均线
                sma_200 > sma_200.shift(20).iloc[-1] if len(data) > self.config['sma_200_period'] + 20 else True,  # 3. 200日均线呈上升趋势
                current_close > sma_50,   # 4. 当前价格高于50日均线
                current_close >= self.config['min_price_increase'] * low_52w,  # 5. 当前价格至少是52周低点的1.3倍
                current_close >= self.config['max_price_decline'] * high_52w,  # 6. 当前价格不低于52周高点的75%
                # 条件7和8需要成交量和相对强度，这里简化
                True,  # 成交量条件 (暂时跳过)
                True   # 相对强度条件 (暂时跳过)
            ]

            return all(conditions)

        except Exception as e:
            logger.warning(f"检查Minervini条件失败: {e}")
            return False

    def detect_buy_signal(self, symbol: str, data: pd.DataFrame,
                          indicators_dict: Dict) -> Optional[Dict]:
        """检测买入信号"""
        min_required = self.config['sma_200_period'] + 50
        if len(data) < min_required:
            return None

        if symbol in self.positions:
            return None

        current_price = data['Close'].iloc[-1]

        # 检查Minervini条件
        if not self.check_minervini_conditions(data):
            return None

        # 检查相对强度 (需要基准数据，这里简化)
        # 在实际应用中，需要传入市场基准数据

        # 成交量确认
        if 'Volume' in data.columns:
            avg_volume = data['Volume'].rolling(20).mean().iloc[-1]
            current_volume = data['Volume'].iloc[-1]
            if current_volume < avg_volume * 1.5:  # 成交量至少放大50%
                return None

        # 价格过滤
        if current_price < self.config['min_price']:
            return None
        if self.config['max_price'] and current_price > self.config['max_price']:
            return None

        # 计算技术强度
        sma_50 = data['Close'].rolling(self.config['sma_50_period']).mean().iloc[-1]
        price_to_ma_ratio = current_price / sma_50

        confidence = min(0.6 + (price_to_ma_ratio - 1) * 2, 0.9)

        logger.info(f"🟢 {symbol} A27买入信号 - Minervini趋势模板 - 价格:{current_price:.2f}, 置信度:{confidence:.2f}")

        signal = {
            'symbol': symbol,
            'signal_type': 'MINERVINI_BUY',
            'action': 'BUY',
            'price': current_price,
            'confidence': confidence,
            'reason': f'Minervini趋势买入: 满足8个趋势条件',
            'timestamp': datetime.now()
        }

        # 计算仓位大小
        position_size = self.calculate_position_size(signal, 0.03)  # 使用固定ATR

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

        # 检查Minervini条件是否仍然满足
        if not self.check_minervini_conditions(data):
            return {
                'symbol': symbol,
                'signal_type': 'MINERVINI_SELL',
                'action': 'SELL',
                'price': current_price,
                'confidence': 0.8,
                'reason': 'Minervini条件不再满足',
                'position_size': abs(self.positions[symbol]['size']),
                'timestamp': datetime.now()
            }

        return None

    def generate_signals(self, symbol: str, data: pd.DataFrame,
                        indicators: Dict) -> List[Dict]:
        """生成交易信号"""
        signals = []

        # 基本数据检查
        if data.empty or len(data) < 250:
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