#!/usr/bin/env python3
"""
选股策略测试脚本
测试各种选股策略的功能和性能
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import time
import requests

from strategies.screener_manager import ScreenerManager
from data.data_provider import DataProvider
from config import CONFIG


class MockDataProvider:
    """模拟数据提供者，用于测试"""

    def __init__(self):
        self.stock_data = {}
        self.fundamental_data = {}
        self._generate_mock_data()

    def _generate_mock_data(self):
        """生成模拟股票数据"""
        # 从配置中获取股票列表
        symbols = CONFIG.get('trading', {}).get('symbols')
        print(f"生成模拟数据，股票列表: {symbols}")
        # 如果symbols太多，只取前20个用于演示
        if len(symbols) > 20:
            symbols = symbols[:20]

        # 生成2年的日线数据
        dates = pd.date_range(start='2022-01-01', end='2024-01-01', freq='D')

        # 生成基准指数数据（S&P 500）
        np.random.seed(42)  # 固定种子确保基准数据一致
        initial_index = 4000
        index_changes = np.random.normal(0.0005, 0.015, len(dates))
        index_prices = initial_index * np.exp(np.cumsum(index_changes))

        benchmark_df = pd.DataFrame({
            'Open': index_prices * (1 + np.random.normal(0, 0.005, len(dates))),
            'High': index_prices * (1 + np.random.normal(0.002, 0.008, len(dates))),
            'Low': index_prices * (1 - np.random.normal(0.002, 0.008, len(dates))),
            'Close': index_prices,
            'Volume': np.random.uniform(1000000, 5000000, len(dates))
        }, index=dates)

        benchmark_df['High'] = np.maximum(benchmark_df['High'], benchmark_df[['Close', 'Open']].max(axis=1))
        benchmark_df['Low'] = np.minimum(benchmark_df['Low'], benchmark_df[['Close', 'Open']].min(axis=1))

        self.stock_data['^GSPC'] = benchmark_df

        for symbol in symbols:
            np.random.seed(hash(symbol) % 2**32)

            # 生成价格数据
            initial_price = np.random.uniform(50, 200)
            price_changes = np.random.normal(0.001, 0.02, len(dates))
            prices = initial_price * np.exp(np.cumsum(price_changes))

            # 生成成交量
            volumes = np.random.uniform(100000, 1000000, len(dates))

            # 创建DataFrame
            df = pd.DataFrame({
                'Open': prices * (1 + np.random.normal(0, 0.01, len(dates))),
                'High': prices * (1 + np.random.normal(0.005, 0.01, len(dates))),
                'Low': prices * (1 - np.random.normal(0.005, 0.01, len(dates))),
                'Close': prices,
                'Volume': volumes
            }, index=dates)

            # 确保High >= Close >= Low
            df['High'] = np.maximum(df['High'], df[['Close', 'Open']].max(axis=1))
            df['Low'] = np.minimum(df['Low'], df[['Close', 'Open']].min(axis=1))

            self.stock_data[symbol] = df

            # 生成基本面数据
            self.fundamental_data[symbol] = {
                'roe': np.random.uniform(0.05, 0.25),
                'roa': np.random.uniform(0.02, 0.15),
                'debt_ratio': np.random.uniform(0.1, 2.0),
                'revenue_growth': np.random.uniform(-0.1, 0.3),
                'net_income_growth': np.random.uniform(-0.2, 0.4),
                'dividend_yield': np.random.uniform(0, 0.05),
                'market_cap': np.random.uniform(1e9, 1e12),
                'pe_ratio': np.random.uniform(10, 50),
                'pb_ratio': np.random.uniform(1, 5),
                'sector': np.random.choice(['Technology', 'Healthcare', 'Financial', 'Consumer', 'Industrial']),
            }

    def get_stock_data(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """获取股票数据"""
        return self.stock_data.get(symbol, pd.DataFrame())

    def get_fundamental_data(self, symbol: str) -> dict:
        """获取基本面数据"""
        return self.fundamental_data.get(symbol, {})


class EnhancedServerDataProvider:
    """连接到enhanced_http_server获取真实数据"""

    def __init__(self, server_url="http://localhost:8001"):
        self.server_url = server_url
        self.session = requests.Session()
        self.session.timeout = 30  # 30秒超时

    def get_stock_data(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """从enhanced_server获取股票价格数据"""
        try:
            # 转换period格式
            period_mapping = {
                "1mo": "1mo", "3mo": "3mo", "6mo": "6mo",
                "1y": "1y", "2y": "2y", "5y": "5y"
            }
            server_period = period_mapping.get(period, "1y")

            url = f"{self.server_url}/enhanced-data?symbol={symbol}&period={server_period}&interval=1d"
            response = self.session.get(url)

            if response.status_code != 200:
                print(f"服务器响应错误: {response.status_code}")
                return pd.DataFrame()

            data = response.json()

            if "error" in data:
                print(f"服务器返回错误: {data['error']}")
                return pd.DataFrame()

            # 解析raw_data
            if "raw_data" not in data:
                print("服务器响应中没有raw_data")
                return pd.DataFrame()

            records = []
            for item in data["raw_data"]:
                try:
                    # 解析时间
                    time_str = item["time"]
                    if "T" in time_str:
                        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                    else:
                        dt = datetime.strptime(time_str, "%Y-%m-%d")

                    record = {
                        "Open": item.get("open"),
                        "High": item.get("high"),
                        "Low": item.get("low"),
                        "Close": item.get("close"),
                        "Volume": item.get("volume", 0),
                    }
                    records.append((dt, record))

                except Exception as e:
                    print(f"解析数据点失败: {e}")
                    continue

            if not records:
                return pd.DataFrame()

            # 创建DataFrame
            df = pd.DataFrame.from_records([r[1] for r in records], index=[r[0] for r in records])
            df = df.dropna()  # 移除NaN值

            print(f"从服务器获取到 {len(df)} 条 {symbol} 数据")
            return df

        except requests.exceptions.RequestException as e:
            print(f"网络请求失败: {e}")
            return pd.DataFrame()
        except Exception as e:
            print(f"获取股票数据失败 {symbol}: {e}")
            return pd.DataFrame()

    def get_fundamental_data(self, symbol: str) -> dict:
        """从enhanced_server获取基本面数据"""
        try:
            url = f"{self.server_url}/enhanced-data?symbol={symbol}&period=1mo&interval=1d"
            response = self.session.get(url)

            if response.status_code != 200:
                print(f"服务器响应错误: {response.status_code}")
                return {}

            data = response.json()

            if "error" in data:
                print(f"服务器返回错误: {data['error']}")
                return {}

            # 从company_info提取基本面数据
            company_info = data.get("company_info", {})

            fundamentals = {
                "roe": company_info.get("returnOnEquityTTM"),  # ROE
                "roa": company_info.get("returnOnAssets"),     # ROA
                "debt_ratio": company_info.get("debtToEquity"), # 债务比率
                "revenue_growth": company_info.get("revenueGrowth"), # 营收增长
                "net_income_growth": company_info.get("earningsGrowth"), # 利润增长
                "dividend_yield": company_info.get("dividendYield", 0), # 股息率
                "market_cap": company_info.get("marketCap"),   # 市值
                "pe_ratio": company_info.get("peRatio"),       # PE比率
                "pb_ratio": company_info.get("pbRatio"),       # PB比率
                "sector": company_info.get("sector"),          # 行业
            }

            # 清理数据
            for key, value in fundamentals.items():
                if value is None or (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
                    fundamentals[key] = 0

            print(f"从服务器获取到 {symbol} 基本面数据")
            return fundamentals

        except Exception as e:
            print(f"获取基本面数据失败 {symbol}: {e}")
            return {}
