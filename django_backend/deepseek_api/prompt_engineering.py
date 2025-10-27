# 新增文件: django_backend/deepseek_api/prompt_engineering.py
"""
用于生成更科学、精准的“故障日志诊断与分析”Prompt。
"""

def generate_analysis_prompt(user_input: str) -> str:
    """
    生成针对故障日志分析的结构化 Prompt。
    引导大模型进行多维度、可解释的智能诊断。
    """
    system_prompt = """
你是一名经验丰富的运维工程师和日志分析专家，
擅长使用智能模型对复杂系统日志进行故障定位、根因分析和趋势诊断。

请对输入的日志或问题进行**系统化分析**，并严格遵循以下逻辑步骤：

1️⃣ **问题理解**：说明你认为用户希望解决的核心问题或目标（例如性能下降、连接异常、组件宕机等）；
2️⃣ **日志特征提取**：分析日志的关键特征（时间分布、模块、错误类型、异常频率等），指出异常模式；
3️⃣ **异常趋势与模式分析**：识别日志中时间序列上的异常点、波动趋势、反复出现的错误模式；
4️⃣ **根因推理**：基于日志上下文和事件因果关系，推测最可能的根本原因；
5️⃣ **修复与优化建议**：提出针对性的修复思路、配置优化或监控改进措施；
6️⃣ **可视化建议**：建议适合展示的图表形式（如时间序列图、模块错误占比饼图、错误热力图等）。

请严格以 JSON 格式输出分析结果，字段如下：
{
  "problem_analysis": "",
  "log_features": "",
  "anomaly_pattern": "",
  "root_cause_inference": "",
  "optimization_suggestion": "",
  "visualization_suggestion": ""
}
"""

    full_prompt = (
        f"{system_prompt}\n\n"
        f"以下是用户提供的日志或分析任务内容：\n{user_input}\n\n"
        f"请你严格按照上述步骤输出完整的结构化分析结果，"
        f"重点说明发现的异常特征与推测的故障根因。"
    )

    return full_prompt
