#!/usr/bin/env python3
"""
RSI超买超卖选股策略
基于相对强弱指数(RSI)的动量选股策略
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
import time

from .base_screener import BaseScreener

logger = logging.getLogger(__name__)

class RSIScreener(BaseScreener):
    """RSI超买超卖选股策略"""

    def _default_config(self) -> Dict:
        """RSI策略的默认配置"""
        config = super()._default_config()
        config.update({
            'universe': 'sp500',
            'min_market_cap': 500000000,  # 5亿市值
            'min_price': 5.0,
            'min_volume': 100000,
            'max_screen_size': 30,
            'ranking_method': 'rsi_signal_strength',  # 按RSI信号强度排序

            # RSI特定参数
            'rsi_period': 14,  # RSI计算周期
            'oversold_threshold': 30,  # 超卖阈值
            'overbought_threshold': 70,  # 超买阈值
            'lookback_period': 14,  # 回望周期（计算平均RSI）
            'signal_type': 'oversold',  # 'oversold', 'overbought', 'both'
            'require_trend_confirmation': True,  # 需要趋势确认
            'trend_period': 50,  # 趋势确认周期
        })
        return config

    def screen_stocks(self, data_provider, **kwargs) -> List[Dict]:
        """
        执行RSI筛选

        Args:
            data_provider: 数据提供者实例
            **kwargs: 额外参数

        Returns:
            List[Dict]: 筛选结果
        """
        start_time = time.time()

        # 检查缓存
        cached_results = self._get_cached_results()
        if cached_results:
            logger.info("使用缓存的RSI筛选结果")
            return cached_results

        logger.info("开始执行RSI超买超卖筛选")

        # 获取股票池
        universe_stocks = self._get_universe_stocks(data_provider)
        logger.info(f"股票池包含 {len(universe_stocks)} 只股票")

        # 筛选符合条件的股票
        screened_stocks = []
        processed_count = 0
        timeout_count = 0
        max_timeout_count = 5  # 最大连续超时次数

        for symbol in universe_stocks:
            try:
                processed_count += 1
                if processed_count % 10 == 0:  # 每处理10只股票打印一次进度
                    logger.info(f"已处理 {processed_count}/{len(universe_stocks)} 只股票")

                logger.debug(f"正在处理股票 {symbol} ({processed_count}/{len(universe_stocks)})")

                # 如果连续超时太多，跳出循环
                if timeout_count >= max_timeout_count:
                    logger.warning(f"连续超时次数过多 ({timeout_count})，停止处理以避免长时间等待")
                    break

                # 使用较短的超时时间，避免长时间等待
                try:
                    # 根据data_provider类型选择合适的方法
                    if hasattr(data_provider, 'get_intraday_data'):
                        # 真实数据提供者
                        stock_data = data_provider.get_intraday_data(
                            symbol,
                            interval='1d',  # 日线数据
                            lookback=180,  # 约6个月的数据
                            use_cache=True
                        )
                    elif hasattr(data_provider, 'get_stock_data'):
                        # 模拟数据提供者
                        stock_data = data_provider.get_stock_data(symbol, period="6mo")
                    else:
                        logger.warning(f"数据提供者不支持获取股票数据的方法")
                        timeout_count += 1
                        continue

                except Exception as e:
                    timeout_count += 1
                    logger.warning(f"股票 {symbol} 数据获取失败: {e}，跳过")
                    continue

                if stock_data is None or stock_data.empty:
                    logger.debug(f"股票 {symbol} 数据为空，跳过")
                    continue

                # 重置超时计数
                timeout_count = 0
                logger.debug(f"股票 {symbol} 获取到 {len(stock_data)} 条数据")

                # 应用基本筛选条件
                filtered_data = self._filter_basic_criteria({symbol: stock_data})
                if symbol not in filtered_data:
                    logger.debug(f"股票 {symbol} 未通过基本筛选条件")
                    continue

                # 计算RSI并检查信号
                rsi_signal = self._calculate_rsi_signal(stock_data)

                if rsi_signal['has_signal']:
                    logger.info(f"股票 {symbol} 触发RSI信号: {rsi_signal['signal_type']}, 评分: {rsi_signal['score']:.2f}")
                    screened_stocks.append({
                        'symbol': symbol,
                        'score': rsi_signal['score'],
                        'rsi_value': rsi_signal['rsi_value'],
                        'signal_type': rsi_signal['signal_type'],
                        'confidence': rsi_signal['confidence'],
                        'details': rsi_signal['details'],
                        'strategy': 'rsi_momentum',
                        'screened_at': datetime.now().isoformat()
                    })
                else:
                    logger.debug(f"股票 {symbol} 未触发RSI信号")

            except Exception as e:
                logger.warning(f"处理股票 {symbol} 时出错: {e}")
                continue

        # 排序和限制结果
        screened_stocks = self._rank_stocks(screened_stocks)

        # 更新统计
        processing_time = time.time() - start_time
        self._update_stats(processing_time, len(universe_stocks), len(screened_stocks))

        # 缓存结果
        self._cache_results(screened_stocks)

        logger.info(f"RSI筛选完成，共筛选出 {len(screened_stocks)} 只股票")
        return screened_stocks

    def _calculate_rsi_signal(self, data: pd.DataFrame) -> Dict:
        """
        计算RSI信号

        Returns:
            Dict: RSI信号信息
        """
        result = {
            'has_signal': False,
            'score': 0,
            'rsi_value': 0,
            'signal_type': None,
            'confidence': 0.0,
            'details': {}
        }

        try:
            # 计算RSI
            rsi = self._calculate_rsi(data['Close'], self.config['rsi_period'])
            if rsi.empty:
                return result

            # 获取最近的RSI值
            current_rsi = rsi.iloc[-1]
            result['rsi_value'] = current_rsi

            # 计算指定周期的平均RSI
            lookback_period = min(self.config['lookback_period'], len(rsi))
            avg_rsi = rsi.tail(lookback_period).mean()

            result['details']['current_rsi'] = current_rsi
            result['details']['avg_rsi'] = avg_rsi

            signal_type = self.config['signal_type']
            has_signal = False
            score = 0

            # 检查超卖信号
            if signal_type in ['oversold', 'both']:
                oversold_threshold = self.config['oversold_threshold']
                if avg_rsi <= oversold_threshold:
                    has_signal = True
                    result['signal_type'] = 'oversold'
                    # 评分基于RSI偏离程度
                    deviation = oversold_threshold - avg_rsi
                    score = min(100, deviation * 5)  # 每偏离1点得5分

                    # 趋势确认加分
                    if self.config['require_trend_confirmation']:
                        trend_score = self._check_trend_confirmation(data)
                        score += trend_score * 20  # 趋势确认加最多20分

            # 检查超买信号
            elif signal_type in ['overbought', 'both']:
                overbought_threshold = self.config['overbought_threshold']
                if avg_rsi >= overbought_threshold:
                    has_signal = True
                    result['signal_type'] = 'overbought'
                    # 评分基于RSI偏离程度
                    deviation = avg_rsi - overbought_threshold
                    score = min(100, deviation * 5)  # 每偏离1点得5分

            if has_signal:
                result['has_signal'] = True
                result['score'] = score
                result['confidence'] = min(1.0, score / 100.0)

                result['details']['signal_strength'] = score
                result['details']['threshold'] = (
                    self.config['oversold_threshold'] if result['signal_type'] == 'oversold'
                    else self.config['overbought_threshold']
                )

        except Exception as e:
            logger.warning(f"计算RSI信号失败: {e}")

        return result

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """计算RSI指标"""
        try:
            delta = prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))

            return rsi
        except Exception as e:
            logger.warning(f"计算RSI失败: {e}")
            return pd.Series()

    def _check_trend_confirmation(self, data: pd.DataFrame) -> float:
        """
        检查趋势确认
        Returns:
            float: 趋势确认评分 (0-1)
        """
        try:
            trend_period = self.config['trend_period']
            if len(data) < trend_period:
                return 0.0

            # 计算趋势斜率
            prices = data['Close'].tail(trend_period)
            x = np.arange(len(prices))
            slope = np.polyfit(x, prices, 1)[0]

            # 计算R²值作为趋势强度
            y_pred = slope * x + np.polyfit(x, prices, 1)[1]
            r_squared = 1 - (np.sum((prices - y_pred)**2) / np.sum((prices - np.mean(prices))**2))

            # 正斜率且R²>0.3认为是有效趋势
            if slope > 0 and r_squared > 0.3:
                return min(1.0, r_squared)
            else:
                return 0.0

        except Exception as e:
            logger.warning(f"趋势确认检查失败: {e}")
            return 0.0

    def _rank_stocks(self, screened_stocks: List[Dict]) -> List[Dict]:
        """对筛选结果进行排序"""
        ranking_method = self.config.get('ranking_method', 'rsi_signal_strength')

        if ranking_method == 'rsi_signal_strength':
            # 按信号强度排序
            screened_stocks.sort(key=lambda x: x.get('score', 0), reverse=True)
        elif ranking_method == 'rsi_value':
            # 按RSI值排序（超卖优先）
            if self.config['signal_type'] == 'oversold':
                screened_stocks.sort(key=lambda x: x.get('rsi_value', 50))
            else:
                screened_stocks.sort(key=lambda x: x.get('rsi_value', 50), reverse=True)

        # 限制结果数量
        max_size = self.config.get('max_screen_size', 30)
        return screened_stocks[:max_size]