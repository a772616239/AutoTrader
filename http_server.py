#!/usr/bin/env python3
"""
独立的HTTP服务器，提供股票数据API - 修正版
运行: python http_server.py
"""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import yfinance as yf
from urllib.parse import urlparse, parse_qs

class StockAPIHandler(BaseHTTPRequestHandler):
    def _safe_float(self, value, default=0.0):
        """安全转换为float"""
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def _safe_int(self, value, default=0):
        """安全转换为int"""
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    
    def do_GET(self):
        """处理GET请求"""
        parsed = urlparse(self.path)
        
        if parsed.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<h1>Stock Data API Server</h1><p>Use /stock?symbol=AAPL</p>')
            return
            
        elif parsed.path == '/stock':
            # 获取查询参数
            params = parse_qs(parsed.query)
            symbol = params.get('symbol', ['AAPL'])[0]
            period = params.get('period', ['1mo'])[0]
            
            try:
                # 获取股票数据
                stock = yf.download(
                    symbol, 
                    period=period, 
                    progress=False, 
                    auto_adjust=True
                )
                
                if stock.empty:
                    response = {'error': f'No data found for {symbol}'}
                else:
                    # 准备数据 - 确保所有值为Python原生类型
                    data = []
                    for idx, row in stock.iterrows():
                        # 处理日期
                        if hasattr(idx, 'strftime'):
                            date_str = idx.strftime('%Y-%m-%d')
                        else:
                            date_str = str(idx)
                        
                        # 获取价格数据（确保是原生Python类型）
                        open_val = self._safe_float(row.get('Open', 0))
                        high_val = self._safe_float(row.get('High', 0))
                        low_val = self._safe_float(row.get('Low', 0))
                        close_val = self._safe_float(row.get('Close', 0))
                        
                        # 处理交易量
                        volume_val = self._safe_int(row.get('Volume', 0))
                        
                        data.append({
                            'date': date_str,
                            'open': round(open_val, 2),
                            'high': round(high_val, 2),
                            'low': round(low_val, 2),
                            'close': round(close_val, 2),
                            'volume': volume_val
                        })
                    
                    # 获取最新价格
                    latest_price = self._safe_float(
                        stock['Close'].iloc[-1] if not stock.empty else 0
                    )
                    
                    response = {
                        'symbol': symbol,
                        'period': period,
                        'data_points': len(data),
                        'latest_price': round(latest_price, 2),
                        'data': data
                    }
                    
            except Exception as e:
                response = {'error': str(e)}
            
            # 返回JSON响应
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            # 使用ensure_ascii=False支持中文，但不使用indent以减少数据量
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode())
            return
    
    def log_message(self, format, *args):
        """简化日志输出"""
        print(f"[HTTP] {args[0]} {args[1]} {args[2]}")

def run_http_server(port=8000):
    """启动HTTP服务器"""
    server_address = ('', port)
    httpd = HTTPServer(server_address, StockAPIHandler)
    print(f'✅ HTTP服务器启动成功，监听端口 {port}')
    print(f'🔗 测试链接: http://localhost:{port}/stock?symbol=AAPL')
    print(f'📡 等待请求... (按 Ctrl+C 停止)')
    httpd.serve_forever()

if __name__ == '__main__':
    run_http_server(port=8000)