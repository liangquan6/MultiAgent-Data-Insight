"""单数据集分析入口。先跑通这一个, 再去 benchmark 批量。

用法:
  python main.py --data data/iris.csv --mode selector
  python main.py --data data/iris.csv --schema-mode verbose   # 对照基线
"""
import argparse
import asyncio
import glob
import os
import time
from teams.team_factory import build_team
from memory.schema_memory import SchemaMemory
from memory.conversation_memory import ConversationMemory

import pandas as pd


TASK_TEMPLATE = (
    "数据集路径: {path}\n"
    "Schema 摘要: {schema}\n"
    "任务: 请四位协作完成数据分析, 最终由 Reporter 产出 markdown 报告。\n"
    "Reviewer 认为可以收尾时回复 PASS。"
)


def _format_msg(content) -> str:
    """把 Agent 消息格式化成可读日志: 纯文本截断, 工具调用提取名字。

    content 可能是 str, 也可能是 list (FunctionCall / FunctionExecutionResult)。
    之前直接 str(content)[:200] 会把 FunctionCall 的 repr 截断, 看不出调了哪个工具。
    """
    if isinstance(content, str):
        return content[:200]
    parts = []
    for item in content:
        name = getattr(item, "name", None)
        if name:  # FunctionCall
            parts.append(f"<call {name}>")
            continue
        c = getattr(item, "content", None)
        if c:  # FunctionExecutionResult
            parts.append(f"<result {str(c)[:80]}>")
            continue
        parts.append(str(item)[:80])
    return " ".join(parts) if parts else str(content)[:200]


def _usage_of(msg) -> dict | None:
    """从 AutoGen 消息对象提取 token 用量, 返回 {prompt, completion} 或 None。

    AutoGen 把每次 LLM 推理的 token 挂在 message.models_usage 上 (RequestUsage)。
    只有 LLM 真正推理产生的消息才有; 工具执行结果/user 起始消息为 None。
    """
    u = getattr(msg, "models_usage", None)
    if u is None:
        return None
    return {"prompt": u.prompt_tokens, "completion": u.completion_tokens}


def _is_real_report(text: str) -> bool:
    """判断 Reporter 的发言是真报告还是"等图"占位。"""
    if not text:
        return False
    if "等 Coder" in text or "等图" in text:
        return False
    return "#" in text and len(text) > 100


async def _reporter_fallback(path: str, analyst_text: str, coder_text: str,
                             token_counter: dict) -> str:
    """团队没出报告时的确定性兜底: 直接调 model_client 写报告。

    不走 AssistantAgent.on_messages_stream (实测 qwen 在该路径偶尔返回空 content),
    改用最底层的 model_client.create(), 拿到 CreateResult.content 直接用。
    程序扫 results/plots 拿确定的图路径列表, 连同 Analyst 思路和
    Coder 工具摘要一起喂给模型, 让它写报告。

    token_counter: 传入可变 dict, 兜底调用的 token 也计入统计。
    """
    from config import get_model_client
    from autogen_core.models import SystemMessage, UserMessage
    from autogen_core import CancellationToken

    plots = sorted(glob.glob("results/plots/plot_*.png"))
    plots_rel = [p.replace("\\", "/") for p in plots]
    system = (
        "你是数据分析报告员。基于给定的分析思路、工具产出和图路径清单, "
        "写一份结构化 markdown 报告。每个发现引用真实图路径, 不准编造。"
    )
    user = (
        f"数据集: {path}\n"
        f"Analyst 分析思路:\n{analyst_text}\n\n"
        f"Coder 工具产出摘要:\n{coder_text}\n\n"
        f"系统已确认生成以下 {len(plots_rel)} 张图 (路径真实存在):\n"
        + "\n".join(f"- {p}" for p in plots_rel)
        + "\n\n请写一份 markdown 分析报告, 含数据概览、关键发现(附图路径)、结论。"
    )
    client = get_model_client()
    result = await client.create(
        [SystemMessage(content=system), UserMessage(source="user", content=user)],
        cancellation_token=CancellationToken(),
    )
    # 兜底调用的 token 也计入
    if result.usage:
        token_counter["prompt"] += result.usage.prompt_tokens
        token_counter["completion"] += result.usage.completion_tokens
    return result.content if isinstance(result.content, str) else str(result.content)


async def main(path: str, mode: str, schema_mode: str = "compact",
               schema_cap: int = 1500, transport: str = "direct") -> dict:
    """跑一次完整分析, 返回 token 统计 + 产物路径。

    Args:
        path: CSV 路径
        mode: round_robin / selector
        schema_mode: compact (SchemaMemory 压缩) / verbose (朴素 dump, 对照基线)
        schema_cap: 注入 task 的 schema 字符数上限。默认 1500 控成本;
            对照实验想看压缩全貌时调大 (如 20000), 让 verbose 的宽表 schema 完整进来。
        transport: direct (本地函数) / mcp (MCP stdio server), 只影响 Coder 工具来源。
    """
    df = pd.read_csv(path)
    if schema_mode == "verbose":
        schema = SchemaMemory.verbose_schema(df)
    else:
        schema = SchemaMemory(df).get()

    mem = ConversationMemory(store_path=f"results/{path.split('/')[-1]}.jsonl")

    # 续聊注入: 如果上次跑过同数据集, 把历史摘要拼到 task 前面
    continuation = mem.context_for_continuation()
    task = continuation + TASK_TEMPLATE.format(path=path, schema=schema[:schema_cap])

    print(f"[启动] mode={mode}, schema_mode={schema_mode}, transport={transport}, "
          f"模型在生成中, 多 Agent 协作通常需要 1-3 分钟...\n", flush=True)
    team = await build_team(mode, transport)

    # token 统计: 分 prompt/completion 累计 (压缩 schema 主要省 prompt token)
    token_counter = {"prompt": 0, "completion": 0}
    n_rounds = 0
    t0 = time.time()

    reporter_text = None
    analyst_text = ""
    coder_text = ""
    async for msg in team.run_stream(task=task):
        if hasattr(msg, "source") and hasattr(msg, "content"):
            n_rounds += 1
            snip = _format_msg(msg.content)
            print(f"\n[{msg.source}] {snip}", flush=True)

            # 采集 token: 只有 LLM 推理的消息带 models_usage
            usage = _usage_of(msg)
            if usage:
                token_counter["prompt"] += usage["prompt"]
                token_counter["completion"] += usage["completion"]

            if msg.source == "Reporter" and isinstance(msg.content, str):
                reporter_text = msg.content
            if msg.source == "Analyst" and isinstance(msg.content, str) and len(msg.content) > 50:
                analyst_text = msg.content
            if msg.source == "Coder" and isinstance(msg.content, str):
                coder_text = msg.content

            mem.add(msg.source, msg.content, usage=usage)
    mem.save()

    # 报告落盘: 优先用团队协作中 Reporter 写的真报告;
    # 若 Reporter 只说了"等图", 走兜底单独再调一次。
    if not _is_real_report(reporter_text):
        print("\n[兜底] 团队协作未产出报告, 单独调 Reporter 重写...", flush=True)
        reporter_text = await _reporter_fallback(path, analyst_text, coder_text, token_counter)

    report_path = f"results/{path.split('/')[-1].replace('.csv', '_report.md')}"
    with open(report_path, "w", encoding="utf-8") as f:
        body = (reporter_text or "(Reporter 未产出报告)").replace("TAG: TERMINATE", "").rstrip()
        f.write(body)

    elapsed = round(time.time() - t0, 1)
    n_plots = len(glob.glob("results/plots/plot_*.png"))
    total_tokens = token_counter["prompt"] + token_counter["completion"]

    stats = {
        "data": path,
        "mode": mode,
        "schema_mode": schema_mode,
        "transport": transport,
        "prompt_tokens": token_counter["prompt"],
        "completion_tokens": token_counter["completion"],
        "total_tokens": total_tokens,
        "rounds": n_rounds,
        "elapsed_sec": elapsed,
        "n_plots": n_plots,
        "report_path": report_path,
    }
    print(f"\n=== 完成, 报告已存到 {report_path} ===")
    print(f"    token: prompt={token_counter['prompt']} completion={token_counter['completion']} "
          f"total={total_tokens} | rounds={n_rounds} | {elapsed}s | {n_plots} plots")
    return stats


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True)
    p.add_argument("--mode", default="round_robin",
                   choices=["round_robin", "selector", "llm_selector"])
    p.add_argument("--schema-mode", default="compact", choices=["compact", "verbose"],
                   help="compact=SchemaMemory压缩 / verbose=朴素dump(对照基线)")
    p.add_argument("--transport", default="direct", choices=["direct", "mcp"],
                   help="direct=本地函数直连 / mcp=MCP stdio server (W3.2)")
    args = p.parse_args()
    asyncio.run(main(args.data, args.mode, args.schema_mode, transport=args.transport))
