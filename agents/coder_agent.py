"""编码员 Agent: 按分析思路写 pandas/matplotlib 代码并执行。

W3.2: 支持 transport 参数切换工具传输层。
  - "direct": 工具是本地 Python 函数, Agent 直接调用 (W2/W3.1 的路径, 默认)
  - "mcp":    工具经 MCP stdio server 暴露, Agent 通过 MCP 协议远程调用
两条路对 LLM 透明 (工具名/签名/描述一致), 简历上可对比"工具传输层 direct vs MCP"。
"""
import os
import sys

from autogen_agentchat.agents import AssistantAgent
from autogen_core import CancellationToken
from autogen_ext.tools.mcp import StdioMcpToolAdapter, StdioServerParams, mcp_server_tools

from config import get_model_client
from tools.data_tools import (
    plot_distribution,
    correlation_heatmap,
    scatter_plot,
    box_plot,
    groupby_aggregate,
    detect_outliers,
)

# MCP server 脚本绝对路径 (client 起子进程用); 用绝对路径避开 Windows 相对路径坑
_MCP_SERVER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "tools", "mcp_server.py")

_SYSTEM_MESSAGE = (
    "你是数据编码员。按 Analyst 给的每条思路产出可视化或检测结果。\n\n"
    "工作准则:\n"
    "1) 一条思路至少调一个工具; 可用工具:\n"
    "   - plot_distribution(path, column): 画单列分布直方图\n"
    "   - correlation_heatmap(path): 画数值列相关性热力图\n"
    "   - scatter_plot(path, x, y, hue): 画两列散点图, 可按 hue 列着色\n"
    "   - box_plot(path, groupby, column): 按类别分组画某数值列箱线图\n"
    "   - groupby_aggregate(path, groupby, columns, agg_funcs): 分组聚合\n"
    "   - detect_outliers(path, column): IQR 法检测异常值\n"
    "2) Analyst 提了 N 条思路, 你就调 N 个工具, 不要只调一两个就交差;\n"
    "3) 不准编造分析结果, 没调过的工具不要说调过;\n"
    "4) Analyst 说的工具如果不在上面列表里, 先用最接近的替代工具尝试;\n"
    "   但如果某条思路**需要现有工具不具备的能力**(如创建派生列 petal_ratio=a/b、\n"
    "   跑自定义公式、对不存在的列做聚合), 不要反复试会报错的工具,\n"
    "   直接明确回复 '该子任务现有工具不可达: <原因>', 让 Reviewer 判定跳过。\n"
    "   反复试报错的工具只会耗光消息预算, 导致整轮兜底——诚实报告边界比硬试更有价值。"
)


class _FlatMcpTool(StdioMcpToolAdapter):
    """把 MCP 工具返回的 list[TextContent] 拍平成纯字符串。

    StdioMcpToolAdapter.run() 返回 result.content (list[TextContent]), AutoGen
    下游会对它 str() 成 "[TextContent(type='text', text='...', ...)]", 破坏
    Reviewer/Reporter 靠的 "[box_plot(...)] plot_xxx.png" 路径前缀。这里重写 run,
    把每个 TextContent 的 .text 拼回纯字符串, 让 MCP 路径与直连路径返回格式一致。
    """

    async def run(self, args, cancellation_token: CancellationToken):  # type: ignore[override]
        result = await super().run(args, cancellation_token)
        if isinstance(result, list):
            return "".join(getattr(item, "text", str(item)) for item in result)
        return result


async def _build_mcp_tools() -> list[_FlatMcpTool]:
    """起 MCP server 子进程, 拉取 6 个工具, 用 _FlatMcpTool 包一层拍平返回值。

    command 用 sys.executable (= agent_proj 的 python.exe), 保证子进程用同一环境,
    装的 mcp / pandas 都在。server 脚本内部已处理 sys.path, 不用额外设 env。
    """
    params = StdioServerParams(command=sys.executable, args=["-u", _MCP_SERVER])
    adapters = await mcp_server_tools(params)
    # mcp_server_tools 返回的是 StdioMcpToolAdapter 实例; 换成 _FlatMcpTool 同款配置。
    # 直接复用其 _server_params + _tool (MCP Tool 元数据) 重新构造, 复用 schema 解析。
    flat = []
    for a in adapters:
        flat.append(_FlatMcpTool(server_params=a._server_params, tool=a._tool))
    return flat


async def build_coder_agent(transport: str = "direct") -> AssistantAgent:
    """构造 Coder。

    Args:
        transport: "direct" 本地函数直连 / "mcp" 走 MCP stdio server。
                   两者工具签名一致, system_message 不用变。
    """
    if transport == "mcp":
        tools = await _build_mcp_tools()
    else:
        tools = [
            plot_distribution,
            correlation_heatmap,
            scatter_plot,
            box_plot,
            groupby_aggregate,
            detect_outliers,
        ]

    return AssistantAgent(
        name="Coder",
        model_client=get_model_client(),
        tools=tools,
        # reflect_on_tool_use 实测: qwen 在 AutoGen 的 reflection 步 (tool 结果后直接生成)
        # 会返回空 content, 导致下游收到空消息. 经测试直接调模型正常, 是 AutoGen 消息
        # 序列化与 qwen 的兼容问题. 故关掉 reflect, 改用 tool_call_summary_format +
        # 工具返回自带的 [tool_name(params)] 前缀, 让下游能数清几张图。
        reflect_on_tool_use=False,
        # tool_call_summary_format: reflect=False 时, 工具结果按此格式拼成摘要喂给下游。
        # 把工具名+结果原样保留, 确保 Reporter 能看到 plot_*.png 路径 (关键判断依据)。
        tool_call_summary_format="[{tool_name}] {result}",
        system_message=_SYSTEM_MESSAGE,
    )
