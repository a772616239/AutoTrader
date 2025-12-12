#!/usr/bin/env python3
"""
基本面选股策略专用演示
展示如何使用基本面多因子策略进行股票筛选
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

            # yfinance只提供有限的基本面数据，我们需要生成模拟数据
            # 注意：yfinance的dividendYield已经是百分比形式（如0.32表示3.2%）
            dividend_yield_raw = company_info.get("dividendYield", 0)
            # 如果dividendYield大于1，说明它已经是百分比形式，直接使用
            # 如果小于1，说明是小数形式，需要乘以100转换为百分比
            if dividend_yield_raw > 1:
                dividend_yield = dividend_yield_raw  # 已经是百分比
            else:
                dividend_yield = dividend_yield_raw * 100  # 转换为百分比

            fundamentals = {
                "dividend_yield": dividend_yield, # 股息率（百分比）
                "market_cap": company_info.get("marketCap", 0),   # 市值
                "pe_ratio": company_info.get("peRatio", 0),       # PE比率
                "sector": company_info.get("sector", "Unknown"),  # 行业
                "beta": company_info.get("beta", 1.0),  # Beta系数
            }

            # 生成基于市值和行业的模拟基本面数据
            market_cap = fundamentals["market_cap"]
            sector = fundamentals["sector"]

            # 设置随机种子以确保结果一致性
            np.random.seed(hash(symbol) % 2**32)

            # 根据市值调整财务比率
            if market_cap > 100000000000:  # 大型公司 (>1000亿)
                fundamentals["roe"] = np.random.uniform(0.12, 0.25)
                fundamentals["roa"] = np.random.uniform(0.08, 0.18)
                fundamentals["debt_ratio"] = np.random.uniform(0.3, 1.2)
                fundamentals["pb_ratio"] = np.random.uniform(2.0, 5.0)
            elif market_cap > 10000000000:  # 中型公司 (>100亿)
                fundamentals["roe"] = np.random.uniform(0.08, 0.20)
                fundamentals["roa"] = np.random.uniform(0.05, 0.15)
                fundamentals["debt_ratio"] = np.random.uniform(0.4, 1.5)
                fundamentals["pb_ratio"] = np.random.uniform(1.5, 4.0)
            else:  # 小型公司
                fundamentals["roe"] = np.random.uniform(0.05, 0.18)
                fundamentals["roa"] = np.random.uniform(0.02, 0.12)
                fundamentals["debt_ratio"] = np.random.uniform(0.5, 2.0)
                fundamentals["pb_ratio"] = np.random.uniform(1.0, 3.5)

            # 根据行业调整增长指标
            if sector == "Technology":
                fundamentals["revenue_growth"] = np.random.uniform(0.08, 0.25)
                fundamentals["net_income_growth"] = np.random.uniform(0.10, 0.35)
            elif sector == "Healthcare":
                fundamentals["revenue_growth"] = np.random.uniform(0.05, 0.15)
                fundamentals["net_income_growth"] = np.random.uniform(0.03, 0.20)
            elif sector == "Financial":
                fundamentals["revenue_growth"] = np.random.uniform(0.02, 0.12)
                fundamentals["net_income_growth"] = np.random.uniform(0.01, 0.15)
            elif sector == "Consumer Cyclical":
                fundamentals["revenue_growth"] = np.random.uniform(0.03, 0.18)
                fundamentals["net_income_growth"] = np.random.uniform(0.02, 0.25)
            else:
                fundamentals["revenue_growth"] = np.random.uniform(0.03, 0.18)
                fundamentals["net_income_growth"] = np.random.uniform(0.02, 0.22)

            # 清理数据
            for key, value in fundamentals.items():
                if value is None or (isinstance(value, float) and (pd.isna(value) or np.isinf(value))):
                    fundamentals[key] = 0

            print(f"从enhanced_server获取到 {symbol} 基本面数据 (包含模拟财务比率)")
            return fundamentals

        except Exception as e:
            print(f"获取基本面数据失败 {symbol}: {e}")
            return {}

def demo_fundamental_growth(data_provider):
    """演示成长型基本面筛选"""
    print("📈 成长型基本面选股演示")
    print("=" * 45)

    # 初始化
    screener_manager = ScreenerManager(data_provider)

    # 配置成长型策略 - 注重增长指标
    config = {
        'min_roe': 0.12,  # ROE > 12%
        'min_roa': 0.06,  # ROA > 6%
        'max_debt_ratio': 1.5,  # 债务比率 < 150%
        'min_revenue_growth': 0.08,  # 营收增长 > 8%
        'min_net_income_growth': 0.10,  # 净利润增长 > 10%
        'dividend_required': False,  # 不强制要求分红
        'weights': {
            'roe': 1.3,  # ROE权重更高
            'roa': 1.2,
            'debt_ratio': -1.5,  # 债务比率负权重
            'revenue_growth': 1.4,  # 营收增长权重最高
            'net_income_growth': 1.5,  # 净利润增长权重最高
            'dividend_yield': 0.5,  # 分红权重较低
        },
        'max_screen_size': 10
    }

    print("🎯 策略配置 (成长型):")
    for key, value in config.items():
        if key != 'weights':
            print(f"   {key}: {value}")
    print("   weights: 自定义权重配置")

    # 执行筛选
    print("\n⚡ 执行成长型基本面筛选...")
    results = screener_manager.run_screener('fundamental', config)

    print(f"✅ 筛选完成! 找到 {len(results)} 只成长股")

    if results:
        print("\n🏆 成长股列表:")
        print("排名 | 股票代码 | 综合评分 | ROE | ROA | 营收增长 | 净利润增长")
        print("-" * 70)
        for i, stock in enumerate(results, 1):
            fundamentals = stock.get('fundamentals', {})
            roe = fundamentals.get('roe', 0)
            roa = fundamentals.get('roa', 0)
            rev_growth = fundamentals.get('revenue_growth', 0)
            net_growth = fundamentals.get('net_income_growth', 0)
            score = stock.get('score', 0)
            print(f"{i:2d} | {stock['symbol']:8s} | {score:8.1f} | {roe:6.1%} | {roa:6.1%} | {rev_growth:8.1%} | {net_growth:10.1%}")

        # 导出结果
        try:
            screener_manager.export_results(results, "fundamental_growth_results", format='csv')
            print("💾 成长型结果已导出为 CSV 文件")
            screener_manager.export_results(results, "fundamental_growth_results", format='json')
            print("💾 成长型结果已导出为 JSON 文件")
        except Exception as e:
            print(f"❌ 导出失败: {e}")
    else:
        print("ℹ️ 没有找到符合条件的成长股")

    return results

def demo_fundamental_value(data_provider):
    """演示价值型基本面筛选"""
    print("\n💰 价值型基本面选股演示")
    print("=" * 45)

    # 初始化
    screener_manager = ScreenerManager(data_provider)

    # 配置价值型策略 - 注重稳定和分红
    config = {
        'min_roe': 0.08,  # ROE > 8% (相对宽松)
        'min_roa': 0.04,  # ROA > 4%
        'max_debt_ratio': 1.0,  # 债务比率 < 100% (更保守)
        'min_revenue_growth': 0.03,  # 营收增长 > 3% (相对稳定)
        'min_net_income_growth': 0.02,  # 净利润增长 > 2%
        'dividend_required': True,  # 必须有分红
        'min_dividend_yield': 0.025,  # 股息率 > 2.5%
        'weights': {
            'roe': 1.0,
            'roa': 1.1,
            'debt_ratio': -1.2,  # 债务控制更重要
            'revenue_growth': 0.8,  # 增长权重较低
            'net_income_growth': 0.9,
            'dividend_yield': 1.4,  # 分红权重最高
        },
        'max_screen_size': 10
    }

    print("🎯 策略配置 (价值型):")
    for key, value in config.items():
        if key != 'weights':
            print(f"   {key}: {value}")
    print("   weights: 价值投资权重配置")

    # 执行筛选
    print("\n⚡ 执行价值型基本面筛选...")
    results = screener_manager.run_screener('fundamental', config)

    print(f"✅ 筛选完成! 找到 {len(results)} 只价值股")

    if results:
        print("\n🏆 价值股列表:")
        print("排名 | 股票代码 | 综合评分 | ROE | ROA | 债务比率 | 股息率")
        print("-" * 65)
        for i, stock in enumerate(results, 1):
            fundamentals = stock.get('fundamentals', {})
            roe = fundamentals.get('roe', 0)
            roa = fundamentals.get('roa', 0)
            debt_ratio = fundamentals.get('debt_ratio', 0)
            dividend_yield = fundamentals.get('dividend_yield', 0)
            score = stock.get('score', 0)
            print(f"{i:2d} | {stock['symbol']:8s} | {score:8.1f} | {roe:6.1%} | {roa:6.1%} | {debt_ratio:8.1f} | {dividend_yield:6.1%}")

        # 导出结果
        try:
            screener_manager.export_results(results, "fundamental_value_results", format='csv')
            print("💾 价值型结果已导出为 CSV 文件")
            screener_manager.export_results(results, "fundamental_value_results", format='json')
            print("💾 价值型结果已导出为 JSON 文件")
        except Exception as e:
            print(f"❌ 导出失败: {e}")
    else:
        print("ℹ️ 没有找到符合条件的价值股")

    return results

def demo_fundamental_balanced(data_provider):
    """演示均衡型基本面筛选"""
    print("\n⚖️ 均衡型基本面选股演示")
    print("=" * 45)

    # 初始化
    screener_manager = ScreenerManager(data_provider)

    # 配置均衡型策略 - 平衡增长和稳定
    config = {
        'min_roe': 0.10,  # ROE > 10%
        'min_roa': 0.05,  # ROA > 5%
        'max_debt_ratio': 1.2,  # 债务比率 < 120%
        'min_revenue_growth': 0.05,  # 营收增长 > 5%
        'min_net_income_growth': 0.05,  # 净利润增长 > 5%
        'dividend_required': False,  # 可选分红
        'min_dividend_yield': 0.015,  # 股息率 > 1.5% (如果有分红)
        'weights': {
            'roe': 1.2,  # 盈利能力重要
            'roa': 1.1,
            'debt_ratio': -1.1,  # 财务稳健重要
            'revenue_growth': 1.0,  # 增长适中重要
            'net_income_growth': 1.1,
            'dividend_yield': 0.8,  # 分红有益但不强制
        },
        'max_screen_size': 15
    }

    print("🎯 策略配置 (均衡型):")
    for key, value in config.items():
        if key != 'weights':
            print(f"   {key}: {value}")
    print("   weights: 均衡配置权重")

    # 执行筛选
    print("\n⚡ 执行均衡型基本面筛选...")
    results = screener_manager.run_screener('fundamental', config)

    print(f"✅ 筛选完成! 找到 {len(results)} 只均衡股")

    if results:
        print("\n🏆 均衡股列表:")
        print("排名 | 股票代码 | 综合评分 | ROE | ROA | 营收增长 | 债务比率 | 股息率")
        print("-" * 80)
        for i, stock in enumerate(results, 1):
            fundamentals = stock.get('fundamentals', {})
            roe = fundamentals.get('roe', 0)
            roa = fundamentals.get('roa', 0)
            rev_growth = fundamentals.get('revenue_growth', 0)
            debt_ratio = fundamentals.get('debt_ratio', 0)
            dividend_yield = fundamentals.get('dividend_yield', 0)
            score = stock.get('score', 0)
            print(f"{i:2d} | {stock['symbol']:8s} | {score:8.1f} | {roe:6.1%} | {roa:6.1%} | {rev_growth:8.1%} | {debt_ratio:8.1f} | {dividend_yield:6.1%}")

        # 导出结果
        try:
            screener_manager.export_results(results, "fundamental_balanced_results", format='csv')
            print("💾 均衡型结果已导出为 CSV 文件")
            screener_manager.export_results(results, "fundamental_balanced_results", format='json')
            print("💾 均衡型结果已导出为 JSON 文件")
        except Exception as e:
            print(f"❌ 导出失败: {e}")
    else:
        print("ℹ️ 没有找到符合条件的均衡股")

    return results

def demo_fundamental_comparison(data_provider):
    """演示不同基本面配置的对比"""
    print("\n📊 基本面策略配置对比演示")
    print("=" * 55)

    screener_manager = ScreenerManager(data_provider)

    # 不同的配置方案
    configs = {
        '激进成长': {
            'min_roe': 0.15, 'min_revenue_growth': 0.12, 'max_debt_ratio': 2.0,
            'weights': {'revenue_growth': 1.5, 'net_income_growth': 1.4, 'roe': 1.2}
        },
        '稳健价值': {
            'min_roe': 0.08, 'min_revenue_growth': 0.02, 'max_debt_ratio': 0.8,
            'dividend_required': True, 'min_dividend_yield': 0.03,
            'weights': {'dividend_yield': 1.5, 'debt_ratio': -1.3, 'roe': 1.0}
        },
        '平衡配置': {
            'min_roe': 0.10, 'min_revenue_growth': 0.05, 'max_debt_ratio': 1.2,
            'weights': {'roe': 1.2, 'revenue_growth': 1.0, 'debt_ratio': -1.1}
        },
        '高分红': {
            'min_roe': 0.06, 'dividend_required': True, 'min_dividend_yield': 0.04,
            'weights': {'dividend_yield': 2.0, 'roe': 0.8, 'debt_ratio': -1.0}
        }
    }

    results_summary = {}

    print("🎯 对比不同基本面配置:")
    print("配置名称 | 筛选股票数 | 平均评分 | 平均ROE | 平均增长率")
    print("-" * 65)

    for name, config in configs.items():
        import time
        start_time = time.time()

        results = screener_manager.run_screener('fundamental', config)
        end_time = time.time()

        if results:
            avg_score = sum(r['score'] for r in results) / len(results)
            avg_roe = sum(r['fundamentals'].get('roe', 0) for r in results) / len(results)
            avg_growth = sum(r['fundamentals'].get('revenue_growth', 0) for r in results) / len(results)
        else:
            avg_score = avg_roe = avg_growth = 0

        exec_time = end_time - start_time
        results_summary[name] = results

        print(f"{name:8s} | {len(results):8d} | {avg_score:8.1f} | {avg_roe:8.1%} | {avg_growth:10.1%}")

    # 找出最佳配置
    best_config = max(results_summary.items(), key=lambda x: len(x[1]) if x[1] else 0)
    print(f"\n🏆 筛选最多股票配置: {best_config[0]} (筛选出 {len(best_config[1])} 只股票)")

    return results_summary

def main():
    """主演示函数"""
    print("🏢 基本面选股策略演示")
    print("基于财务比率和增长指标的多因子量化选股")
    print("=" * 70)

    # 默认使用真实数据源测试基本面功能
    print("🔗 使用真实数据源 (enhanced_http_server API)")
    data_provider = EnhancedServerClient()

    try:
        # 演示1: 成长型筛选
        growth_results = demo_fundamental_growth(data_provider)

        # 演示2: 价值型筛选
        value_results = demo_fundamental_value(data_provider)

        # 演示3: 均衡型筛选
        balanced_results = demo_fundamental_balanced(data_provider)

        # 演示4: 配置对比
        comparison_results = demo_fundamental_comparison(data_provider)

        print("\n" + "=" * 70)
        print("📊 演示总结")
        print("=" * 70)
        print(f"成长型筛选结果: {len(growth_results)} 只股票")
        print(f"价值型筛选结果: {len(value_results)} 只股票")
        print(f"均衡型筛选结果: {len(balanced_results)} 只股票")

        print("\n💡 基本面策略使用建议:")
        print("1. 成长型: 适合看好未来增长的投资者，注重ROE和营收增长")
        print("2. 价值型: 适合追求稳定收益的投资者，注重分红和低债务")
        print("3. 均衡型: 适合大多数投资者，在增长和稳定间取平衡")
        print("4. 根据市场环境调整权重: 牛市可增加成长权重，熊市可增加价值权重")
        print("5. 结合技术分析: 基本面选股后用技术指标确定买卖时机")

        print("\n🎯 关键财务指标说明:")
        print("- ROE (净资产收益率): 衡量盈利能力，>15%为优秀")
        print("- ROA (总资产收益率): 衡量运营效率，>8%为良好")
        print("- 债务比率: 衡量财务杠杆，<100%较为安全")
        print("- 营收增长率: 衡量业务扩张，>10%为高速增长")
        print("- 净利润增长率: 衡量盈利增长，>15%为优秀")
        print("- 股息率: 衡量分红收益，>3%为高分红")

        print("\n📁 导出文件说明:")
        print("- fundamental_growth_results.csv/json: 成长型选股结果")
        print("- fundamental_value_results.csv/json: 价值型选股结果")
        print("- fundamental_balanced_results.csv/json: 均衡型选股结果")

        print("\n✅ 基本面选股策略演示完成!")

    except Exception as e:
        print(f"❌ 演示过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()