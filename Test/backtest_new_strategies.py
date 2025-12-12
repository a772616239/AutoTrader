#!/usr/bin/env python3
"""
新策略回测脚本
测试从Finance目录迁移过来的新策略性能
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from strategies.a23_aroon_oscillator import A23AroonOscillatorStrategy
from strategies.a24_ultimate_oscillator import A24UltimateOscillatorStrategy
from data.data_provider import DataProvider

def create_sample_data(symbol='AAPL', days=200):
    """创建示例数据用于回测"""
    np.random.seed(42)

    # 生成基础价格数据
    dates = pd.date_range('2024-01-01', periods=days, freq='D')

    # 模拟价格走势
    base_price = 150
    prices = [base_price]

    for i in range(1, days):
        # 添加趋势和随机波动
        trend = 0.001 if i > days//2 else -0.001  # 中间开始上涨
        shock = np.random.normal(0, 0.02)
        new_price = prices[-1] * (1 + trend + shock)
        prices.append(max(new_price, 50))  # 确保不低于50

    # 创建OHLCV数据
    data = pd.DataFrame({
        'Open': [p * (1 + np.random.normal(0, 0.005)) for p in prices],
        'High': [p * (1 + abs(np.random.normal(0, 0.01))) for p in prices],
        'Low': [p * (1 - abs(np.random.normal(0, 0.01))) for p in prices],
        'Close': prices,
        'Volume': np.random.randint(1000000, 5000000, days)
    }, index=dates)

    # 确保High >= Close >= Low
    data['High'] = np.maximum(data['High'], data['Close'])
    data['Low'] = np.minimum(data['Low'], data['Close'])

    return data

def backtest_strategy(strategy_class, symbol, data, initial_capital=50000):
    """回测单个策略"""
    print(f"\n🔬 开始回测 {strategy_class.__name__} - {symbol}")
    print("=" * 60)

    strategy = strategy_class()
    strategy.capital = initial_capital
    strategy.positions = {}
    strategy.trades = []

    portfolio_values = [initial_capital]
    dates = []

    # 滑窗回测
    window_size = 100  # 使用100天的数据窗口

    for i in range(window_size, len(data)):
        current_data = data.iloc[i-window_size:i+1]
        current_date = data.index[i]

        # 跳过周末和非交易日检查
        if hasattr(current_date, 'weekday') and current_date.weekday() >= 5:
            continue

        # 生成信号
        signals = strategy.generate_signals(symbol, current_data, {})

        # 执行信号
        for signal in signals:
            if signal['action'] == 'BUY' and symbol not in strategy.positions:
                # 计算买入数量
                investment = min(strategy.capital * 0.1, 10000)  # 最多投入10%资本或10000
                shares = int(investment / signal['price'])

                if shares > 0:
                    strategy.positions[symbol] = {
                        'size': shares,
                        'avg_cost': signal['price'],
                        'entry_time': current_date
                    }
                    strategy.capital -= shares * signal['price']

                    strategy.trades.append({
                        'date': current_date,
                        'action': 'BUY',
                        'price': signal['price'],
                        'shares': shares,
                        'capital': strategy.capital
                    })

            elif signal['action'] == 'SELL' and symbol in strategy.positions:
                position = strategy.positions[symbol]
                sell_price = signal['price']
                sell_value = position['size'] * sell_price

                # 计算盈亏
                cost_basis = position['size'] * position['avg_cost']
                pnl = sell_value - cost_basis

                strategy.capital += sell_value

                strategy.trades.append({
                    'date': current_date,
                    'action': 'SELL',
                    'price': sell_price,
                    'shares': position['size'],
                    'pnl': pnl,
                    'capital': strategy.capital
                })

                del strategy.positions[symbol]

        # 计算当前投资组合价值
        portfolio_value = strategy.capital
        if symbol in strategy.positions:
            position = strategy.positions[symbol]
            current_price = data.iloc[i]['Close']
            portfolio_value += position['size'] * current_price

        portfolio_values.append(portfolio_value)
        dates.append(current_date)

    # 计算回测结果
    final_value = portfolio_values[-1]
    total_return = (final_value - initial_capital) / initial_capital * 100

    # 计算年化收益率
    days = (dates[-1] - dates[0]).days
    years = days / 365
    annualized_return = ((final_value / initial_capital) ** (1/years) - 1) * 100

    # 计算最大回撤
    peak = initial_capital
    max_drawdown = 0
    for value in portfolio_values:
        if value > peak:
            peak = value
        drawdown = (peak - value) / peak * 100
        max_drawdown = max(max_drawdown, drawdown)

    # 计算夏普比率（简化版）
    returns = pd.Series(portfolio_values).pct_change().dropna()
    if len(returns) > 0:
        sharpe_ratio = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
    else:
        sharpe_ratio = 0

    results = {
        'strategy': strategy_class.__name__,
        'symbol': symbol,
        'initial_capital': initial_capital,
        'final_value': final_value,
        'total_return_pct': total_return,
        'annualized_return_pct': annualized_return,
        'max_drawdown_pct': max_drawdown,
        'sharpe_ratio': sharpe_ratio,
        'total_trades': len(strategy.trades),
        'portfolio_values': portfolio_values,
        'dates': dates,
        'trades': strategy.trades
    }

    print(f"初始资本: ${initial_capital:,.0f}")
    print(f"最终价值: ${final_value:,.0f}")
    print(f"总收益率: {total_return:.2f}%")
    print(f"年化收益率: {annualized_return:.2f}%")
    print(f"最大回撤: {max_drawdown:.2f}%")
    print(f"夏普比率: {sharpe_ratio:.2f}")
    print(f"总交易次数: {len(strategy.trades)}")

    return results

def plot_results(results_list):
    """绘制回测结果对比图"""
    plt.figure(figsize=(15, 10))

    # 投资组合价值曲线
    plt.subplot(2, 2, 1)
    for result in results_list:
        plt.plot(result['dates'], result['portfolio_values'],
                label=f"{result['strategy']} ({result['total_return_pct']:.1f}%)", linewidth=2)

    plt.title('投资组合价值对比')
    plt.xlabel('日期')
    plt.ylabel('投资组合价值 ($)')
    plt.legend()
    plt.grid(True)

    # 收益分布
    plt.subplot(2, 2, 2)
    strategies = [r['strategy'] for r in results_list]
    returns = [r['total_return_pct'] for r in results_list]

    bars = plt.bar(strategies, returns, color=['blue', 'green', 'red', 'orange'])
    plt.title('总收益率对比')
    plt.ylabel('收益率 (%)')
    plt.xticks(rotation=45)

    # 为每个bar添加数值标签
    for bar, return_val in zip(bars, returns):
        plt.text(bar.get_x() + bar.get_width()/2, bar.get_y() + bar.get_height(),
                f'{return_val:.1f}%', ha='center', va='bottom')

    # 最大回撤对比
    plt.subplot(2, 2, 3)
    drawdowns = [r['max_drawdown_pct'] for r in results_list]
    bars = plt.bar(strategies, drawdowns, color=['lightblue', 'lightgreen', 'lightcoral', 'orange'])
    plt.title('最大回撤对比')
    plt.ylabel('最大回撤 (%)')
    plt.xticks(rotation=45)

    for bar, dd in zip(bars, drawdowns):
        plt.text(bar.get_x() + bar.get_width()/2, bar.get_y() + bar.get_height(),
                f'{dd:.1f}%', ha='center', va='bottom')

    # 夏普比率对比
    plt.subplot(2, 2, 4)
    sharpes = [r['sharpe_ratio'] for r in results_list]
    bars = plt.bar(strategies, sharpes, color=['skyblue', 'lightgreen', 'salmon', 'gold'])
    plt.title('夏普比率对比')
    plt.ylabel('夏普比率')
    plt.xticks(rotation=45)

    for bar, sr in zip(bars, sharpes):
        plt.text(bar.get_x() + bar.get_width()/2, bar.get_y() + bar.get_height(),
                f'{sr:.2f}', ha='center', va='bottom')

    plt.tight_layout()
    plt.savefig('Test/new_strategies_backtest_results.png', dpi=300, bbox_inches='tight')
    plt.show()

def main():
    """主函数"""
    print("🚀 新策略回测系统")
    print("=" * 60)

    # 创建测试数据
    symbol = 'AAPL'
    data = create_sample_data(symbol, days=300)
    print(f"✅ 创建测试数据完成 - {symbol}, {len(data)}天")

    # 定义要测试的策略
    strategies_to_test = [
        (A23AroonOscillatorStrategy, "A23 Aroon Oscillator"),
        (A24UltimateOscillatorStrategy, "A24 Ultimate Oscillator"),
    ]

    # 执行回测
    results = []
    for strategy_class, name in strategies_to_test:
        try:
            result = backtest_strategy(strategy_class, symbol, data)
            results.append(result)
        except Exception as e:
            print(f"❌ 回测 {name} 失败: {e}")
            import traceback
            traceback.print_exc()

    # 生成对比报告
    if results:
        print("\n📊 回测结果汇总")
        print("=" * 80)
        print("<12")
        print("-" * 80)

        for result in results:
            print("<12"
                  "<8.1f"
                  "<8.1f"
                  "<8.1f"
                  "<8.2f"
                  "<8")

        # 绘制对比图
        try:
            plot_results(results)
            print("✅ 回测结果图表已保存为: Test/new_strategies_backtest_results.png")
        except Exception as e:
            print(f"⚠️ 无法生成图表: {e}")

    print("\n🎉 回测完成！")

if __name__ == '__main__':
    main()