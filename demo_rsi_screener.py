#!/usr/bin/env python3
"""
RSI选股策略专用演示
展示如何使用RSI动量策略进行股票筛选
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
            # print(data)

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

def demo_rsi_oversold(data_provider):
    """演示RSI超卖筛选"""
    print("📈 RSI超卖选股演示")
    print("=" * 40)

    # 初始化
    screener_manager = ScreenerManager(data_provider)

    # 配置RSI超卖策略
    config = {
        'signal_type': 'oversold',  # 超卖信号
        'rsi_period': 14,  # RSI周期
        'oversold_threshold': 30,  # 超卖阈值
        'lookback_period': 14,  # 回望周期
        'require_trend_confirmation': True,  # 需要趋势确认
        'trend_period': 50,  # 趋势确认周期
        'max_screen_size': 10  # 最大筛选数量
    }

    print("🎯 策略配置:")
    for key, value in config.items():
        print(f"   {key}: {value}")

    # 执行筛选
    print("\n⚡ 执行RSI超卖筛选...")
    results = screener_manager.run_screener('rsi', config)

    print(f"✅ 筛选完成! 找到 {len(results)} 只超卖股票")

    if results:
        print("\n🏆 超卖股票列表:")
        print("排名 | 股票代码 | RSI值 | 信号强度 | 置信度")
        print("-" * 50)
        for i, stock in enumerate(results, 1):
            rsi_value = stock['details'].get('current_rsi', 0)
            signal_strength = stock['details'].get('signal_strength', 0)
            confidence = stock.get('confidence', 0)
            print(f"{i:2d} | {stock['symbol']:8s} | {rsi_value:6.2f} | {signal_strength:6.1f} | {confidence:.2f}")

        # 导出结果
        try:
            screener_manager.export_results(results, "rsi_oversold_results", format='csv')
            print("💾 超卖结果已导出为 CSV 文件")
            screener_manager.export_results(results, "rsi_oversold_results", format='json')
            print("💾 超卖结果已导出为 JSON 文件")
        except Exception as e:
            print(f"❌ 导出失败: {e}")
    else:
        print("ℹ️ 没有找到符合条件的超卖股票")

    return results

def demo_rsi_overbought(data_provider):
    """演示RSI超买筛选"""
    print("\n📉 RSI超买选股演示")
    print("=" * 40)

    # 初始化
    screener_manager = ScreenerManager(data_provider)

    # 配置RSI超买策略
    config = {
        'signal_type': 'overbought',  # 超买信号
        'rsi_period': 14,
        'overbought_threshold': 70,  # 超买阈值
        'lookback_period': 5,  # 短期平均
        'require_trend_confirmation': False,  # 不需要趋势确认
        'max_screen_size': 10
    }

    print("🎯 策略配置:")
    for key, value in config.items():
        print(f"   {key}: {value}")

    # 执行筛选
    print("\n⚡ 执行RSI超买筛选...")
    results = screener_manager.run_screener('rsi', config)

    print(f"✅ 筛选完成! 找到 {len(results)} 只超买股票")

    if results:
        print("\n🏆 超买股票列表:")
        print("排名 | 股票代码 | RSI值 | 信号强度 | 置信度")
        print("-" * 50)
        for i, stock in enumerate(results, 1):
            rsi_value = stock['details'].get('current_rsi', 0)
            signal_strength = stock['details'].get('signal_strength', 0)
            confidence = stock.get('confidence', 0)
            print(f"{i:2d} | {stock['symbol']:8s} | {rsi_value:6.2f} | {signal_strength:6.1f} | {confidence:.2f}")

        # 导出结果
        try:
            screener_manager.export_results(results, "rsi_overbought_results", format='csv')
            print("💾 超买结果已导出为 CSV 文件")
            screener_manager.export_results(results, "rsi_overbought_results", format='json')
            print("💾 超买结果已导出为 JSON 文件")
        except Exception as e:
            print(f"❌ 导出失败: {e}")
    else:
        print("ℹ️ 没有找到符合条件的超买股票")

    return results

def demo_rsi_combined(data_provider):
    """演示RSI双向筛选（超卖+超买）"""
    print("\n🔄 RSI双向选股演示")
    print("=" * 40)

    # 初始化
    screener_manager = ScreenerManager(data_provider)

    # 配置双向RSI策略
    config = {
        'signal_type': 'both',  # 同时筛选超卖和超买
        'rsi_period': 14,
        'oversold_threshold': 35,  # 放宽超卖阈值
        'overbought_threshold': 65,  # 放宽超买阈值
        'lookback_period': 10,
        'require_trend_confirmation': True,
        'max_screen_size': 15
    }

    print("🎯 策略配置:")
    for key, value in config.items():
        print(f"   {key}: {value}")

    # 执行筛选
    print("\n⚡ 执行RSI双向筛选...")
    results = screener_manager.run_screener('rsi', config)

    print(f"✅ 筛选完成! 找到 {len(results)} 只股票")

    if results:
        print("\n🏆 双向信号股票列表:")
        print("排名 | 股票代码 | 信号类型 | RSI值 | 信号强度 | 置信度")
        print("-" * 60)
        for i, stock in enumerate(results, 1):
            signal_type = stock.get('signal_type', 'unknown')
            rsi_value = stock['details'].get('current_rsi', 0)
            signal_strength = stock['details'].get('signal_strength', 0)
            confidence = stock.get('confidence', 0)
            print(f"{i:2d} | {stock['symbol']:8s} | {signal_type:8s} | {rsi_value:6.2f} | {signal_strength:6.1f} | {confidence:.2f}")

        # 导出结果
        try:
            screener_manager.export_results(results, "rsi_combined_results", format='csv')
            print("💾 双向筛选结果已导出为 CSV 文件")
            screener_manager.export_results(results, "rsi_combined_results", format='json')
            print("💾 双向筛选结果已导出为 JSON 文件")
        except Exception as e:
            print(f"❌ 导出失败: {e}")
    else:
        print("ℹ️ 没有找到符合条件的股票")

    return results

def demo_rsi_comparison(data_provider):
    """演示不同RSI配置的对比"""
    print("\n⚖️ RSI策略配置对比演示")
    print("=" * 50)

    screener_manager = ScreenerManager(data_provider)

    # 不同的配置方案
    configs = {
        '保守超卖': {
            'signal_type': 'oversold',
            'oversold_threshold': 25,
            'require_trend_confirmation': True
        },
        '激进超卖': {
            'signal_type': 'oversold',
            'oversold_threshold': 35,
            'require_trend_confirmation': False
        },
        '保守超买': {
            'signal_type': 'overbought',
            'overbought_threshold': 75,
            'require_trend_confirmation': True
        },
        '激进超买': {
            'signal_type': 'overbought',
            'overbought_threshold': 65,
            'require_trend_confirmation': False
        }
    }

    results_summary = {}

    print("🎯 对比不同RSI配置:")
    print("配置名称 | 筛选股票数 | 平均评分 | 执行时间")
    print("-" * 50)

    for name, config in configs.items():
        import time
        start_time = time.time()

        results = screener_manager.run_screener('rsi', config)
        end_time = time.time()

        avg_score = sum(r['score'] for r in results) / len(results) if results else 0
        exec_time = end_time - start_time

        results_summary[name] = results

        print(f"{name:8s} | {len(results):8d} | {avg_score:8.1f} | {exec_time:.3f}")

    # 找出最佳配置
    best_config = max(results_summary.items(), key=lambda x: len(x[1]))
    print(f"\n🏆 最佳配置: {best_config[0]} (筛选出 {len(best_config[1])} 只股票)")

    return results_summary

def main():
    """主演示函数"""
    print("🚀 RSI选股策略演示")
    print("基于相对强弱指数(RSI)的动量选股策略")
    print("=" * 60)

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

    try:
        # 演示1: RSI超卖筛选
        oversold_results = demo_rsi_oversold(data_provider)

        # 演示2: RSI超买筛选
        overbought_results = demo_rsi_overbought(data_provider)

        # 演示3: RSI双向筛选
        combined_results = demo_rsi_combined(data_provider)

        # 演示4: 配置对比
        comparison_results = demo_rsi_comparison(data_provider)

        print("\n" + "=" * 60)
        print("📊 演示总结")
        print("=" * 60)
        print(f"超卖筛选结果: {len(oversold_results)} 只股票")
        print(f"超买筛选结果: {len(overbought_results)} 只股票")
        print(f"双向筛选结果: {len(combined_results)} 只股票")

        print("\n💡 RSI策略使用建议:")
        print("1. 超卖信号( RSI < 30): 适合寻找买入机会")
        print("2. 超买信号(RSI > 70): 适合寻找卖出机会")
        print("3. 结合趋势确认: 可以提高信号质量")
        print("4. 调整阈值: 根据市场环境调整敏感度")
        print("5. 多时间周期: 结合不同周期的RSI信号")

        print("\n🎯 策略参数说明:")
        print("- rsi_period: RSI计算周期(默认14)")
        print("- oversold_threshold: 超卖阈值(默认30)")
        print("- overbought_threshold: 超买阈值(默认70)")
        print("- lookback_period: 平均RSI计算周期")
        print("- require_trend_confirmation: 是否需要趋势确认")

        print("\n✅ RSI选股策略演示完成!")

    except Exception as e:
        print(f"❌ 演示过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()