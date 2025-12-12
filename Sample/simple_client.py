#!/usr/bin/env python3
"""
测试HTTP服务器
运行: python simple_client.py
"""
import requests
import json

def test_http_server():
    server_url = "http://localhost:8000"
    
    print("测试HTTP股票数据服务器...")
    print("=" * 50)
    
    # 测试1: 获取AAPL数据
    print("测试1: 获取苹果公司(AAPL)数据")
    try:
        response = requests.get(f"{server_url}/stock?symbol=AAPL&period=5d", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if 'error' not in data:
                # print(f"✅ 成功获取 {data['symbol']} 数据")
                print(f"   数据点: {data['data_points']} 条")
                print(f"   最新价格: ${data['latest_price']}")
                
                # 显示最近3条数据
                print("   最近3天数据:")
                for i, day in enumerate(data['data'][-3:], 1):
                    print(f"     {day['date']}: 开${day['open']:.2f}, 收${day['close']:.2f}")
            else:
                print(f"❌ 错误: {data['error']}")
        else:
            print(f"❌ HTTP错误: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务器，请确保 http_server.py 正在运行")
        return False
    
    # 测试2: 获取MSFT数据
    print("\n测试2: 获取微软公司(MSFT)数据")
    try:
        response = requests.get(f"{server_url}/stock?symbol=MSFT&period=1mo", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if 'error' not in data:
                # print(f"✅ 成功获取 {data['symbol']} 数据")
                print(f"   数据点: {data['data_points']} 条")
                print(f"   最新价格: ${data['latest_price']}")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
    
    print("\n" + "=" * 50)
    print("测试完成!")
    return True

if __name__ == "__main__":
    print("HTTP客户端测试程序")
    print("注意: 请先运行 http_server.py")
    print("-" * 40)
    test_http_server()