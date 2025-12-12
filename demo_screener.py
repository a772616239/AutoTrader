#!/usr/bin/env python3
"""
选股策略使用演示
展示如何使用选股策略管理器进行股票筛选
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import requests
import pandas as pd
import numpy as np
from datetime import datetime
from strategies.screener_manager import ScreenerManager
from Test.test_screeners import MockDataProvider
from config import CONFIG

class EnhancedServerClient:
    """直接调用enhanced_http_server API的客户端"""

    def __init__(self, server_url="http://localhost:8001"):
        self.server_url = server_url
        self.session = requests.Session()
        self.session.timeout = 30

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

            print(f"从enhanced_server获取到 {len(df)} 条 {symbol} 数据")
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
                if value is None or (isinstance(value, float) and (pd.isna(value) or np.isinf(value))):
                    fundamentals[key] = 0

            print(f"从enhanced_server获取到 {symbol} 基本面数据")
            return fundamentals

        except Exception as e:
            print(f"获取基本面数据失败 {symbol}: {e}")
            return {}

def main():
    print("🚀 选股策略演示")
    print("=" * 50)

    # 选择数据源
    print("请选择数据源:")
    print("1. 模拟数据 (快速演示，不需要网络)")
    print("2. 真实数据 (直接调用enhanced_http_server API)")
    choice = input("请选择 (1或2) [默认1]: ").strip()

    if choice == "2":
        print("🔗 使用真实数据源 (enhanced_http_server API)")
        data_provider = EnhancedServerClient()
    else:
        print("🎭 使用模拟数据源 (MockDataProvider)")
        data_provider = MockDataProvider()

    # 1. 初始化数据提供者
    print("📊 初始化数据提供者...")

    # 2. 创建选股策略管理器
    print("🎯 创建选股策略管理器...")
    screener_manager = ScreenerManager(data_provider)

    # 3. 查看可用策略
    available_screeners = screener_manager.get_available_screeners()
    
    print(f"📋 可用选股策略: {available_screeners}")

    if not available_screeners:
        print("❌ 没有找到可用的选股策略")
        return

    # 4. 演示单个策略筛选
    print("\n" + "=" * 50)
    print("📈 单个策略筛选演示")

    # 选择第一个可用的策略
    strategy_name = available_screeners[0]
    print(f"🎯 执行策略: {strategy_name}")

    try:
        results = screener_manager.run_screener(strategy_name)
        print(f"✅ 筛选完成! 找到 {len(results)} 只股票")

        if results:
            print("\n🏆 筛选结果 (前5只):")
            for i, stock in enumerate(results[:5], 1):
                print(f"{i}. {stock['symbol']} - 评分: {stock['score']:.2f}")

    except Exception as e:
        print(f"❌ 策略执行失败: {e}")

    # 5. 演示组合策略
    print("\n" + "=" * 50)
    print("🔄 组合策略演示")

    if len(available_screeners) >= 2:
        # 配置多个策略
        screener_configs = {}
        for strategy in available_screeners[:2]:  # 最多使用2个策略
            screener_configs[strategy] = {
                'max_screen_size': 10  # 限制每策略最多返回10只股票
            }

        print(f"🎯 执行组合策略: {list(screener_configs.keys())}")

        try:
            # 运行多个策略
            multi_results = screener_manager.run_multiple_screeners(screener_configs)

            print("📊 各策略结果:")
            for name, results in multi_results.items():
                print(f"  {name}: {len(results)} 只股票")

            # 演示结果合并
            results_list = list(multi_results.values())

            # 交集合并 (所有策略都选中的股票)
            intersection = screener_manager.combine_results(results_list, method='intersection')
            print(f"🔗 交集合并: {len(intersection)} 只股票")

            # 并集合并 (任意策略选中的股票)
            union = screener_manager.combine_results(results_list, method='union')
            print(f"➕ 并集合并: {len(union)} 只股票")

            # 加权合并 (基于评分智能合并)
            weighted = screener_manager.combine_results(results_list, method='weighted')
            print(f"⚖️ 加权合并: {len(weighted)} 只股票")

            if weighted:
                print("\n🏆 加权合并结果 (前3只):")
                for i, stock in enumerate(weighted[:3], 1):
                    strategies_count = stock.get('strategies_count', 1)
                    print(f"{i}. {stock['symbol']} - 评分: {stock['score']:.2f} (来自{strategies_count}个策略)")

        except Exception as e:
            print(f"❌ 组合策略执行失败: {e}")

    # 6. 演示导出功能
    print("\n" + "=" * 50)
    print("💾 导出功能演示")

    try:
        if 'weighted' in locals() and weighted:
            # 导出为CSV
            screener_manager.export_results(weighted, "demo_screener_results", format='csv')
            print("✅ 结果已导出为 CSV 文件")

            # 导出为JSON
            screener_manager.export_results(weighted, "demo_screener_results", format='json')
            print("✅ 结果已导出为 JSON 文件")

        else:
            print("ℹ️ 没有结果可导出")

    except Exception as e:
        print(f"❌ 导出失败: {e}")

    # 7. 显示统计信息
    print("\n" + "=" * 50)
    print("📊 策略统计信息")

    all_stats = screener_manager.get_all_stats()
    for name, stats in all_stats.items():
        print(f"🎯 {name}:")
        print(f"   执行次数: {stats['total_screenings']}")
        print(f"   处理股票: {stats['stocks_screened']}")
        print(f"   筛选通过: {stats['stocks_passed']}")
        print(f"   平均时间: {stats['avg_processing_time']:.3f}")
        print()

    print("🎉 选股策略演示完成!")
    print("\n💡 使用提示:")
    print("1. 修改 screener_configs 来自定义策略参数")
    print("2. 使用不同的合并方法获得不同筛选结果")
    print("3. 查看 strategies/ 目录添加新的选股策略")
    print("4. 运行 Test/test_screeners.py 查看详细测试")

if __name__ == "__main__":
    main()