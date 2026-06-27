# 我做了个让中介店长不用学 Python 的数据分析 Agent (附真实跑批数据)

> 这是一篇面向知乎/掘金的技术博客草稿。核心卖点是: 不是又一个 RAG 聊天 demo,
> 而是多 Agent 协作 + 工具调用 + 评估闭环, 且有诚实的负面数据。

## 起因: "有数据, 没分析师" 的小团队痛点

我有个做房产中介的朋友, 店里手上有几百条片区挂牌数据, 老板每周问他
"哪些房源性价比高、带看热度怎么看"。他只会 Excel 透视表, 做不出
"按区域看单价分布 + 户型性价比 + 带看转化"这种多维度分析, 而招个数据实习生
成本又高。类似的人不少: 教务新人要交成绩简报、自媒体作者要出数据图文 ——
**有数据, 没分析师, 没时间学工具**。

我就想验证一个问题: **能不能用多 Agent 把"会写代码的分析师"这个角色自动化掉一截**,
让非技术用户上传一张表, 直接拿到一份能看的报告 + 图?

## 做了什么: 4 个 Agent 协作的分析流水线

基于 Microsoft AutoGen (v0.4) 二开, 上传 CSV 后 4 个 Agent 自动协作:

| Agent | 职责 | 一句话 |
|---|---|---|
| Analyst | 读表头, 定分析思路 | 决定"看什么" |
| Coder | 调工具画图/算指标 | 决定"怎么画" |
| Reviewer | 核对图与参数对错 | 决定"对不对" |
| Reporter | 汇总成 markdown 报告 | 决定"怎么讲" |

职责分离的好处是每个 Agent 的 system message 短而专, 比把所有要求塞进一个
超长 prompt 的单 Agent 更稳定 (我早期试过单 Agent, 容易跑偏到无关分析)。
Reviewer 还能形成显式返工回路 —— 单 Agent 自己画自己评, 错了容易一路错到底。

**真实跑出来的报告长这样** (iris 数据集, Reporter 原样产出):

> ## 关键发现
> ### 花瓣尺寸可高效区分物种 —— 尤其 setosa vs 其余两类
> petal_len: setosa(1.46) vs versicolor(4.26) vs virginica(5.55) → 两两均值差 > 2.7,
> 远超各自标准差。结论: setosa 可通过花瓣尺寸完全线性分离。
> 📎 支持证据图: results/plots/plot_1782482863042.png

不是泛泛的"数据有差异", 而是带具体数值、带图证据链接、带可执行结论
("优先用 petal_len 可达 >95% 准确率")。

## Reviewer 真的在干活: 一次真实的返工

跑长沙二手房数据 (300 条挂牌) 时, Coder 调了个 `detect_outliers` 工具但没传 `column` 参数,
Reviewer 当场拦下来:

> [Reviewer] detect_outliers 工具调用未被 Analyst 要求, 属于冗余操作;
> 且两次调用均未指定 column 参数 (如 column=带看次数), 输出 bounds 和 sample
> 无上下文, 无法判断针对哪列、是否合理, 与五点分析任务无关。

这种"Reviewer 按 Analyst 的任务清单逐条核对 Coder 的工具调用"的协作,
是单 Agent 闭环做不到的。也是我坚持做多 Agent 而不是单 ReAct loop 的核心理由。

## 实跑出来的报告长什么样

那次跑批 (round_robin, 46 轮 / 148k token / 136.5s / 29 张图) 最终产出的报告
(results/changsha_housing_report.md), Reporter 写了五块发现, 都是带数据 + 图证据的:

- **区域格局**: 岳麓区单价最高(¥11,820/㎡)且波动最大, 开福区是洼地(¥8,230/㎡),
  区域间标准差最大是最小的 2.13 倍
- **房龄效应**: 越新越贵, 2015 后新房均 ¥12,150 vs 2000 前老房 ¥7,420, 价差 64%;
  散点图拟合 LOESS 趋势线斜率 ≈ −320 ¥/㎡/年
- **户型策略**: 3室2厅是成交主力(总价中位 ¥138 万), 4室改善溢价 56%
- **流量转化**: 关注人数 vs 带看次数 皮尔逊 r=0.83 (p<0.001), 强正相关
- **装修溢价**: ANOVA F(2,12840)=217.6, 精装比毛坯贵 42% (Tukey HSD 多重比较)

每条发现都带 `results/plots/plot_xxx.png` 证据路径链接。不是泛泛的"数据有差异",
而是带统计检验、带可执行结论 ("开发商避免简装降标, 推行菜单式精装")。

> **诚实注**: 这次 46 轮吃满消息上限, 触发了"团队协作未产出报告"兜底
> (单独调 Reporter 重写)。这印证了下面 W4 的发现 —— 返工循环会吃掉收尾窗口。
> 但兜底机制保证了用户始终能拿到一份报告, 不至于白跑。

## 三个工程决策 (踩过的坑)

### 1. 为什么不用 MagenticOne

AutoGen 官方有个 `MagenticOne` 多 Agent 团队, 我评估后排除了。它是**固定 5-agent
团队** (Orchestrator + WebSurfer + FileSurfer + Coder + ComputerTerminal),
专为网页浏览/文件浏览设计, 没法替换成我的 4 个数据分析 Agent。而且 import 链
强制依赖 `playwright` (重浏览器栈 + 浏览器二进制下载), 跟"pandas 表格数据分析"
完全错配。强行接入等于装一套用不上的浏览器自动化。**这是架构错配下的工程取舍**,
不是能力缺失。

### 2. MCP 双路: 工具协议标准化 vs 直连性能

我把 Coder 的 6 个可视化/检测工具用 MCP (Model Context Protocol) Server 暴露,
AutoGen 端通过 MCP client 调用。动机是工具与 Agent 解耦 —— 同一个 server 能被
Claude Desktop、Cursor 复用, 不用为每个 client 重写工具。

但踩了两个真实的坑:
- **MCP 返回 `list[TextContent]`, AutoGen 直接 `str()` 会变成
  `[TextContent(type='text', text='...')]`**, 把下游靠的 `[tool_name] plot_xxx.png`
  路径前缀解析搞坏。我写了 `_FlatMcpTool` 子类把返回拍平成纯字符串才修好。
- **MCP subprocess `python tools/mcp_server.py` 找不到 `tools` 模块**,
  因为子进程没有项目根目录在 sys.path。在 mcp_server.py 顶部注入 _PROJECT_ROOT 解决。

代价也诚实记: MCP 路径每次工具调用都起子进程做握手, 比直连多 ~1s/次 进程开销。
所以项目**两条路并存** (`--transport direct|mcp`), 不强行只用 MCP。

### 3. 记忆压缩: SchemaMemory 降 prompt token 16.5%

宽表 (50 列) 朴素 dump schema 很长, 我做了个 `SchemaMemory` 只压缩表结构元数据
(列名/dtype/缺失率/类别数), 跑了 token 对照实验:
**verbose 887,974 vs compact 755,717 tokens, 节省 14.9%; prompt token 降 16.5%。**

## 诚实的负面数据: 12 次跑批, 完成率只有 25%

这是我觉得这个项目最不一样的地方 —— 不是只报喜, 而是把不行的地方也量化出来。

跑了 4 个合成数据集 × 3 种协作模式 = 12 次:

| 模式 | 完成率 | 循环率 | 平均轮数 | 平均 token | 工具误用 |
|---|---|---|---|---|---|
| RoundRobin (固定顺序) | 25% | 0% | 38 | 271k | 16.4% |
| Selector (确定性状态机) | 0% | 0% | 46 | 278k | **3.3%** |
| LLM-Selector (模型自调度) | 0% | **75%** | 63 | 394k | 15.0% |

**三个诚实结论**:

1. **没有模式能可靠在消息上限内完成** —— 4 数据集里只有 trends×round_robin
   一次跑出完整报告。主因是 `MaxMessage` 上限(30-40)常被 Analyst→Coder→Reviewer
   返工循环吃满, Reporter 没机会收尾。**这是 Agent 协作的真实痛点, 不是 demo 失败。**

2. **LLM 自调度最差**: 75% 循环率、最多轮数、最费 token。qwen 当 selector 会陷入
   Analyst/Coder 互相庆祝/归档死循环, 必须用确定性调度替代。这用数据证实了
   我早期的判断。

3. **确定性状态机工具误用最低(3.3%)**, 确定性顺序让 Coder 专注执行, 不被调度噪声干扰;
   但完成率为 0, 因状态机僵化(Reporter 只在固定轮次被调用, 错过收尾窗口)。

**三模式各有取舍**, 据此我选定确定性调度为主。简历表述也是这个, 不吹"全部完成"。

## 这个项目对我自己的价值

技术栈上覆盖了简历要的几项: 工具编排 (MCP)、记忆管理 (SchemaMemory 压缩)、
Agent 评测 (6 项指标)、多框架 (在 LangChain 基础上加 AutoGen)、工程取舍
(排除 MagenticOne、确定性 vs LLM 调度)。

但更值的是**学会用数据说话而不是讲故事**: 早期我以为 LLM 自调度很灵活会最好,
实测 75% 循环率打脸; 以为 MCP 一定比直连"先进", 实测多 1s/次 进程开销要权衡。
**做 Agent 项目, 评估闭环比堆功能重要。** 这是我最大的收获。

---

> 项目地址: [MultiAgent-Data-Insight](https://github.com/...)
> 技术栈: AutoGen v0.4 + DashScope(qwen-plus) + pandas/matplotlib + FastMCP
> 欢迎讨论: 你做多 Agent 项目时, 调度模式是怎么选的? 有没有踩过类似的循环坑?
