# MultiAgent-Data-Insight

基于 Microsoft AutoGen 二开的数据分析多 Agent 系统。上传一个 CSV，4 个 Agent 自动协作产出"分析报告 + 可视化"。

> **演示场景**: 一个不懂 pandas 的房产中介店长, 把爬来的长沙二手房挂牌表丢进去,
> 直接拿到"哪个区域是价格洼地、哪些房源被低估、带看热度怎么看"的报告, 不用养数据分析师。
> 业务故事详见 [docs/BUSINESS_STORY.md](docs/BUSINESS_STORY.md)。

本项目用于 Agent 实习方向的能力补强与简历背书。

## 能力目标(对应简历能力项)

| 简历能力项 | 本项目落地点 |
|---|---|
| 工具编排 | 跨 Agent 工具调度 + 动态工具选择 |
| 记忆管理 | `SchemaMemory` 压缩 + 对话历史摘要 + 持久化 |
| MCP | 用 MCP 协议暴露 1-2 个数据分析工具 |
| 多 Agent 协作 | 4 Agent × 3 种 GroupChat 模式对比 (含评估后排除 MagenticOne 的工程决策) |
| Agent 评测 | 完成率 / 循环检测 / token 效率 / 工具误用 |
| 跨框架 | 在 LangChain/LangGraph 基础上加 AutoGen |

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env          # 填入 DASHSCOPE_API_KEY (或 OPENAI_API_KEY)
python data/make_datasets.py  # 生成评测数据集 (iris/wide_synth 已有, 补 trends/mixed/changsha_housing)
python main.py --data data/iris.csv                       # 默认 round_robin + direct
python main.py --data data/changsha_housing.csv --mode selector --transport mcp  # 业务演示, 走 MCP
python -m eval.benchmark                                  # 4 数据集 × 3 模式 = 12 次批量评测
```

CLI 参数: `--mode {round_robin,selector,llm_selector}` `--schema-mode {compact,verbose}` `--transport {direct,mcp}`。

## 为什么用 MCP

[Model Context Protocol](https://modelcontextprotocol.io/) 是 Anthropic 提的工具调用标准协议。本项目把 Coder 的 6 个可视化/检测工具用 MCP Server (stdio) 暴露，AutoGen 端通过 MCP client 调用。动机三点：

1. **工具与 Agent 解耦**: 工具实现 (Python + pandas + matplotlib) 不再绑死在 Agent 进程里, 而是独立成一个 server。同一个 server 可被 Claude Desktop、Cursor、其它语言的 MCP client 复用, 不用为每个 client 重写工具。
2. **统一工具协议**: AutoGen 原生工具是 Python 函数直连, 换框架就得重写一遍适配。MCP 把"工具长什么样、怎么调"标准化成 JSON-RPC over stdio, 跨框架迁移时工具层零改动。
3. **可演进性**: 现在走本地 stdio 子进程 (零网络依赖、最简), 后续要做成远程服务只需切 transport 为 SSE/HTTP, server 代码不动。

**取舍 (诚实记录)**: MCP 路径每次工具调用都会起一个新子进程做握手 (MCP `initialize` + `list_tools` + `call_tool`), 比直连路径多了 ~1s/次 的进程开销; 且 FastMCP 从函数签名生成的 JSON Schema 描述不如 AutoGen 直连读 Python docstring 完整, 偶发 LLM 参数名错误 (如 `box_plot` 的 `groupby`)。故本项目 **两条路并存** (`--transport direct|mcp`), W4 会在同一数据集上量化 direct vs MCP 的 token/耗时/完成率差异。

设计细节见 `tools/mcp_server.py` (server 端) 与 `agents/coder_agent.py` 的 `_FlatMcpTool` (client 端把 MCP 返回的 `list[TextContent]` 拍平成纯字符串, 保住下游靠的 `[tool_name(params)] plot_xxx.png` 路径前缀)。

## 架构

```
main.py (CLI 入口: 读 CSV → 拼 task → build_team → 跑 → 存 stats)
   │
   ▼
┌───────────────────────── teams/team_factory.py ─────────────────────────┐
│  build_team(mode, transport)                                             │
│  ├─ round_robin  : RoundRobinGroupChat (固定顺序轮转)                     │
│  ├─ selector     : SelectorGroupChat + selector_func (确定性状态机)       │
│  └─ llm_selector : SelectorGroupChat 无 selector_func (模型自调度)        │
└──────────────────────────────────────────────────────────────────────────┘
   │ 产出 4 个 AssistantAgent (system_message 分工)
   ▼
┌───── Agent 层 (agents/*.py) ─────┐   ┌──── 工具层 (tools/) ────────────┐
│  Analyst   读表头/定分析思路       │   │ data_tools.py: 6 个可视化/检测  │
│  Coder     调工具画图/算指标       │◄──┤  plot_distribution/box_plot/   │
│  Reviewer  核对图与参数对错        │   │  scatter/groupby_aggregate/    │
│  Reporter  汇总成 markdown 报告    │   │  correlation_heatmap/          │
└───────────────────────────────────┘   │  detect_outliers               │
                                        ├─ direct: Python 函数直连       │
                                        └─ mcp:    mcp_server.py (stdio) │
┌───── 记忆层 (memory/) ───────────┐         ↑ MCP client = _FlatMcpTool
│  SchemaMemory      压缩表结构元数据  │       (拍平 list[TextContent] → str)
│  ConversationMemory 对话历史摘要     │
│                   + jsonl 持久化/load │
└───────────────────────────────────┘
```

**分工一句话**: Analyst 决定"看什么", Coder 决定"怎么画", Reviewer 决定"对不对",
Reporter 决定"怎么讲"。职责分离让每个 Agent 的 system message 短而专, 比单 Agent
塞超长 prompt 更稳定 (W2 实测单 Agent 易跑偏)。代价是协作有调度开销, W4 实测
RoundRobin 平均 38 轮 / 271k token —— 这是"稳定性 vs 效率"的取舍, 项目选了前者。

## 协作模式对比(W4 实测, 4 数据集 × 3 模式)

| 模式 | 完成率 | 一次通过率 | 循环率 | 平均轮数 | 平均 token | 平均耗时 | 工具误用 |
|---|---|---|---|---|---|---|---|
| RoundRobin (固定顺序) | 25% | 25% | 0% | 38.0 | 271,284 | 156s | 16.4% |
| Selector (确定性状态机) | 0% | 0% | 0% | 46.0 | 277,543 | 182s | **3.3%** |
| LLM-Selector (模型自调度) | 0% | 0% | **75%** | 63.0 | 394,304 | 263s | 15.0% |

> 数据来源 `results/benchmark.json` (4 合成数据集: iris / wide_synth / trends / mixed, 见 `data/make_datasets.py`)。
> 完成率 = Reporter 产出真报告(含 markdown 标题且非"等图"占位)的比例;
> 循环率 = 触发 loop_detection(同 Agent 连续 3 次近似发言)的比例。

**读数 (诚实结论)**:
- **没有模式能可靠在消息上限内完成**——4 数据集里只有 trends×round_robin 一次跑出真报告。主因是 `MaxMessage` 上限(30-40)常被 Analyst→Coder→Reviewer 返工循环吃满, Reporter 没机会收尾。这是 Agent 协作的真实痛点, 不是 demo 失败。
- **LLM-Selector 最差**: 75% 循环率、最多轮数(63)、最费 token(394k)、最长耗时(263s)。**用数据证实了 W2 的判断**——qwen 当 selector 会陷入 Analyst/Coder 互相庆祝/归档死循环, 必须用确定性调度替代。
- **Selector(确定性状态机)工具误用最低(3.3%)**: 确定性顺序让 Coder 专注执行, 不被调度噪声干扰; 但完成率为 0, 因状态机僵化(Reporter 只在固定轮次被调用, 错过收尾窗口)。
- **RoundRobin 综合最稳**: 唯一有完成记录(25%)、零循环、最快; 但工具误用高(16.4%), 因固定顺序不区分返工需求。
- **结论**: 三模式各有取舍, 简历表述为"实测三模式对比, 发现 LLM 自调度循环率 75%、确定性状态机工具误用最低, 据此选定确定性调度为主"。

**为什么不用 MagenticOne**: 评估后排除。`autogen_ext.teams.magentic_one.MagenticOne` 是**固定 5-agent 团队**(Orchestrator + WebSurfer + FileSurfer + Coder + ComputerTerminal), 专为网页浏览/文件浏览任务设计, 无法替换为本项目的 4 个数据分析 agent(Analyst/Coder/Reviewer/Reporter)。其 import 链强制依赖 `playwright`(重浏览器栈 + 浏览器二进制下载), 与"pandas 表格数据分析"场景完全错配。强行接入等于装一套用不上的浏览器自动化, 且 Orchestrator 调度逻辑不匹配线性分析流水线。**这是架构错配下的工程取舍**, 非能力缺失。第三模式改用 `llm_selector`(模型自调度), 量化 LLM 当 selector 的不可靠性, 反衬确定性状态机的必要性。

## 业务故事 (W5)

演示场景: **长沙二手房挂牌分析**。一个不懂 pandas 的中介店长, 把爬来的
`data/changsha_housing.csv` (300 条挂牌, 13 字段, 含缺失) 丢进去, 4 个 Agent
自动协作产出"哪个区域是价格洼地、哪些房源被低估、带看热度怎么看"的报告。

为什么要绑业务: 技术能力只回答"会不会", 业务故事回答"做了有什么用"。
演示数据贴近真实挂牌结构 (区域/面积/总价/单价/户型/楼层/朝向/装修/建成年代/
关注/带看), 价格按"区域档位 × 面积 × 房龄 × 装修"叠加噪声生成, 刻意挖缺失
模拟字段不全。Agent 需自行派生房龄、核验单价=总价/面积, 考察脏数据处理。

完整痛点画像 + 使用故事 + 为什么是多 Agent, 见 [docs/BUSINESS_STORY.md](docs/BUSINESS_STORY.md)。
博客草稿见 [docs/BLOG_DRAFT.md](docs/BLOG_DRAFT.md)。

**实跑结果** (round_robin): 46 轮 / 148k token / 136.5s / 29 张图, Reporter 产出五块
带统计检验的发现 —— 岳麓区单价最高(¥11,820/㎡)且波动最大、开福区是洼地(¥8,230/㎡)、
越新越贵(2015 后新房 vs 2000 前老房价差 64%)、3室2厅为成交主力、关注 vs 带看 r=0.83、
精装比毛坯贵 42% (ANOVA F=217.6)。完整报告见 [results/changsha_housing_report.md](results/changsha_housing_report.md)。
> 注: 46 轮吃满消息上限后触发兜底(单独调 Reporter 重写), 印证 W4 "返工循环吃收尾窗口"的发现;
> 兜底机制保证用户始终能拿到报告。

## 文档

- [docs/BUSINESS_STORY.md](docs/BUSINESS_STORY.md) — 业务故事 (解决谁的痛点 + 演示场景)
- [docs/BLOG_DRAFT.md](docs/BLOG_DRAFT.md) — 博客草稿 (知乎/掘金)
- [docs/INTERVIEW_PREP.md](docs/INTERVIEW_PREP.md) — 面试准备 (5min 自述稿 + 20 题 Q&A)
- [results/changsha_housing_report.md](results/changsha_housing_report.md) — 业务演示实跑报告 (29 张图)
- [RESUME_TEMPLATE.md](RESUME_TEMPLATE.md) — 简历项目段 + 20 题面试 Q&A
- [ROADMAP.md](ROADMAP.md) — 分周计划与完成情况

## 进度

- [x] 脚手架搭建
- [~] W1 跑通 AutoGen quickstart + 读源码 (环境/quickstart 已跑通, 源码流程图仅 1/5 张)
- [x] W2 4 Agent 骨架 + 工具集 P0 (4 Agent + 6 工具 + 沙箱 3 层防御, benchmark 12 次验证)
- [x] W3 SchemaMemory + 沙箱 + MCP
  - [x] 3.1 记忆接入 (SchemaMemory 压缩 + ConversationMemory 持久化 + token 对照实验)
  - [x] 3.2 MCP 工具暴露 (stdio server + direct/mcp 双路可切)
  - [x] 3.3 沙箱加固 (进程级超时兜底 + 14 项单元测试; OOM 内存限制留 TODO)
- [x] W4 协作模式评测 (3 模式对比 + 排除 MagenticOne + benchmark 12 次跑批)
- [x] W5 业务绑定 (长沙二手房场景 + 业务故事 + 博客草稿) + README/简历
  - [x] W5.3 面试准备 (5min 自述稿 + 20 题 Q&A, docs/INTERVIEW_PREP.md)
  - [ ] 用户自行: 录音自测 + demo 视频