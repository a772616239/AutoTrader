#!/usr/bin/env python3
"""
选股策略管理器
统一管理和执行各种选股策略
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
import importlib
import inspect

from .base_screener import BaseScreener

logger = logging.getLogger(__name__)

class ScreenerManager:
    """选股策略管理器"""

    def __init__(self, data_provider=None):
        self.data_provider = data_provider
        self.screeners = {}
        self._load_screeners()

    def _load_screeners(self):
        """动态加载所有选股策略"""
        try:
            import os
            import sys

            # 获取strategies目录路径
            strategies_dir = os.path.dirname(os.path.abspath(__file__))
            screener_classes = []

            # 扫描strategies目录中的screener文件
            for filename in os.listdir(strategies_dir):
                if (filename.startswith('screener_') and
                    filename.endswith('.py') and
                    not filename.endswith('_manager.py')):

                    module_name = filename[:-3]  # 移除.py扩展名
                    try:
                        # 动态导入模块
                        module = importlib.import_module(f'strategies.{module_name}')

                        # 查找继承自BaseScreener的类
                        for name, obj in inspect.getmembers(module):
                            if (inspect.isclass(obj) and
                                issubclass(obj, BaseScreener) and
                                obj != BaseScreener):
                                screener_classes.append((module_name, obj))
                                break  # 每个模块只取第一个符合条件的类

                    except Exception as e:
                        logger.warning(f"加载选股策略 {module_name} 失败: {e}")

            # 实例化所有选股策略
            for module_name, screener_class in screener_classes:
                try:
                    screener_name = module_name.replace('screener_', '')
                    self.screeners[screener_name] = screener_class()
                    logger.info(f"加载选股策略: {screener_name}")
                except Exception as e:
                    logger.error(f"实例化选股策略 {screener_class.__name__} 失败: {e}")

        except Exception as e:
            logger.error(f"加载选股策略失败: {e}")

    def get_available_screeners(self) -> List[str]:
        """获取所有可用的选股策略"""
        return list(self.screeners.keys())

    def get_screener(self, screener_name: str) -> Optional[BaseScreener]:
        """获取指定的选股策略"""
        return self.screeners.get(screener_name)

    def run_screener(self, screener_name: str, config: Dict = None, **kwargs) -> List[Dict]:
        """
        执行指定的选股策略

        Args:
            screener_name: 策略名称
            config: 策略配置
            **kwargs: 额外参数

        Returns:
            List[Dict]: 筛选结果
        """
        screener = self.get_screener(screener_name)
        if not screener:
            logger.error(f"未找到选股策略: {screener_name}")
            return []

        try:
            # 更新配置
            if config:
                screener.config.update(config)

            # 执行筛选
            results = screener.screen_stocks(self.data_provider, **kwargs)

            logger.info(f"选股策略 {screener_name} 执行完成，筛选出 {len(results)} 只股票")
            return results

        except Exception as e:
            logger.error(f"执行选股策略 {screener_name} 失败: {e}")
            return []

    def run_multiple_screeners(self, screener_configs: Dict[str, Dict]) -> Dict[str, List[Dict]]:
        """
        批量执行多个选股策略

        Args:
            screener_configs: 策略名称到配置的映射

        Returns:
            Dict[str, List[Dict]]: 各策略的筛选结果
        """
        results = {}

        for screener_name, config in screener_configs.items():
            results[screener_name] = self.run_screener(screener_name, config)

        return results

    def combine_results(self, results_list: List[List[Dict]], method: str = 'intersection') -> List[Dict]:
        """
        合并多个选股策略的结果

        Args:
            results_list: 多个策略的筛选结果列表
            method: 合并方法 - 'intersection', 'union', 'weighted'

        Returns:
            List[Dict]: 合并后的结果
        """
        if not results_list:
            return []

        if method == 'intersection':
            # 取交集 - 所有策略都选中的股票
            if len(results_list) == 1:
                return results_list[0]

            # 获取所有股票符号
            symbol_sets = [set(result['symbol'] for result in results) for results in results_list]

            # 取交集
            common_symbols = set.intersection(*symbol_sets)

            # 从第一个结果中筛选共同股票
            combined_results = [result for result in results_list[0] if result['symbol'] in common_symbols]

        elif method == 'union':
            # 取并集 - 任意策略选中的股票
            all_results = []
            seen_symbols = set()

            for results in results_list:
                for result in results:
                    if result['symbol'] not in seen_symbols:
                        all_results.append(result)
                        seen_symbols.add(result['symbol'])

            combined_results = all_results

        elif method == 'weighted':
            # 加权合并 - 基于多个策略的评分
            symbol_scores = {}

            for results in results_list:
                for result in results:
                    symbol = result['symbol']
                    score = result.get('score', 0)
                    confidence = result.get('confidence', 0.5)

                    if symbol not in symbol_scores:
                        symbol_scores[symbol] = {
                            'total_score': 0,
                            'count': 0,
                            'results': []
                        }

                    symbol_scores[symbol]['total_score'] += score * confidence
                    symbol_scores[symbol]['count'] += 1
                    symbol_scores[symbol]['results'].append(result)

            # 计算平均分数并排序
            combined_results = []
            for symbol, data in symbol_scores.items():
                avg_score = data['total_score'] / data['count']
                # 使用第一个结果作为基础，更新评分
                base_result = data['results'][0].copy()
                base_result['score'] = avg_score
                base_result['confidence'] = min(1.0, avg_score / 100.0)
                base_result['strategies_count'] = data['count']
                combined_results.append(base_result)

            # 按平均分排序
            combined_results.sort(key=lambda x: x['score'], reverse=True)

        else:
            logger.error(f"不支持的合并方法: {method}")
            return results_list[0] if results_list else []

        return combined_results

    def get_screener_stats(self, screener_name: str) -> Optional[Dict]:
        """获取指定选股策略的统计信息"""
        screener = self.get_screener(screener_name)
        if screener:
            return screener.get_stats()
        return None

    def get_all_stats(self) -> Dict[str, Dict]:
        """获取所有选股策略的统计信息"""
        stats = {}
        for name, screener in self.screeners.items():
            stats[name] = screener.get_stats()
        return stats

    def clear_all_cache(self):
        """清除所有选股策略的缓存"""
        for screener in self.screeners.values():
            screener.clear_cache()
        logger.info("已清除所有选股策略缓存")

    def export_results(self, results: List[Dict], filename: str = None, format: str = 'csv'):
        """
        导出筛选结果

        Args:
            results: 筛选结果
            filename: 导出文件名
            format: 导出格式 ('csv', 'json', 'excel')
        """
        if not results:
            logger.warning("没有结果可导出")
            return

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screener_results_{timestamp}"

        try:
            df = pd.DataFrame(results)

            if format == 'csv':
                df.to_csv(f"{filename}.csv", index=False)
            elif format == 'json':
                df.to_json(f"{filename}.json", orient='records', indent=2)
            elif format == 'excel':
                df.to_excel(f"{filename}.xlsx", index=False)
            else:
                logger.error(f"不支持的导出格式: {format}")

            logger.info(f"筛选结果已导出到 {filename}.{format}")

        except Exception as e:
            logger.error(f"导出筛选结果失败: {e}")