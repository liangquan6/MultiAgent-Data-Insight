"""数据分析师 Agent: 理解数据 + 提分析思路。"""
from autogen_agentchat.agents import AssistantAgent
from config import get_model_client
from tools.data_tools import load_csv, profile_dataset


def build_analyst_agent() -> AssistantAgent:
    return AssistantAgent(
        name="Analyst",
        model_client=get_model_client(),
        tools=[load_csv, profile_dataset],
        reflect_on_tool_use=True,   # 调完工具让 LLM 自己总结成自然语言, 给后续 Agent 看
        system_message=(
            "你是数据分析师。收到数据集路径后:\n"
            "1) 调用 load_csv / profile_dataset 摸清数据画像;\n"
            "2) 在工具调用结果的基础上, 用 3-5 条**自然语言**提出分析思路,\n"
            "   每条思路指明用哪列、做什么分析、解决什么问题, 让 Coder 能照干;\n"
            "3) 不要花太多话描述 schema, 工具结果里已经有了, 直接说'分析思路';\n"
            "4) 如果 Coder 已经按你的思路画过图了, 不要再重复提同样的思路让 Coder 重画。\n"
            "   此时只回复一句 '思路已交付, 等 Reviewer/Reporter 收尾即可', 不要新增需求。"
        ),
    )