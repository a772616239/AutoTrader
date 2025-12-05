import requests
import json

# 获取增强数据
response = requests.get("http://localhost:8001/enhanced-data?symbol=TSLA&period=3mo")
data = response.json()

# 格式化为LLM友好格式
from llm_optimized_data import LLMDataFormatter
llm_data = LLMDataFormatter.format_for_llm(data, style="analytical")

# 构建给大模型的提示
prompt = f"""
请分析以下股票数据并提供投资建议：

{json.dumps(llm_data, indent=2, ensure_ascii=False)}

请从趋势、风险、机会三个维度进行分析，并给出具体建议。
"""

# 将prompt发送给大模型（如DeepSeek、ChatGPT等）
print(prompt)