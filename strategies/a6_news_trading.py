#!/usr/bin/env python3
"""
A6 策略: 基于新闻的交易策略
快速反应突发新闻带来的市场波动，结合新闻情感分析和价格波动检测。
增强版: 包含利好出尽、情绪背离和动量衰竭的卖出逻辑。
"""

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from strategies.base_strategy import BaseStrategy
from strategies import indicators  # 假设有这个模块用于计算RSI/MA

logger = logging.getLogger(__name__)


class A6NewsTrading(BaseStrategy):
    """
    基于新闻的交易策略

    核心机制:
    1. 实时监控Alpha Vantage/Polygon新闻API
    2. 分析新闻情感和相关性
    3. 检测新闻发布后的价格波动
    4. 基于情感和波动强度生成交易信号
    5. 严格的风险控制和快速进出
    """

    def _default_config(self) -> Dict:
        """A6 策略的默认配置"""
        return {
            'initial_capital': 40000.0,
            'risk_per_trade': 0.015,
            'max_position_size': 0.04,
            'per_trade_notional_cap': 4000.0,
            'max_position_notional': 20000.0,
            'alpha_vantage_api_key': 'YOUR_API_KEY_HERE',
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
                        indicators_dict: Dict) -> List[Dict]:
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

            if data is None or len(data) < 20:
                logger.warning(f"[{symbol}] A6信号生成: 数据不足")
                return signals

            close_col = 'Close' if 'Close' in data.columns else 'close'
            current_price = data[close_col].iloc[-1]

            # 预过滤 - 检查交易时间和基本条件
            current_time = datetime.now()
            
            # --- 辅助指标计算 (用于增强卖出逻辑) ---
            # 计算 MA20 (作为短期趋势线)
            ma20 = data[close_col].rolling(20).mean().iloc[-1]
            # 计算 RSI (用于判断超买/衰竭)
            delta = data[close_col].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs)).iloc[-1]
            if np.isnan(rsi): rsi = 50.0

            # 1. 检查持仓止损止盈 (CRITICAL: 即使没有新闻也要检查止损)
            if symbol in self.positions:
                exit_signal = self.check_exit_conditions(symbol, current_price)
                if exit_signal:
                    signals.append(exit_signal)
                    return signals # 触发硬止损直接返回

            # 检查最近是否进行过新闻交易 (冷却期)
            if symbol in self.last_news_trade_time:
                time_since_last_trade = (current_time - self.last_news_trade_time[symbol]).total_seconds() / 60
                if time_since_last_trade < self.cooldown_after_news_trade:
                    # 即使在冷却期，如果满足"紧急离场条件"，也允许生成卖出信号
                    if symbol in self.positions:
                        # 紧急离场：价格跌破均线 且 RSI 极高回落
                        if current_price < ma20 and rsi > 70:
                             pass # 允许继续执行下面的逻辑以生成卖出信号
                        else:
                            logger.info(f"[{symbol}] A6 新闻交易冷却中，还需 {self.cooldown_after_news_trade - time_since_last_trade:.1f} 分钟")
                            return signals
                    else:
                        return signals

            # 获取新闻影响分析
            news_impact = self.data_provider.get_recent_news_impact(
                symbol, self.polygon_api_key, self.news_reaction_window
            )

            if not news_impact or news_impact.get('news_count', 0) == 0:
                # 即使没有新新闻，如果持仓且技术面恶化，也应该检查是否该卖出（"Sell the News" 后期）
                if symbol in self.positions:
                     # 构造一个空的/中性的新闻对象来触发 _generate_news_signal 中的纯技术检查
                     dummy_news = {'title': 'No recent news', 'sentiment_score': 0, 'relevance_score': 0}
                     signal = self._generate_news_signal(
                        symbol, dummy_news, 0, 0, 0, self.positions[symbol], current_price, ma20, rsi
                     )
                     if signal:
                         signals.append(signal)
                else:
                    logger.info(f"[{symbol}] A6 无相关新闻数据")
                return signals

            impact_score = news_impact.get('impact_score', 0.0)
            significant_news = news_impact.get('significant_news', [])

            logger.info(
                f"[{symbol}] ========== A6 新闻分析周期 =========="
            )
            logger.info(
                f"[{symbol}] 新闻影响评分: {impact_score:.2f}, 显著新闻数量: {len(significant_news)}, "
                f"总新闻数: {news_impact.get('news_count', 0)}, RSI={rsi:.1f}, MA20={ma20:.2f}"
            )

            # 分析显著新闻
            # 如果没有显著新闻，但也持仓，使用最新的一条普通新闻进行检查
            if not significant_news and symbol in self.positions:
                pass 
                # 这里可以扩展，如果没有显著新闻但持仓，也可以触发卖出检查，
                # 但上面的 dummy_news 逻辑或者下面的循环逻辑覆盖了一部分

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

                # 过滤条件 (买入时严格，卖出时宽松)
                if relevance_score < self.min_news_relevance:
                    continue

                if time_diff_minutes > (self.max_news_age_hours * 60):
                    continue

                # 买入需要波动率支持，卖出(止损)不需要太高的波动率限制
                if symbol not in self.positions and volatility < self.volatility_threshold:
                    logger.info(f"[{symbol}] 价格波动不足以开仓: {volatility:.4f} < {self.volatility_threshold}")
                    continue

                # 获取当前持仓
                current_position = self.positions.get(symbol, 0)

                # 生成交易信号 (传入 MA20 和 RSI)
                signal = self._generate_news_signal(
                    symbol, news, sentiment_score, volatility,
                    news_impact_score, current_position, current_price,
                    ma20, rsi
                )

                if signal:
                    # 生成信号哈希用于冷却
                    signal_hash = self._generate_signal_hash(signal)
                    
                    # 卖出信号通常不需要太严格的冷却，或者冷却逻辑不同
                    if signal['action'] == 'SELL' and current_position > 0:
                        signals.append(signal)
                        logger.info(f"[{symbol}] ✅ 生成卖出/平仓信号: {signal['reason']}")
                        break
                    
                    elif not self._is_signal_cooldown(signal_hash):
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
                            current_position: int, current_price: float,
                            ma20: float, rsi: float) -> Optional[Dict]:
        """
        基于新闻分析生成具体的交易信号
        """
        try:
            # --- 1. 买入逻辑 (保持原样，略微增加 MA20 过滤) ---
            # 正面新闻且价格上涨 -> 买入信号
            if (current_position == 0 and 
                sentiment_score >= self.sentiment_threshold_positive and
                impact_score > 5.0):
                
                # 简单过滤: 最好价格在均线之上，或者即使在之下但波动率极大(超跌反弹)
                if current_price > ma20 or volatility > self.volatility_threshold * 2:
                    confidence = min(sentiment_score * 0.8 + volatility * 2.0, 1.0)

                    signal = {
                        'symbol': symbol,
                        'signal_type': 'NEWS_POSITIVE_BREAKOUT',
                        'action': 'BUY',
                        'price': current_price,
                        'quantity': 0,  # 执行时计算
                        'confidence': confidence,
                        'reason': f'A6正面新闻: 情感={sentiment_score:.2f}, 波动={volatility:.4f}, '
                                 f'MA20之上/高波',
                        'timestamp': datetime.now(),
                        'news_data': {'sentiment': sentiment_score, 'volatility': volatility}
                    }
                    return signal

            # --- 2. 空头开仓逻辑 ---
            # 负面新闻且价格下跌 -> 卖出信号（空头）
            elif (current_position == 0 and 
                  sentiment_score <= self.sentiment_threshold_negative and
                  impact_score > 5.0):

                confidence = min(abs(sentiment_score) * 0.8 + volatility * 2.0, 1.0)

                signal = {
                    'symbol': symbol,
                    'signal_type': 'NEWS_NEGATIVE_BREAKOUT',
                    'action': 'SELL',  # 做空
                    'price': current_price,
                    'quantity': 0,
                    'confidence': confidence,
                    'reason': f'A6负面新闻: 情感={sentiment_score:.2f}, 波动={volatility:.4f}',
                    'timestamp': datetime.now(),
                    'news_data': {'sentiment': sentiment_score, 'volatility': volatility}
                }
                return signal

            # --- 3. 持多仓时的卖出逻辑 (增强版) ---
            elif current_position > 0:
                should_sell = False
                sell_reason = ""
                sell_confidence = 0.5

                # 逻辑 A: 传统的负面新闻离场
                if sentiment_score <= self.sentiment_threshold_negative:
                    should_sell = True
                    sell_reason = f"负面新闻出现 (情感={sentiment_score:.2f})"
                    sell_confidence = min(abs(sentiment_score) + 0.3, 1.0)

                # 逻辑 B: "Sell the News" / 情绪背离 (Good News but Price Drops)
                # 新闻是好的，但是价格跌破了 MA20，或者在大幅下跌
                elif sentiment_score > 0 and current_price < ma20:
                    should_sell = True
                    sell_reason = f"利好出尽/技术破位 (情感正, 但价格 < MA20)"
                    sell_confidence = 0.7

                # 逻辑 C: 动量衰竭 / 极度超买 (Profit Taking)
                # 即使没有负面新闻，如果 RSI 太高且价格开始滞涨
                elif rsi > 75 and volatility < self.volatility_threshold:
                    should_sell = True
                    sell_reason = f"动量衰竭 (RSI {rsi:.1f} > 75, 波动率低)"
                    sell_confidence = 0.6

                # 逻辑 D: 纯技术面恶化 (作为保底)
                # 假设 impact_score 很低(无新新闻)，但价格跌破关键位
                elif impact_score < 2.0 and current_price < ma20 * 0.98:
                    should_sell = True
                    sell_reason = f"趋势转弱 (无新闻支撑, Price < MA20 * 0.98)"
                    sell_confidence = 0.6

                if should_sell:
                    signal = {
                        'symbol': symbol,
                        'signal_type': 'NEWS_EXIT_LONG',
                        'action': 'SELL',
                        'price': current_price,
                        'quantity': current_position,
                        'confidence': sell_confidence,
                        'reason': f'A6平多: {sell_reason}',
                        'timestamp': datetime.now()
                    }
                    return signal

            # --- 4. 持空仓时的平仓逻辑 ---
            elif current_position < 0:
                should_cover = False
                cover_reason = ""
                
                # 逻辑 A: 正面新闻
                if sentiment_score >= self.sentiment_threshold_positive:
                    should_cover = True
                    cover_reason = f"正面新闻出现 (情感={sentiment_score:.2f})"

                # 逻辑 B: 技术反转 (价格站上 MA20)
                elif current_price > ma20:
                    should_cover = True
                    cover_reason = "趋势反转 (Price > MA20)"

                # 逻辑 C: 超卖 (RSI < 25)
                elif rsi < 25:
                    should_cover = True
                    cover_reason = f"超卖反弹风险 (RSI {rsi:.1f})"

                if should_cover:
                    signal = {
                        'symbol': symbol,
                        'signal_type': 'NEWS_EXIT_SHORT',
                        'action': 'BUY',
                        'price': current_price,
                        'quantity': abs(current_position),
                        'confidence': 0.7,
                        'reason': f'A6平空: {cover_reason}',
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