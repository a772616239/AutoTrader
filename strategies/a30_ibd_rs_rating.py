#!/usr/bin/env python3
"""
A30: IBD RS评级策略 (IBD RS Rating Strategy)
基于Investors Business Daily相对强度评级的交易策略
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy
from strategies import indicators

logger = logging.getLogger(__name__)

class A30IBDRSRatingStrategy(BaseStrategy):
    """IBD RS评级策略 - A30"""

    def _default_config(self) -> Dict:
        """默认配置"""
        from config import CONFIG
        strategy_key = 'strategy_a30'
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

                # IBD RS参数
                'rs_lookback_period': 252,  # 相对强度回望期间 (1年)
                'rs_rating_threshold': 70,  # RS评级阈值（放宽限制）
                'momentum_weight': 0.6,     # 近期动量权重
                'trend_weight': 0.4,        # 长期趋势权重

                # 风险管理
                'stop_loss_pct': 0.05,  # 5% 止损
                'take_profit_pct': 0.10, # 10% 止盈
                'max_holding_days': 30,  # 最大持有30天
                'trailing_stop_pct': 0.03,  # 3% 追踪止损

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
        return "A30 IBD RS Rating Strategy"

    def calculate_rs_rating(self, stock_data: pd.DataFrame,
                           benchmark_data: pd.DataFrame) -> float:
        """计算IBD风格的相对强度评级"""
        try:
            # 确保数据对齐
            common_dates = stock_data.index.intersection(benchmark_data.index)
            if len(common_dates) < 60:  # 至少3个月数据
                return 50.0

            stock_prices = stock_data.loc[common_dates]['Close']
            bench_prices = benchmark_data.loc[common_dates]['Close']

            # 计算收益率
            stock_returns = stock_prices.pct_change().dropna()
            bench_returns = bench_prices.pct_change().dropna()

            # 计算累积收益率
            stock_cum_return = (1 + stock_returns).cumprod().iloc[-1] - 1
            bench_cum_return = (1 + bench_returns).cumprod().iloc[-1] - 1

            # 计算近期动量 (最近3个月)
            recent_stock = (1 + stock_returns.tail(63)).cumprod().iloc[-1] - 1  # 约3个月
            recent_bench = (1 + bench_returns.tail(63)).cumprod().iloc[-1] - 1

            # IBD风格的RS计算：结合长期趋势和近期动量
            long_term_rs = stock_cum_return / bench_cum_return if bench_cum_return != 0 else 1.0
            recent_rs = recent_stock / recent_bench if recent_bench != 0 else 1.0

            # 加权平均
            combined_rs = (self.config['momentum_weight'] * recent_rs +
                          self.config['trend_weight'] * long_term_rs)

            # 转换为0-100评级
            rs_rating = min(max(combined_rs * 50 + 50, 0), 100)

            return rs_rating

        except Exception as e:
            logger.warning(f"计算RS评级失败: {e}")
            return 50.0

    def detect_buy_signal(self, symbol: str, data: pd.DataFrame,
                          indicators_dict: Dict) -> Optional[Dict]:
        """检测买入信号"""
        min_required = self.config['rs_lookback_period'] // 4  # 至少3个月数据
        if len(data) < min_required:
            return None

        if symbol in self.positions:
            return None

        current_price = data['Close'].iloc[-1]

        # 这里简化处理，实际应该传入基准数据
        # 假设基准是标普500或其他主要指数
        # 为了演示，我们基于技术指标来近似RS评级

        # 计算技术强度作为RS的代理
        sma_50 = data['Close'].rolling(50).mean().iloc[-1]
        sma_200 = data['Close'].rolling(200).mean().iloc[-1]

        # 强势股票的特征：价格在均线上方，成交量放大
        price_to_ma_ratio = current_price / sma_50
        ma_trend = sma_50 / sma_200

        # 简化的RS评级计算
        rs_proxy = min((price_to_ma_ratio * ma_trend * 25), 100)

        # 买入信号: RS评级足够高
        buy_signal = rs_proxy >= self.config['rs_rating_threshold']

        if not buy_signal:
            return None

        # 额外的技术确认
        # 价格在上升趋势中
        if current_price < sma_50 or sma_50 < sma_200:
            return None

        # 成交量确认
        from config import CONFIG
        skip_volume_check = CONFIG.get('trading', {}).get('skip_volume_check', False)
        if not skip_volume_check and 'Volume' in data.columns:
            avg_volume = data['Volume'].rolling(20).mean().iloc[-1]
            current_volume = data['Volume'].iloc[-1]
            if current_volume < avg_volume * 1.2:  # 成交量放大
                return None

        # 价格过滤
        if current_price < self.config['min_price']:
            return None
        if self.config['max_price'] and current_price > self.config['max_price']:
            return None

        # 计算置信度
        confidence = min(0.6 + (rs_proxy - 80) / 40, 0.9)

        logger.info(f"🟢 {symbol} A30买入信号 - RS评级:{rs_proxy:.1f}, 价格:{current_price:.2f}, 置信度:{confidence:.2f}")

        signal = {
            'symbol': symbol,
            'signal_type': 'IBD_RS_BUY',
            'action': 'BUY',
            'price': current_price,
            'confidence': confidence,
            'reason': f'IBD RS买入: 评级={rs_proxy:.1f}, 强势股票特征',
            'rs_rating': rs_proxy,
            'timestamp': datetime.now()
        }

        # 计算仓位大小
        position_size = self.calculate_position_size(signal, 0.03)

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

        # 计算RS评级代理
        sma_50 = data['Close'].rolling(50).mean().iloc[-1]
        price_to_ma_ratio = current_price / sma_50

        # 卖出信号: RS评级下降或技术恶化
        sell_signal = price_to_ma_ratio < 0.95  # 价格跌破50日均线附近

        if sell_signal:
            confidence = 0.8
            reason = f'IBD RS卖出: 相对强度减弱'

            logger.info(f"🔴 {symbol} A30卖出信号 - 价格:{current_price:.2f}, 技术恶化")

            return {
                'symbol': symbol,
                'signal_type': 'IBD_RS_SELL',
                'action': 'SELL',
                'price': current_price,
                'confidence': confidence,
                'reason': reason,
                'position_size': abs(self.positions[symbol]['size']),
                'timestamp': datetime.now()
            }

        return None

    def generate_signals(self, symbol: str, data: pd.DataFrame,
                        indicators: Dict) -> List[Dict]:
        """生成交易信号"""
        signals = []

        # 基本数据检查
        if data.empty or len(data) < 100:
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
                return signals

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