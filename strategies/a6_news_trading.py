#!/usr/bin/env python3
"""
A6 策略: 基于新闻的交易策略
快速反应突发新闻带来的市场波动，结合新闻情感分析和价格波动检测。
"""

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class A6NewsTrading(BaseStrategy):
    """
    基于新闻的交易策略

    核心机制:
    1. 实时监控Alpha Vantage新闻API
    2. 分析新闻情感和相关性
    3. 检测新闻发布后的价格波动
    4. 基于情感和波动强度生成交易信号
    5. 严格的风险控制和快速进出
    """

    def _default_config(self) -> Dict:
        """A6 策略的默认配置"""
        return {
            'initial_capital': 100000.0,
            'risk_per_trade': 0.015,
            'max_position_size': 0.04,
            'per_trade_notional_cap': 5000.0,
            'max_position_notional': 20000.0,
            'alpha_vantage_api_key': 'S4DJM04D0PS02401',
            'news_lookback_hours': 24,
            'sentiment_threshold_positive': 0.3,
            'sentiment_threshold_negative': -0.3,
            'volatility_threshold': 0.01,
            'news_reaction_window': 30,
            'min_news_relevance': 0.3,
            'max_news_age_hours': 4,
            'cooldown_after_news_trade': 60,
            'ib_order_type': 'MKT',
            'ib_limit_offset': 0.005,
            'trading_start_time': '09:45',
            'trading_end_time': '15:30',
            'avoid_open_hour': True,
            'avoid_close_hour': True,
        }

    def __init__(self, config: Optional[Dict] = None, ib_trader=None):
        """
        初始化 A6 策略。

        Args:
            config: 策略配置字典
            ib_trader: IB 交易员实例（可选）
        """
        super().__init__(config, ib_trader)

        # 策略特定配置
        self.polygon_api_key = self.config.get('polygon_api_key', 'YOUR_API_KEY_HERE')
        self.news_lookback_hours = self.config.get('news_lookback_hours', 24)
        self.sentiment_threshold_positive = self.config.get('sentiment_threshold_positive', 0.6)
        self.sentiment_threshold_negative = self.config.get('sentiment_threshold_negative', -0.6)
        self.volatility_threshold = self.config.get('volatility_threshold', 0.02)
        self.news_reaction_window = self.config.get('news_reaction_window', 30)
        self.min_news_relevance = self.config.get('min_news_relevance', 0.7)
        self.max_news_age_hours = self.config.get('max_news_age_hours', 4)
        self.cooldown_after_news_trade = self.config.get('cooldown_after_news_trade', 60)

        # 新闻交易状态跟踪
        self.last_news_trade_time = {}

        # 数据提供器（由策略管理器设置）
        self.data_provider = None

        if self.polygon_api_key == 'YOUR_API_KEY_HERE':
            logger.warning("⚠️  A6策略需要有效的Polygon API密钥")

        logger.info(
            f"A6 NewsTrading initialized: sentiment_thresholds=({self.sentiment_threshold_negative:.2f}, "
            f"{self.sentiment_threshold_positive:.2f}), volatility_threshold={self.volatility_threshold:.2f}, "
            f"reaction_window={self.news_reaction_window}min"
        )

    def generate_signals(self, symbol: str, data: pd.DataFrame,
                        indicators: Dict) -> List[Dict]:
        """
        基于新闻分析生成交易信号。

        Args:
            symbol: 股票代码
            data: 包含 OHLCV 数据的 DataFrame
            indicators: 包含技术指标的字典（可选）

        Returns:
            信号字典列表
        """
        signals = []

        try:
            if not hasattr(self, 'data_provider') or self.data_provider is None:
                logger.warning(f"[{symbol}] A6 需要数据提供器来获取新闻")
                return signals

            if self.polygon_api_key == 'YOUR_POLYGON_API_KEY_HERE':
                logger.warning(f"[{symbol}] A6 需要有效的Polygon API密钥")
                return signals

            if data is None or len(data) < 10:
                logger.warning(f"[{symbol}] A6信号生成: 数据不足")
                return signals

            close_col = 'Close' if 'Close' in data.columns else 'close'
            current_price = data[close_col].iloc[-1]

            # 预过滤 - 检查交易时间和基本条件
            current_time = datetime.now()
            trading_start = datetime.strptime(self.config.get('trading_start_time', '09:45'), '%H:%M').time()
            trading_end = datetime.strptime(self.config.get('trading_end_time', '15:30'), '%H:%M').time()

            #     logger.info(f"[{symbol}] A6 不在交易时间范围内")
            #     return signals

            # 1. 检查持仓止损止盈 (CRITICAL: 即使没有新闻也要检查止损)
            if symbol in self.positions:
                exit_signal = self.check_exit_conditions(symbol, current_price)
                if exit_signal:
                    signals.append(exit_signal)

            # 检查最近是否进行过新闻交易
            if symbol in self.last_news_trade_time:
                time_since_last_trade = (current_time - self.last_news_trade_time[symbol]).total_seconds() / 60
                if time_since_last_trade < self.cooldown_after_news_trade:
                    logger.info(f"[{symbol}] A6 新闻交易冷却中，还需 {self.cooldown_after_news_trade - time_since_last_trade:.1f} 分钟")
                    return signals

            # 获取新闻影响分析
            news_impact = self.data_provider.get_recent_news_impact(
                symbol, self.polygon_api_key, self.news_reaction_window
            )

            if not news_impact or news_impact.get('news_count', 0) == 0:
                logger.info(f"[{symbol}] A6 无相关新闻数据")
                return signals

            impact_score = news_impact.get('impact_score', 0.0)
            significant_news = news_impact.get('significant_news', [])

            logger.info(
                f"[{symbol}] ========== A6 新闻分析周期 =========="
            )
            logger.info(
                f"[{symbol}] 新闻影响评分: {impact_score:.2f}, 显著新闻数量: {len(significant_news)}, "
                f"总新闻数: {news_impact.get('news_count', 0)}"
            )

            # 分析显著新闻
            for news_data in significant_news:
                news = news_data['news']
                news_impact_score = news_data['impact_score']
                volatility = news_data['volatility']
                time_diff_minutes = news_data['time_diff_minutes']

                sentiment_score = news['sentiment_score']
                relevance_score = news['relevance_score']

                logger.info(
                    f"[{symbol}] 新闻分析: 情感={sentiment_score:.2f}, 相关性={relevance_score:.2f}, "
                    f"波动={volatility:.4f}, 影响评分={news_impact_score:.2f}, "
                    f"发布时间差={time_diff_minutes:.1f}分钟"
                )

                # 过滤条件
                if relevance_score < self.min_news_relevance:
                    logger.info(f"[{symbol}] 新闻相关性不足: {relevance_score:.2f} < {self.min_news_relevance}")
                    continue

                if time_diff_minutes > (self.max_news_age_hours * 60):
                    logger.info(f"[{symbol}] 新闻太旧: {time_diff_minutes:.1f} > {self.max_news_age_hours * 60} 分钟")
                    continue

                if volatility < self.volatility_threshold:
                    logger.info(f"[{symbol}] 价格波动不足: {volatility:.4f} < {self.volatility_threshold}")
                    continue

                # 获取当前持仓
                current_position = self.positions.get(symbol, 0)

                # 生成交易信号
                signal = self._generate_news_signal(
                    symbol, news, sentiment_score, volatility,
                    news_impact_score, current_position, current_price
                )

                if signal:
                    # 生成信号哈希用于冷却
                    signal_hash = self._generate_signal_hash(signal)
                    if not self._is_signal_cooldown(signal_hash):
                        signals.append(signal)
                        self._add_signal_to_cache(signal_hash, minutes=30)  # 30分钟冷却
                        self.last_news_trade_time[symbol] = current_time

                        logger.info(
                            f"[{symbol}] ✅ 生成新闻交易信号: {signal['action']} @ {current_price:.2f}, "
                            f"原因: {signal['reason']}"
                        )
                        break  # 每个周期只生成一个信号
                    else:
                        logger.info(f"[{symbol}] 新闻信号在冷却期内")

        except Exception as e:
            logger.error(f"[{symbol}] A6 信号生成异常: {e}", exc_info=True)

        if signals:
            logger.info(f"[{symbol}] 本周期 A6 生成 {len(signals)} 个信号")
        else:
            logger.info(f"[{symbol}] 本周期 A6 无信号生成")

        return signals

    def _generate_news_signal(self, symbol: str, news: Dict, sentiment_score: float,
                            volatility: float, impact_score: float,
                            current_position: int, current_price: float) -> Optional[Dict]:
        """
        基于新闻分析生成具体的交易信号
        """
        try:
            # 正面新闻且价格上涨 -> 买入信号
            if (sentiment_score >= self.sentiment_threshold_positive and
                impact_score > 5.0 and current_position == 0):

                confidence = min(sentiment_score * 0.8 + volatility * 2.0, 1.0)

                signal = {
                    'symbol': symbol,
                    'signal_type': 'NEWS_POSITIVE_BREAKOUT',
                    'action': 'BUY',
                    'price': current_price,
                    'quantity': 0,  # 执行时计算
                    'confidence': confidence,
                    'reason': f'A6正面新闻突破: 情感={sentiment_score:.2f}, 波动={volatility:.4f}, '
                             f'影响={impact_score:.2f}, 标题="{news["title"][:50]}..."',
                    'timestamp': datetime.now(),
                    'news_data': {
                        'sentiment': sentiment_score,
                        'volatility': volatility,
                        'impact_score': impact_score
                    }
                }
                return signal

            # 负面新闻且价格下跌 -> 卖出信号（空头）
            elif (sentiment_score <= self.sentiment_threshold_negative and
                  impact_score > 5.0 and current_position == 0):

                confidence = min(abs(sentiment_score) * 0.8 + volatility * 2.0, 1.0)

                signal = {
                    'symbol': symbol,
                    'signal_type': 'NEWS_NEGATIVE_BREAKOUT',
                    'action': 'SELL',  # 做空
                    'price': current_price,
                    'quantity': 0,  # 执行时计算
                    'confidence': confidence,
                    'reason': f'A6负面新闻突破: 情感={sentiment_score:.2f}, 波动={volatility:.4f}, '
                             f'影响={impact_score:.2f}, 标题="{news["title"][:50]}..."',
                    'timestamp': datetime.now(),
                    'news_data': {
                        'sentiment': sentiment_score,
                        'volatility': volatility,
                        'impact_score': impact_score
                    }
                }
                return signal

            # 多头持仓且负面新闻 -> 平多
            elif (current_position > 0 and sentiment_score <= self.sentiment_threshold_negative and
                  impact_score > 3.0):

                confidence = min(abs(sentiment_score) * 0.7 + volatility * 1.5, 1.0)

                signal = {
                    'symbol': symbol,
                    'signal_type': 'NEWS_EXIT_LONG',
                    'action': 'SELL',
                    'price': current_price,
                    'quantity': current_position,
                    'confidence': confidence,
                    'reason': f'A6平多头仓位: 负面新闻情感={sentiment_score:.2f}, 影响={impact_score:.2f}',
                    'timestamp': datetime.now()
                }
                return signal

            # 空头持仓且正面新闻 -> 平空
            elif (current_position < 0 and sentiment_score >= self.sentiment_threshold_positive and
                  impact_score > 3.0):

                confidence = min(sentiment_score * 0.7 + volatility * 1.5, 1.0)

                signal = {
                    'symbol': symbol,
                    'signal_type': 'NEWS_EXIT_SHORT',
                    'action': 'BUY',
                    'price': current_price,
                    'quantity': abs(current_position),
                    'confidence': confidence,
                    'reason': f'A6平空头仓位: 正面新闻情感={sentiment_score:.2f}, 影响={impact_score:.2f}',
                    'timestamp': datetime.now()
                }
                return signal

            return None

        except Exception as e:
            logger.error(f"生成新闻信号失败 {symbol}: {e}")
            return None

    def run_analysis_cycle(self, data_provider, symbols: List[str]) -> Dict[str, List[Dict]]:
        """运行分析周期，设置数据提供器"""
        # 设置数据提供器用于新闻获取
        self.data_provider = data_provider

        # 调用父类方法
        return super().run_analysis_cycle(data_provider, symbols)