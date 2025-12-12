#!/usr/bin/env python3
"""
Minervini趋势模板选股策略
基于Mark Minervini的经典趋势跟踪筛选方法
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
import time

from .base_screener import BaseScreener

logger = logging.getLogger(__name__)

class MinerviniScreener(BaseScreener):
    """Minervini趋势模板选股策略"""

    def _default_config(self) -> Dict:
        """Minervini策略的默认配置"""
        config = super()._default_config()
        config.update({
            'universe': 'sp500',
            'min_market_cap': 1000000000,  # 10亿市值
            'min_price': 10.0,
            'min_volume': 500000,
            'max_screen_size': 20,
            'ranking_method': 'rs_rating',  # 按相对强度评分排序

            # Minervini特定参数
            'rs_percentile_threshold': 70,  # 相对强度百分位阈值
            'min_price_above_52w_low': 1.3,  # 股价至少在52周最低点上方30%
            'max_price_below_52w_high': 0.75,  # 股价不超过52周最高点的75%
            'require_volume_confirmation': True,  # 需要成交量确认
        })
        return config

    def screen_stocks(self, data_provider, **kwargs) -> List[Dict]:
        """
        执行Minervini趋势模板筛选

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
            logger.info("使用缓存的Minervini筛选结果")
            return cached_results

        logger.info("开始执行Minervini趋势模板筛选")

        # 获取股票池
        universe_stocks = self._get_universe_stocks(data_provider)
        logger.info(f"股票池包含 {len(universe_stocks)} 只股票")

        # 获取基准指数数据（S&P 500）
        benchmark_data = self._get_benchmark_data(data_provider)
        if benchmark_data is None:
            logger.error("无法获取基准指数数据")
            return []

        # 计算相对强度
        rs_ratings = self._calculate_relative_strength(universe_stocks, data_provider, benchmark_data)

        # 筛选前70%相对强度的股票
        rs_threshold = np.percentile(list(rs_ratings.values()), self.config['rs_percentile_threshold'])
        top_stocks = [symbol for symbol, rs in rs_ratings.items() if rs >= rs_threshold]

        logger.info(f"相对强度筛选后剩余 {len(top_stocks)} 只股票")

        # 应用Minervini趋势模板条件
        screened_stocks = []
        for symbol in top_stocks:
            try:
                stock_data = data_provider.get_stock_data(symbol, period="2y")
                if stock_data is None or stock_data.empty:
                    continue

                # 应用基本筛选条件
                if not self._passes_basic_filters(stock_data):
                    continue

                # 应用Minervini趋势模板
                score, details = self._apply_minervini_template(stock_data, rs_ratings[symbol])

                if score > 0:
                    screened_stocks.append({
                        'symbol': symbol,
                        'score': score,
                        'rs_rating': rs_ratings[symbol],
                        'confidence': min(1.0, score / 100.0),
                        'details': details,
                        'strategy': 'minervini_trend_template',
                        'screened_at': datetime.now().isoformat()
                    })

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

        logger.info(f"Minervini筛选完成，共筛选出 {len(screened_stocks)} 只股票")
        return screened_stocks

    def _get_benchmark_data(self, data_provider) -> Optional[pd.DataFrame]:
        """获取基准指数数据"""
        try:
            # 使用S&P 500作为基准
            benchmark_data = data_provider.get_stock_data('^GSPC', period="2y")
            return benchmark_data
        except Exception as e:
            logger.error(f"获取基准指数数据失败: {e}")
            return None

    def _calculate_relative_strength(self, stocks: List[str], data_provider, benchmark_data: pd.DataFrame) -> Dict[str, float]:
        """计算股票相对强度评分"""
        rs_ratings = {}

        # 计算基准指数的累积收益率
        benchmark_returns = benchmark_data['Close'].pct_change().dropna()
        benchmark_cum_return = (1 + benchmark_returns).cumprod().iloc[-1]

        for symbol in stocks:
            try:
                stock_data = data_provider.get_stock_data(symbol, period="1y")
                if stock_data is None or stock_data.empty or len(stock_data) < 200:
                    continue

                # 计算股票累积收益率
                stock_returns = stock_data['Close'].pct_change().dropna()
                stock_cum_return = (1 + stock_returns).cumprod().iloc[-1]

                # 计算相对强度倍数
                if benchmark_cum_return > 0:
                    rs_multiple = stock_cum_return / benchmark_cum_return
                    # 转换为百分位评分
                    rs_ratings[symbol] = rs_multiple * 100
                else:
                    rs_ratings[symbol] = 50.0  # 默认中性评分

            except Exception as e:
                logger.warning(f"计算 {symbol} 相对强度失败: {e}")
                continue

        return rs_ratings

    def _passes_basic_filters(self, data: pd.DataFrame) -> bool:
        """应用基本筛选条件"""
        if data.empty or len(data) < 200:
            return False

        # 价格条件
        current_price = data['Close'].iloc[-1]
        if current_price < self.config['min_price']:
            return False

        # 成交量条件
        if self.config['require_volume_confirmation'] and 'Volume' in data.columns:
            avg_volume = data['Volume'].tail(20).mean()
            if pd.isna(avg_volume) or avg_volume < self.config['min_volume']:
                return False

        return True

    def _apply_minervini_template(self, data: pd.DataFrame, rs_rating: float) -> Tuple[float, Dict]:
        """
        应用Minervini趋势模板条件

        Returns:
            Tuple[float, Dict]: (评分, 详细信息)
        """
        score = 0
        details = {}

        try:
            # 计算移动平均线
            sma_50 = data['Close'].rolling(window=50).mean()
            sma_150 = data['Close'].rolling(window=150).mean()
            sma_200 = data['Close'].rolling(window=200).mean()

            current_close = data['Close'].iloc[-1]

            # 计算52周高低点
            high_52w = data['High'].rolling(window=260).max().iloc[-1]
            low_52w = data['Low'].rolling(window=260).min().iloc[-1]

            # 条件1: 当前价格高于150日均线，150日均线高于200日均线
            condition1 = (current_close > sma_150.iloc[-1] > sma_200.iloc[-1])
            details['condition1_price_above_mas'] = condition1
            if condition1:
                score += 25

            # 条件2: 150日均线高于20天前的200日均线（趋势向上）
            condition2 = sma_150.iloc[-1] > sma_200.iloc[-20]
            details['condition2_trend_up'] = condition2
            if condition2:
                score += 20

            # 条件3: 当前价格高于50日均线
            condition3 = current_close > sma_50.iloc[-1]
            details['condition3_above_50ma'] = condition3
            if condition3:
                score += 20

            # 条件4: 当前价格至少在52周最低点上方30%
            condition4 = current_close >= (low_52w * self.config['min_price_above_52w_low'])
            details['condition4_above_52w_low'] = condition4
            if condition4:
                score += 20

            # 条件5: 当前价格不超过52周最高点的75%（避免过度延伸）
            condition5 = current_close >= (high_52w * self.config['max_price_below_52w_high'])
            details['condition5_below_52w_high'] = condition5
            if condition5:
                score += 15

            # 相对强度加分
            rs_bonus = min(20, rs_rating / 5)  # RS评分每5点加1分，最多20分
            score += rs_bonus
            details['rs_rating'] = rs_rating
            details['rs_bonus'] = rs_bonus

            details['total_score'] = score
            details['conditions_met'] = sum([condition1, condition2, condition3, condition4, condition5])

        except Exception as e:
            logger.warning(f"应用Minervini模板失败: {e}")
            score = 0

        return score, details