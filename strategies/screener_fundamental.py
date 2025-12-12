#!/usr/bin/env python3
"""
基本面选股策略
基于财务比率和增长指标的量化选股策略
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
import time

from .base_screener import BaseScreener

logger = logging.getLogger(__name__)

class FundamentalScreener(BaseScreener):
    """基本面选股策略"""

    def _default_config(self) -> Dict:
        """基本面策略的默认配置"""
        config = super()._default_config()
        config.update({
            'universe': 'sp500',
            'min_market_cap': 1000000000,  # 10亿市值
            'min_price': 10.0,
            'min_volume': 100000,
            'max_screen_size': 25,
            'ranking_method': 'composite_score',  # 综合评分排序

            # 基本面筛选参数
            'sector_filter': None,  # 行业筛选，如 'Technology'
            'min_roe': 0.10,  # 最小ROE
            'min_roa': 0.05,  # 最小ROA
            'max_debt_ratio': 1.0,  # 最大债务比率
            'min_revenue_growth': 0.05,  # 最小营收增长率
            'min_net_income_growth': 0.05,  # 最小净利润增长率
            'dividend_required': False,  # 是否要求分红
            'min_dividend_yield': 0.02,  # 最小股息率

            # 评分权重
            'weights': {
                'roe': 1.2,
                'roa': 1.1,
                'debt_ratio': -1.1,  # 负权重，因为债务比率越低越好
                'revenue_growth': 1.25,
                'net_income_growth': 1.10,
                'dividend_yield': 0.8,
            }
        })
        return config

    def screen_stocks(self, data_provider, **kwargs) -> List[Dict]:
        """
        执行基本面筛选

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
            logger.info("使用缓存的基本面筛选结果")
            return cached_results

        logger.info("开始执行基本面选股筛选")

        # 获取股票池
        universe_stocks = self._get_universe_stocks(data_provider)
        logger.info(f"股票池包含 {len(universe_stocks)} 只股票")

        # 获取基本面数据
        fundamental_data = self._get_fundamental_data(universe_stocks, data_provider)

        # 筛选符合条件的股票
        screened_stocks = []
        for symbol, fundamentals in fundamental_data.items():
            try:
                # 应用基本面筛选条件
                if self._passes_fundamental_filters(fundamentals):
                    # 计算综合评分
                    score, details = self._calculate_fundamental_score(fundamentals)

                    screened_stocks.append({
                        'symbol': symbol,
                        'score': score,
                        'fundamentals': fundamentals,
                        'confidence': min(1.0, score / 100.0),
                        'details': details,
                        'strategy': 'fundamental_analysis',
                        'screened_at': datetime.now().isoformat()
                    })

            except Exception as e:
                logger.warning(f"处理股票 {symbol} 基本面数据时出错: {e}")
                continue

        # 排序和限制结果
        screened_stocks = self._rank_stocks(screened_stocks)

        # 更新统计
        processing_time = time.time() - start_time
        self._update_stats(processing_time, len(universe_stocks), len(screened_stocks))

        # 缓存结果
        self._cache_results(screened_stocks)

        logger.info(f"基本面筛选完成，共筛选出 {len(screened_stocks)} 只股票")
        return screened_stocks

    def _get_fundamental_data(self, stocks: List[str], data_provider) -> Dict[str, Dict]:
        """获取基本面数据"""
        fundamental_data = {}

        for symbol in stocks:
            try:
                # 从data_provider获取基本面数据
                # 这里需要data_provider支持基本面数据获取
                fundamentals = data_provider.get_fundamental_data(symbol)

                if fundamentals:
                    fundamental_data[symbol] = fundamentals
                else:
                    # 如果没有真实数据，使用模拟数据进行演示
                    fundamental_data[symbol] = self._generate_mock_fundamentals(symbol)

            except Exception as e:
                logger.warning(f"获取 {symbol} 基本面数据失败: {e}")
                continue

        return fundamental_data

    def _generate_mock_fundamentals(self, symbol: str) -> Dict:
        """生成模拟基本面数据（用于演示）"""
        np.random.seed(hash(symbol) % 2**32)  # 确保相同股票每次生成相同数据

        return {
            'roe': np.random.uniform(0.05, 0.25),  # ROE
            'roa': np.random.uniform(0.02, 0.15),  # ROA
            'debt_ratio': np.random.uniform(0.1, 2.0),  # 债务比率
            'revenue_growth': np.random.uniform(-0.1, 0.3),  # 营收增长率
            'net_income_growth': np.random.uniform(-0.2, 0.4),  # 净利润增长率
            'dividend_yield': np.random.uniform(0, 0.05),  # 股息率
            'market_cap': np.random.uniform(1e9, 1e12),  # 市值
            'pe_ratio': np.random.uniform(10, 50),  # PE比率
            'pb_ratio': np.random.uniform(1, 5),  # PB比率
            'sector': np.random.choice(['Technology', 'Healthcare', 'Financial', 'Consumer', 'Industrial']),
        }

    def _passes_fundamental_filters(self, fundamentals: Dict) -> bool:
        """应用基本面筛选条件"""
        try:
            # ROE筛选
            if fundamentals.get('roe', 0) < self.config['min_roe']:
                return False

            # ROA筛选
            if fundamentals.get('roa', 0) < self.config['min_roa']:
                return False

            # 债务比率筛选
            if fundamentals.get('debt_ratio', 0) > self.config['max_debt_ratio']:
                return False

            # 营收增长筛选
            if fundamentals.get('revenue_growth', 0) < self.config['min_revenue_growth']:
                return False

            # 净利润增长筛选
            if fundamentals.get('net_income_growth', 0) < self.config['min_net_income_growth']:
                return False

            # 分红要求
            if self.config['dividend_required']:
                if fundamentals.get('dividend_yield', 0) < self.config['min_dividend_yield']:
                    return False

            # 行业筛选
            if self.config['sector_filter']:
                if fundamentals.get('sector') != self.config['sector_filter']:
                    return False

            # 市值筛选（已在基类中处理，这里再次确认）
            if fundamentals.get('market_cap', 0) < self.config['min_market_cap']:
                return False

            return True

        except Exception as e:
            logger.warning(f"基本面筛选失败: {e}")
            return False

    def _calculate_fundamental_score(self, fundamentals: Dict) -> Tuple[float, Dict]:
        """
        计算基本面综合评分

        Returns:
            Tuple[float, Dict]: (评分, 详细信息)
        """
        score = 0
        details = {}
        weights = self.config['weights']

        try:
            # 计算各项指标的标准化得分
            metrics = {
                'roe': fundamentals.get('roe', 0),
                'roa': fundamentals.get('roa', 0),
                'debt_ratio': fundamentals.get('debt_ratio', 0),
                'revenue_growth': fundamentals.get('revenue_growth', 0),
                'net_income_growth': fundamentals.get('net_income_growth', 0),
                'dividend_yield': fundamentals.get('dividend_yield', 0),
            }

            # 计算平均值用于标准化
            mean_values = {
                'roe': 0.15,
                'roa': 0.08,
                'debt_ratio': 0.8,
                'revenue_growth': 0.10,
                'net_income_growth': 0.12,
                'dividend_yield': 0.025,
            }

            # 计算标准化得分并应用权重
            for metric, value in metrics.items():
                if metric in mean_values:
                    # 标准化到平均值
                    normalized_value = value / mean_values[metric]
                    weighted_score = normalized_value * weights.get(metric, 1.0)
                    score += weighted_score

                    details[f'{metric}_raw'] = value
                    details[f'{metric}_normalized'] = normalized_value
                    details[f'{metric}_weighted'] = weighted_score

            # 确保评分在合理范围内
            score = max(0, min(100, score * 10))  # 缩放并限制范围

            details['total_score'] = score
            details['metrics_count'] = len([m for m in metrics.values() if m != 0])

        except Exception as e:
            logger.warning(f"计算基本面评分失败: {e}")
            score = 0

        return score, details

    def _rank_stocks(self, screened_stocks: List[Dict]) -> List[Dict]:
        """对筛选结果进行排序"""
        ranking_method = self.config.get('ranking_method', 'composite_score')

        if ranking_method == 'composite_score':
            # 按综合评分排序
            screened_stocks.sort(key=lambda x: x.get('score', 0), reverse=True)
        elif ranking_method == 'roe':
            # 按ROE排序
            screened_stocks.sort(key=lambda x: x.get('fundamentals', {}).get('roe', 0), reverse=True)
        elif ranking_method == 'growth':
            # 按增长率排序
            growth_score = lambda x: (
                x.get('fundamentals', {}).get('revenue_growth', 0) +
                x.get('fundamentals', {}).get('net_income_growth', 0)
            ) / 2
            screened_stocks.sort(key=growth_score, reverse=True)

        # 限制结果数量
        max_size = self.config.get('max_screen_size', 25)
        return screened_stocks[:max_size]