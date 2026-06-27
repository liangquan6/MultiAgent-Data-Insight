"""MCP Server: 把 Coder 的可视化/检测工具用标准协议暴露。

为什么单独一个 server 进程: MCP 的卖点是"工具与 Agent 解耦"——
本文件作为 stdio server 独立运行, 任何 MCP client (AutoGen / Claude Desktop /
其它语言的 client) 都能用同一套协议调用这些工具, 不用关心 Python 实现。

设计: 薄包装转发。不重写工具逻辑, 只用 FastMCP 的 @mcp.tool() 把现有函数
注册成 MCP tool (FastMCP 用函数签名 + docstring 生成 JSON Schema, 与 AutoGen
从 docstring 生成 schema 同理)。直连路径 (data_tools.py) 不动, 两条路并存。

返回值规整: MCP 协议底层要求 tool 返回 content blocks (如 TextContent),
FastMCP 会自动把函数返回的 str 包成单个 TextContent。AutoGen 的 McpToolAdapter
.run() 再取出 result.content (list[TextContent]) 返回给 Agent。实测 AutoGen 会
对 list 做 str() 拼成 "[TextContent(...)]", 破坏 Reviewer/Reporter 靠的
"[box_plot(...)] plot_xxx.png" 路径前缀。故 client 端取值时用 "".join(text)
把内容拼回纯字符串 (见 coder_agent.build_coder_agent 的 MCP 分支说明)。

启动 (client 端会替我们起子进程, 一般不手动跑):
  python -m tools.mcp_server
"""
import json
import os
import sys

# 子进程启动时 (python tools/mcp_server.py) 不会把项目根目录加进 sys.path,
# 导致 `from tools.xxx import` 失败、server 进程直接崩, client 看到的是
# "Connection closed"。这里把项目根 (本文件上两级) 显式塞进 sys.path 兜底。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pandas as pd
from mcp.server.fastmcp import FastMCP

from tools.code_sandbox import run_code
from tools.data_tools import (
    PLOT_DIR, _ensure_dir,
    plot_distribution as _plot_distribution,
    correlation_heatmap as _correlation_heatmap,
    scatter_plot as _scatter_plot,
    box_plot as _box_plot,
    groupby_aggregate as _groupby_aggregate,
    detect_outliers as _detect_outliers,
)

mcp = FastMCP("data-viz-tools")


@mcp.tool()
def plot_distribution(path: str, column: str, save_dir: str = "") -> str:
    """画某列分布直方图, 返回图片路径。

    save_dir 可省略, 默认存 results/plots/。
    """
    return _plot_distribution(path, column, save_dir)


@mcp.tool()
def correlation_heatmap(path: str, save_dir: str = "") -> str:
    """画数值列相关性热力图, 返回图片路径。"""
    return _correlation_heatmap(path, save_dir)


@mcp.tool()
def scatter_plot(path: str, x: str, y: str, hue: str = "", save_dir: str = "") -> str:
    """画散点图 (x vs y, 可按 hue 列着色), 返回图片路径。

    适合观察两个数值列是否随类别分开, 例如: scatter_plot(path, x='sepal_len', y='petal_len', hue='species')
    """
    return _scatter_plot(path, x, y, hue, save_dir)


@mcp.tool()
def box_plot(path: str, groupby: str, column: str, save_dir: str = "") -> str:
    """按 groupby 列分组, 画 column 列的箱线图, 返回图片路径。

    适合比较不同类别在某数值列上的分布差异,
    例如: box_plot(path, groupby='species', column='petal_len')
    """
    return _box_plot(path, groupby, column, save_dir)


@mcp.tool()
def groupby_aggregate(path: str, groupby: str, columns: list[str], agg_funcs: list[str]) -> str:
    """按 groupby 列分组, 对 columns 各列做 agg_funcs 指定的聚合, 返回 JSON 结果。

    agg_funcs 可选: mean / std / min / max / median / count
    示例: groupby_aggregate(path, groupby='species', columns=['petal_len','petal_wid'], agg_funcs=['mean','std'])
    """
    return _groupby_aggregate(path, groupby, columns, agg_funcs)


@mcp.tool()
def detect_outliers(path: str, column: str) -> str:
    """用 IQR 法检测某列异常值, 返回异常数量与示例。"""
    return _detect_outliers(path, column)


if __name__ == "__main__":
    # transport=stdio: client (AutoGen) 通过子进程的 stdin/stdout 与本 server 通信,
    # 不开端口, 不依赖网络。手动跑只在调试时用 (平时由 client 替我们起进程)。
    mcp.run(transport="stdio")
