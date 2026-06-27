"""team_factory: 3 种协作模式可切换, W4 评测对比用。"""
import re
from autogen_agentchat.teams import RoundRobinGroupChat, SelectorGroupChat
from autogen_agentchat.conditions import (
    TextMentionTermination, MaxMessageTermination,
)
from agents.analyst_agent import build_analyst_agent
from agents.coder_agent import build_coder_agent
from agents.reviewer_agent import build_reviewer_agent
from agents.reporter_agent import build_reporter_agent
from config import get_model_client


async def _agents(transport: str = "direct"):
    """构造 4 个 Agent。Coder 按 transport 走直连 / MCP, 其余不变。"""
    return [build_analyst_agent(),
            await build_coder_agent(transport),
            build_reviewer_agent(), build_reporter_agent()]


def _term(max_rounds: int = 30):
    """终止条件: 二者满足其一即收工 (AutoGen 对 termination_condition 走 OR)。

    1. Reporter 末尾追加 "TERMINATE": 报告真交付后再停, 不让其它 Agent 编后续
    2. MaxMessage 上限兜底: 防 Reviewer/Coder 反复返工或 Agent 互相庆祝死循环

    注意: Reviewer 的 "PASS_FINAL" 只是放行信号, 不触发终止——
    否则 Reporter 还没写报告就被 Reviewer 提前掐断。
    MaxMessage 计入 user 起始消息, 4 Agent 走完一轮已有 5 条,
    要让流程能跑 3-4 轮 (Analyst→Coder→Reviewer→Reporter 写报告), 至少 30。

    llm_selector 模式 (模型自调度) 预期更绕、易循环, 调用方传 40 给点空间;
    但别太大, 否则循环时白烧 token。确定性 selector 维持 30。
    """
    return (
        TextMentionTermination("TERMINATE")
        | MaxMessageTermination(max_rounds)
    )


# 确定性调度状态机: 按 Analyst→Coder→Reviewer→Reporter 顺序走,
# 不把"选谁发言"交给 LLM (实测 qwen 当 selector 会陷入 Analyst/Coder 互相庆祝)。
# 依据对话历史里出现过哪些角色的发言来推进, 保证 Reporter 一定会被选中。
def _selector_func(messages) -> str | None:
    """根据对话历史返回下一个发言者名字。

    状态机:
      初始          -> Analyst
      Analyst 发过  -> Coder
      Coder 发过    -> Reviewer
      Reviewer 发过 -> Reporter
      Reporter 说"等图" -> Coder (回去补图)
      Reporter 写了报告(TERMINATE) -> None (交给终止条件收尾)
    """
    # 按发言者统计已发言次数
    spoken = {}
    last_speaker = None
    for m in messages:
        src = getattr(m, "source", None)
        if src and src != "user":
            spoken[src] = spoken.get(src, 0) + 1
            last_speaker = src

    # 第一轮: user 之后必是 Analyst
    if not spoken:
        return "Analyst"

    # 顺序推进: Analyst->Coder->Reviewer->Reporter
    order = ["Analyst", "Coder", "Reviewer", "Reporter"]
    if last_speaker in order:
        idx = order.index(last_speaker)
        # Reporter 之后回到 Analyst 开新一轮 (兜底; 正常会被 TERMINATE 截停)
        if idx < len(order) - 1:
            return order[idx + 1]

    # 默认: 让 Analyst 开新一轮
    return "Analyst"


async def build_team(mode: str = "round_robin", transport: str = "direct"):
    """mode: round_robin / selector / llm_selector
    transport: direct (本地函数) / mcp (MCP stdio server), 只影响 Coder 的工具来源。

    三种协作模式 (W4 对比用):
      - round_robin:   固定顺序轮流发言, 最简单
      - selector:      确定性 selector_func 状态机 (Analyst→Coder→Reviewer→Reporter)
      - llm_selector:  模型自己选谁发言 (不传 selector_func, 回退 model_client)
                       这是 W2 用状态机替代的失败方案, W4 量化它: 预期循环/低完成率,
                       用数据证明确定性调度的必要性。
    """
    # llm_selector 预期更绕, 多给 10 条消息空间; 其余模式维持 30
    term = _term(40 if mode == "llm_selector" else 30)
    agents = await _agents(transport)
    if mode == "round_robin":
        return RoundRobinGroupChat(agents, termination_condition=term)
    if mode == "selector":
        # selector_func 用确定性状态机, 不走 LLM 调度——
        # 否则 qwen 当 selector 会陷入 Analyst/Coder 互相庆祝/归档死循环,
        # Reporter 永远轮不上。
        return SelectorGroupChat(
            agents,
            model_client=get_model_client(),
            selector_func=_selector_func,
            allow_repeated_speaker=True,
            termination_condition=term,
        )
    if mode == "llm_selector":
        # 不传 selector_func → SelectorGroupChat 回退用 model_client 选发言人。
        # allow_repeated_speaker=True: 允许同一 Agent 连续发言 (模型可能反复叫 Coder)。
        # 这是对照组: 看 LLM 自调度能否收敛, 还是陷入循环。
        return SelectorGroupChat(
            agents,
            model_client=get_model_client(),
            allow_repeated_speaker=True,
            termination_condition=term,
        )
    raise ValueError(f"unknown mode: {mode}。可选: round_robin / selector / llm_selector。")