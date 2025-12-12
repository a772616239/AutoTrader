#!/usr/bin/env python3
"""
测试A22超级趋势策略
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from strategies.a22_super_trend import A22SuperTrendStrategy

def create_test_data():
    """创建测试数据 - 实盘可行的突破场景"""
    dates = pd.date_range('2024-01-01', periods=60, freq='D')
    np.random.seed(42)

    # 创建实盘中可能出现的突破模式
    prices = []

    # 前40天：价格在95-105之间波动，模拟横盘整理
    for i in range(40):
        price = 100 + np.random.normal(0, 1.5)  # 横盘
        prices.append(price)

    # 后20天：价格突破上涨，模拟实盘突破
    for i in range(20):
        price = 105 + i * 0.5 + np.random.normal(0, 1)  # 稳步上涨
        prices.append(price)

    prices = np.array(prices)

    # 手动调整成交量，确保突破期间有成交量放大
    volumes = np.random.randint(300000, 500000, 60)  # 基础成交量

    # 在突破开始阶段（最后10天）增加成交量
    for i in range(50, 60):  # 最后10天
        if i < len(volumes):
            volumes[i] = np.random.randint(600000, 900000)  # 突破期间高成交量

    # 创建OHLC数据
    data = pd.DataFrame({
        'Open': prices * (1 + np.random.randn(60) * 0.002),
        'High': np.maximum(prices * (1 + np.random.uniform(0, 0.01, 60)),
                          prices * 1.005),
        'Low': np.minimum(prices * (1 - np.random.uniform(0, 0.01, 60)),
                         prices * 0.995),
        'Close': prices,
        'Volume': volumes
    }, index=dates)

    return data

def main():
    print("🧪 测试A22超级趋势策略")
    print("=" * 50)

    # 创建测试数据
    data = create_test_data()
    print("✅ 测试数据创建完成")
    print(f"   价格范围: ${data['Close'].min():.2f} - ${data['Close'].max():.2f}")
    print(f"   数据长度: {len(data)}")

    # 先检查超级趋势指标计算
    from strategies.indicators import calculate_super_trend
    super_trend, trend_direction = calculate_super_trend(data['High'], data['Low'], data['Close'])

    print("\n🔍 超级趋势指标分析:")
    print(f"   最后10个超级趋势值: {super_trend.tail(10).values}")
    print(f"   最后10个趋势方向: {trend_direction.tail(10).values}")
    print(f"   最后10个收盘价: {data['Close'].tail(10).values}")

    # 检查是否有趋势变化
    trend_changes = []
    for i in range(1, len(trend_direction)):
        if trend_direction.iloc[i] != trend_direction.iloc[i-1]:
            trend_changes.append((i, trend_direction.iloc[i-1], trend_direction.iloc[i]))

    print(f"   趋势变化点: {len(trend_changes)} 个")
    for change in trend_changes[-3:]:  # 显示最后3个变化
        idx, old_trend, new_trend = change
        print(f"     位置{idx}: {old_trend} -> {new_trend}")

    # 检查买入信号条件
    current_price = data['Close'].iloc[-1]
    prev_price = data['Close'].iloc[-2]
    current_st = super_trend.iloc[-1]
    prev_st = super_trend.iloc[-2]
    current_trend = trend_direction.iloc[-1]
    prev_trend = trend_direction.iloc[-2]

    print("\n🔍 买入信号条件检查:")
    print(f"   当前价格: {current_price:.2f}, 上一价格: {prev_price:.2f}")
    print(f"   当前ST: {current_st:.2f}, 上一ST: {prev_st:.2f}")
    print(f"   当前趋势: {current_trend}, 上一趋势: {prev_trend}")

    condition1 = prev_price < prev_st
    condition2 = current_price >= current_st
    condition3 = prev_trend == -1
    condition4 = current_trend == 1

    print(f"   条件1 (prev_price < prev_st): {condition1}")
    print(f"   条件2 (current_price >= current_st): {condition2}")
    print(f"   条件3 (prev_trend == -1): {condition3}")
    print(f"   条件4 (current_trend == 1): {condition4}")
    print(f"   整体买入信号: {condition1 and condition2 and condition3 and condition4}")

    # 创建一个明确的突破场景进行测试
    print("\n🔬 创建明确的突破测试场景:")

    # 手动构造一个突破场景 - 使用更多数据点确保ATR计算准确
    test_prices = []
    # 前30天：缓慢下跌
    for i in range(30):
        price = 120 - i * 0.5 + np.random.normal(0, 1)
        test_prices.append(price)

    # 后30天：突破上涨
    for i in range(30):
        price = 105 + i * 1.2 + np.random.normal(0, 1.5)
        test_prices.append(price)

    test_dates = pd.date_range('2024-01-01', periods=60, freq='D')
    test_data = pd.DataFrame({
        'Open': np.array(test_prices) * (1 + np.random.randn(60) * 0.005),
        'High': np.maximum(np.array(test_prices) * (1 + np.random.uniform(0, 0.02, 60)),
                          np.array(test_prices) * 1.005),
        'Low': np.minimum(np.array(test_prices) * (1 - np.random.uniform(0, 0.02, 60)),
                         np.array(test_prices) * 0.995),
        'Close': test_prices,
        'Volume': np.random.randint(300000, 800000, 60)
    }, index=test_dates)

    print(f"   测试数据价格: {test_prices}")
    print(f"   前10天: 下跌趋势")
    print(f"   后10天: 突破上涨")

    # 计算超级趋势
    test_st, test_trend = calculate_super_trend(test_data['High'], test_data['Low'], test_data['Close'])
    print(f"   超级趋势: {test_st.values}")
    print(f"   趋势方向: {test_trend.values}")

    # 找到突破点并测试
    breakthrough_points = []
    for i in range(1, len(test_trend)):
        if test_trend.iloc[i] == 1 and test_trend.iloc[i-1] == -1:
            breakthrough_points.append(i)

    print(f"   突破点: {breakthrough_points}")

    # 测试策略信号生成
    strategy = A22SuperTrendStrategy()

    # 测试完整的突破场景 - 提供足够的历史数据
    print("\n🔬 测试完整突破场景:")
    print(f"   数据总长度: {len(test_data)} (足够计算ATR)")

    # 手动查找突破点并检查所有条件
    print("\n🔍 手动查找突破点:")
    breakthrough_found = False
    for i in range(1, len(test_st)):
        if pd.notna(test_st.iloc[i]) and pd.notna(test_st.iloc[i-1]):
            prev_price = test_data['Close'].iloc[i-1]
            current_price = test_data['Close'].iloc[i]
            prev_st = test_st.iloc[i-1]
            current_st = test_st.iloc[i]

            if prev_price <= prev_st and current_price > current_st:
                print(f"   ✅ 找到突破点! 位置{i}:")
                print(f"      上一价格: {prev_price:.2f} <= 上一ST: {prev_st:.2f}")
                print(f"      当前价格: {current_price:.2f} > 当前ST: {current_st:.2f}")

                # 检查其他条件
                # 成交量确认
                avg_volume = test_data['Volume'].rolling(10).mean().iloc[i]
                current_volume = test_data['Volume'].iloc[i]
                volume_check = current_volume >= avg_volume * 1.2
                print(f"      成交量检查: {current_volume:.0f} >= {avg_volume:.0f} * 1.2 = {volume_check}")

                # 价格过滤
                min_price_check = current_price >= 5.0
                max_price_check = True  # 没有max_price限制
                print(f"      价格过滤: {min_price_check} and {max_price_check} = {min_price_check and max_price_check}")

                # 趋势强度
                trend_strength = abs(current_st - prev_st) / current_price
                min_trend_strength = 0.001
                strength_check = trend_strength >= min_trend_strength
                print(f"      趋势强度: {trend_strength:.4f} >= {min_trend_strength} = {strength_check}")

                # 整体结果
                all_conditions = volume_check and min_price_check and max_price_check and strength_check
                print(f"      所有条件满足: {all_conditions}")

                breakthrough_found = True
                break

    if not breakthrough_found:
        print("   ❌ 未找到任何突破点")

    # 在突破点检查信号 - 使用完整数据但模拟实时检测
    breakthrough_idx = 35  # 从手动查找中找到的位置

    print(f"\n🔍 在突破点位置{breakthrough_idx}检查信号:")
    try:
        # 使用完整数据进行检测（策略会自动检查最后一个数据点）
        # 但我们需要确保突破点是最后一个数据点
        breakthrough_data = test_data.iloc[:breakthrough_idx + 1]  # 包含突破点

        buy_signal = strategy.detect_buy_signal('TEST', breakthrough_data, {})
        if buy_signal:
            print("   ✅ 检测到买入信号!")
            print(f"   价格: ${buy_signal['price']:.2f}, 置信度: {buy_signal['confidence']:.2f}")
            print(f"   原因: {buy_signal.get('reason', 'N/A')}")
        else:
            print("   ❌ 未检测到买入信号")

            # 检查突破点的条件
            current_price = breakthrough_data['Close'].iloc[-1]
            prev_price = breakthrough_data['Close'].iloc[-2]
            # 重新计算超级趋势以确保一致性
            from strategies.indicators import calculate_super_trend
            st_calc, trend_calc = calculate_super_trend(
                breakthrough_data['High'], breakthrough_data['Low'], breakthrough_data['Close']
            )
            current_st_val = st_calc.iloc[-1] if pd.notna(st_calc.iloc[-1]) else float('nan')
            prev_st_val = st_calc.iloc[-2] if pd.notna(st_calc.iloc[-2]) else float('nan')

            print(f"   突破点检查:")
            print(f"   当前价格: {current_price:.2f}, 上一价格: {prev_price:.2f}")
            print(f"   当前ST: {current_st_val:.2f}, 上一ST: {prev_st_val:.2f}")
            if not (pd.isna(prev_st_val) or pd.isna(current_st_val)):
                result = (prev_price <= prev_st_val and current_price > current_st_val)
                print(f"   买入条件: prev_price <= prev_st and current_price > current_st")
                print(f"   结果: {prev_price <= prev_st_val} and {current_price > current_st_val} = {result}")

                # 检查成交量
                if len(breakthrough_data) >= 11:
                    avg_volume = breakthrough_data['Volume'].rolling(10).mean().iloc[-1]
                    current_volume = breakthrough_data['Volume'].iloc[-1]
                    volume_ok = current_volume >= avg_volume * 1.2
                    print(f"   成交量条件: {current_volume:.0f} >= {avg_volume:.0f} * 1.2 = {volume_ok}")

    except Exception as e:
        print(f"   ❌ 买入信号检测出错: {e}")
        import traceback
        traceback.print_exc()

    # 关键测试：在突破点进行实盘模拟
    breakthrough_idx = 38  # 从手动查找中找到的位置
    if breakthrough_idx < len(test_data):
        # 模拟实盘：策略在突破发生时接收数据
        real_time_data = test_data.iloc[:breakthrough_idx + 1]

        print(f"\n🎯 实盘信号测试 - 在突破点{breakthrough_idx}接收数据:")
        try:
            buy_signal = strategy.detect_buy_signal('TEST', real_time_data, {})
            if buy_signal:
                print("   ✅ 实盘买入信号!")
                print(f"   价格: ${buy_signal['price']:.2f}, 置信度: {buy_signal['confidence']:.2f}")
                print(f"   原因: {buy_signal.get('reason', 'N/A')}")
                print("   🎉 测试成功：策略能在实盘中产生交易信号！")
            else:
                print("   ❌ 实盘未检测到买入信号")

                # 检查为什么没有信号
                current_price = real_time_data['Close'].iloc[-1]
                prev_price = real_time_data['Close'].iloc[-2]
                from strategies.indicators import calculate_super_trend
                st, trend = calculate_super_trend(real_time_data['High'], real_time_data['Low'], real_time_data['Close'])
                current_st = st.iloc[-1]
                prev_st = st.iloc[-2]

                print(f"   调试信息:")
                print(f"   当前价格: {current_price:.2f}, 上一价格: {prev_price:.2f}")
                print(f"   当前ST: {current_st:.2f}, 上一ST: {prev_st:.2f}")
                print(f"   价格突破条件: {prev_price <= prev_st} and {current_price > current_st}")

        except Exception as e:
            print(f"   ❌ 实盘信号检测出错: {e}")
            import traceback
            traceback.print_exc()

    # 使用完整的测试数据进行信号检测
    try:
        buy_signal = strategy.detect_buy_signal('TEST', test_data, {})
        if buy_signal:
            print("   ✅ 完整数据检测到买入信号")
            print(f"   价格: ${buy_signal['price']:.2f}, 置信度: {buy_signal['confidence']:.2f}")
            print(f"   原因: {buy_signal.get('reason', 'N/A')}")
        else:
            print("   ❌ 完整数据未检测到买入信号（正常，因为突破已过）")

    except Exception as e:
        print(f"   ❌ 完整数据买入信号检测出错: {e}")
        import traceback
        traceback.print_exc()

    # 同时测试卖出信号
    try:
        sell_signal = strategy.detect_sell_signal('TEST', test_data, {})
        if sell_signal:
            print("   ✅ 检测到卖出信号")
            print(f"   价格: ${sell_signal['price']:.2f}, 置信度: {sell_signal['confidence']:.2f}")
        else:
            print("   ❌ 未检测到卖出信号")
    except Exception as e:
        print(f"   ❌ 卖出信号检测出错: {e}")

    signals = strategy.generate_signals('TEST', test_data, {})

    print(f"\n🎯 生成的信号数量: {len(signals)}")
    for i, signal in enumerate(signals, 1):
        print(f"{i}. {signal['action']}信号 - 价格:${signal['price']:.2f}, 置信度:{signal['confidence']:.2f}")
        if 'reason' in signal:
            print(f"   原因: {signal['reason']}")
        print()

    if signals:
        print("✅ A22超级趋势策略信号生成测试通过！")
    else:
        print("⚠️  A22策略未生成信号，可能需要调整测试数据或参数")
        print("💡 建议: 检查趋势变化是否足够明显，或调整策略参数")

if __name__ == '__main__':
    main()