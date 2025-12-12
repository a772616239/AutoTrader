#!/usr/bin/env python3
"""
选股策略基类
为各种选股策略提供统一的框架和接口
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class BaseScreener(ABC):
    """选股策略基类"""

    def __init__(self, config: Dict = None):
        self.config = self._default_config()
        if config:
            self.config.update(config)

        # 选股结果缓存
        self.screened_stocks = {}
        self.last_screened = None

        # 性能统计
        self.screening_stats = {
            'total_screenings': 0,
            'stocks_screened': 0,
            'stocks_passed': 0,
            'avg_processing_time': 0.0
        }

        logger.info(f"选股策略 {self.get_screener_name()} 初始化完成")

    def _default_config(self) -> Dict:
        """默认配置 - 子类应该重写此方法"""
        return {
            'universe': 'sp500',  # 股票池：sp500, nasdaq, nyse, custom
            'min_market_cap': 500000000,  # 最小市值
            'min_price': 5.0,  # 最小股价
            'min_volume': 100000,  # 最小成交量
            'max_screen_size': 50,  # 最大筛选结果数量
            'cache_duration_hours': 24,  # 缓存有效期（小时）
            'ranking_method': 'composite',  # 排序方法：score, alpha, custom
        }

    def get_screener_name(self) -> str:
        """获取选股策略名称"""
        return self.__class__.__name__

    @abstractmethod
    def screen_stocks(self, data_provider, **kwargs) -> List[Dict]:
        """
        执行选股筛选

        Args:
            data_provider: 数据提供者实例
            **kwargs: 额外的筛选参数

        Returns:
            List[Dict]: 筛选结果列表，每个元素包含股票信息和评分
        """
        pass

    def _get_universe_stocks(self, data_provider) -> List[str]:
        """获取股票池"""
        from config import CONFIG  # 导入配置

        universe = self.config.get('universe', 'sp500')

        if universe == 'sp500':
            # 从CONFIG获取trading.symbols，如果没有则返回示例股票列表
            symbols = CONFIG.get('trading', {}).get('symbols')
            if symbols:
                logger.info(f"从CONFIG获取股票池，共 {len(symbols)} 只股票")
                return symbols
            else:
                # 备用示例股票列表
                logger.warning("CONFIG中未找到trading.symbols，使用示例股票列表")
                return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX']
        elif universe == 'nasdaq':
            # NASDAQ股票池
            return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META']
        elif universe == 'nyse':
            # NYSE股票池
            return ['JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'BLK']
        else:
            # 自定义股票池
            return self.config.get('custom_universe', [])

    def _filter_basic_criteria(self, stocks_data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """应用基本筛选条件"""
        filtered_data = {}

        min_price = self.config.get('min_price', 5.0)
        min_volume = self.config.get('min_volume', 100000)
        min_market_cap = self.config.get('min_market_cap', 500000000)

        for symbol, data in stocks_data.items():
            if data.empty or len(data) < 5:
                continue

            # 价格筛选
            current_price = data['Close'].iloc[-1]
            if current_price < min_price:
                continue

            # 成交量筛选
            if 'Volume' in data.columns:
                avg_volume = data['Volume'].tail(20).mean()
                if pd.isna(avg_volume) or avg_volume < min_volume:
                    continue

            # 这里可以添加市值筛选（需要从data_provider获取市值数据）

            filtered_data[symbol] = data

        return filtered_data

    def _rank_stocks(self, screened_stocks: List[Dict]) -> List[Dict]:
        """对筛选结果进行排序"""
        ranking_method = self.config.get('ranking_method', 'composite')

        if ranking_method == 'score':
            # 按综合评分排序
            screened_stocks.sort(key=lambda x: x.get('score', 0), reverse=True)
        elif ranking_method == 'alpha':
            # 按预期收益率排序
            screened_stocks.sort(key=lambda x: x.get('expected_return', 0), reverse=True)
        elif ranking_method == 'composite':
            # 综合排序：评分 * 置信度
            for stock in screened_stocks:
                stock['composite_score'] = stock.get('score', 0) * stock.get('confidence', 0.5)
            screened_stocks.sort(key=lambda x: x.get('composite_score', 0), reverse=True)

        # 限制结果数量
        max_size = self.config.get('max_screen_size', 50)
        return screened_stocks[:max_size]

    def _cache_results(self, results: List[Dict]):
        """缓存筛选结果"""
        self.screened_stocks = {stock['symbol']: stock for stock in results}
        self.last_screened = datetime.now()

    def _get_cached_results(self) -> Optional[List[Dict]]:
        """获取缓存的筛选结果"""
        if not self.last_screened:
            return None

        cache_duration = timedelta(hours=self.config.get('cache_duration_hours', 24))
        if datetime.now() - self.last_screened > cache_duration:
            return None

        return list(self.screened_stocks.values())

    def _update_stats(self, processing_time: float, total_stocks: int, passed_stocks: int):
        """更新性能统计"""
        self.screening_stats['total_screenings'] += 1
        self.screening_stats['stocks_screened'] += total_stocks
        self.screening_stats['stocks_passed'] += passed_stocks

        # 更新平均处理时间
        current_avg = self.screening_stats['avg_processing_time']
        total_screenings = self.screening_stats['total_screenings']
        self.screening_stats['avg_processing_time'] = (
            (current_avg * (total_screenings - 1)) + processing_time
        ) / total_screenings

    def get_stats(self) -> Dict:
        """获取性能统计"""
        return self.screening_stats.copy()

    def clear_cache(self):
        """清除缓存"""
        self.screened_stocks.clear()
        self.last_screened = None
        logger.info(f"{self.get_screener_name()} 缓存已清除")