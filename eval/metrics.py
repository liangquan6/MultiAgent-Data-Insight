"""Agent 行为评测指标。

与你简历里的 RAGAS/Hit@K/MRR 不同: 那些评检索生成, 这里评 Agent 协作过程。
W4 靠这一组指标产出协作模式对比表。
"""
import json
import re
from collections import Counter


def completion_rate(results: list[dict]) -> float:
    """任务完成率: 报告是否含'关键发现'且 PASS 出现。"""
    if not results:
        return 0.0
    ok = sum(1 for r in results if r.get("completed"))
    return round(ok / len(results), 3)


def first_pass_rate(runs: list[list[dict]]) -> float:
    """代码一次通过率: 一轮里 Coder 没有 Reviewer 返工的比例。"""
    if not runs:
        return 0.0
    passed = 0
    for run in runs:
        need_rework = any("返工" in m.get("content", "") for m in run if m.get("source") == "Reviewer")
        if not need_rework:
            passed += 1
    return round(passed / len(runs), 3)


def loop_detection(messages: list[dict]) -> bool:
    """循环检测: 同一 Agent 连续 3 次说高度相似的话, 判为死循环。"""
    contents = [m.get("content", "") for m in messages]
    for i in range(len(contents) - 2):
        if len({contents[i][:40], contents[i+1][:40], contents[i+2][:40]}) == 1:
            return True
    return False


def token_efficiency(messages: list[dict], total_tokens: int) -> float:
    """token 效率: 完成任务需要的平均 round 数 / 每轮 token。"""
    rounds = len(messages)
    return round(total_tokens / max(rounds, 1), 1)


def tool_misuse_rate(tool_calls: list[dict]) -> float:
    """工具误用率: 报错 / 参数错的工具调用占比。"""
    if not tool_calls:
        return 0.0
    bad = sum(1 for c in tool_calls if c.get("error"))
    return round(bad / len(tool_calls), 3)


def summary(metrics: dict) -> str:
    return json.dumps(metrics, ensure_ascii=False, indent=2)


# 工具调用结果里常见的报错关键词; 命中即判为一次误用。
_ERROR_MARKERS = ("Error", "TypeError", "ValueError", "KeyError",
                  "no numeric data", "不存在", "错误:")


def extract_tool_calls(messages: list[dict]) -> list[dict]:
    """从消息序列里提取工具调用记录, 供 tool_misuse_rate 用。

    Coder 的工具结果摘要 (reflect=False + tool_call_summary_format) 形如:
      "[box_plot] [box_plot(groupby=species, column=petal_len)] results\\plots\\plot_xxx.png"
    或出错时:
      "[box_plot] Error: 2 validation errors for box_plotArguments ..."

    tool_call_summary_format 会在每个工具结果前加 [tool_name], 故按这个前缀正则切分。
    注意工具自身返回值也含 [tool_name(params)] 形态的路径前缀, 那是函数返回值不是
    summary 头, 会一起被切到——但它们也代表一次"调用产出", 计入调用数无妨;
    误用判定看整段有没有报错关键词, 不影响。

    返回 [{"name": str, "error": bool}, ...]。
    """
    # 匹配 [单词] 形态的工具头, 如 [box_plot] [scatter_plot]
    head_re = re.compile(r"\[([a-zA-Z_]\w*)\]")
    calls = []
    for m in messages:
        if m.get("source") != "Coder":
            continue
        content = m.get("content", "")
        if not isinstance(content, str):
            continue
        # 找所有工具头位置, 每段 = 从一个头到下一个头之前
        heads = list(head_re.finditer(content))
        for i, mt in enumerate(heads):
            name = mt.group(1)
            seg = content[mt.end():heads[i + 1].start()] if i + 1 < len(heads) else content[mt.end():]
            calls.append({
                "name": name,
                "error": any(marker in seg for marker in _ERROR_MARKERS),
            })
    return calls