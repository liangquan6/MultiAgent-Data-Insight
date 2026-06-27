# 面试准备: 5 分钟自述 + 20 题 Q&A

> W5.3 产出。用法: 先把"5 分钟自述"背到能脱稿讲, 再把 20 题逐题过一遍,
> 答卡壳的就回去翻对应代码 (题号后标了文件锚点)。建议录音自测, 听一遍就知道哪卡。

---

## 一、5 分钟项目自述 (背到能脱稿, 控制在 4:30-5:30)

> 结构: 一句话定位 → 业务痛点 → 技术架构 → 三个工程决策 → 量化结果 → 反思。

### 0:00-0:40 一句话 + 痛点

> 我做了一个数据分析多 Agent 系统, 叫 MultiAgent-Data-Insight。一句话: 上传一个 CSV,
> 4 个 Agent 自动协作产出分析报告 + 可视化。
>
> 做这个的起因是我观察到一个小团队痛点 —— 比如房产中介店长手上有几百条挂牌数据,
> 想知道哪些房源性价比高, 但只会 Excel, 做不出多维度分析, 招数据实习生又贵。
> 我想验证能不能用多 Agent 把"会写代码的分析师"这个角色自动化掉一截。

### 0:40-1:40 技术架构

> 技术栈是 Microsoft AutoGen v0.4, 加 DashScope 的 qwen-plus 做模型。
> 架构上 4 个 Agent 分工: Analyst 决定看什么, Coder 决定怎么画, Reviewer 决定对不对,
> Reporter 决定怎么讲。职责分离让每个 Agent 的 system message 短而专, 比单 Agent
> 塞超长 prompt 更稳定。
>
> 下面分几层: 入口层 main.py 读 CSV 拼任务; Agent 协作层用 GroupChat 调度;
> 记忆层有 SchemaMemory 压缩表结构元信息、ConversationMemory 做对话摘要和持久化;
> 工具层有 6 个可视化检测工具, 支持 direct 直连和 MCP 协议双路调用。

### 1:40-3:00 三个工程决策 (最有料的一段)

> 这个项目我没只是堆功能, 有三个工程决策我觉得值得讲:
>
> **第一, 排除 MagenticOne**。AutoGen 官方有个 MagenticOne 多 Agent 团队, 我评估后排除了。
> 它是固定 5 个 agent, 为网页浏览文件浏览设计的, 没法换成我的 4 个数据分析 agent,
> 而且 import 链强制依赖 playwright 重浏览器栈, 跟表格数据分析完全错配。这是架构错配
> 下的工程取舍, 不是能力缺失。第三模式我改用 llm_selector, 让模型自己调度, 反过来
> 量化它有多不可靠。
>
> **第二, MCP 双路**。我把 6 个工具用 MCP 协议暴露, 动机是工具和 Agent 解耦, 同一个
> server 能被 Claude Desktop 复用。但踩了两个真实的坑: MCP 返回 list[TextContent]
> 被 AutoGen str() 会破坏下游图路径前缀, 我写了适配子类拍平; 子进程 import 路径缺失
> 报错。代价是 MCP 每次调用起子进程握手多一秒开销, 所以我保留 direct 直连两条路并存。
>
> **第三, SchemaMemory 记忆压缩**。宽表 50 列朴素 dump schema 很长, 我做了压缩只留
> 列名 dtype 缺失率类别数, 跑了对照实验, prompt token 降了 16.5%。

### 3:00-4:20 量化结果 (诚实带负面)

> W4 我搭了 Agent 评测, 4 个合成数据集 × 3 种协作模式跑了 12 次, 指标有完成率、
> 循环检测、token 效率、工具误用率。
>
> 实测结果是: RoundRobin 固定顺序完成率 25%、零循环、最快; 确定性 Selector 工具误用
> 最低 3.3%; LLM 自调度循环率高达 75%、最费 token。**最关键的诚实结论是: 没有模式
> 能可靠在消息上限内完成**, 12 次里只有 1 次跑出完整报告, 主因是返工循环吃满了消息上限。
> 但我加了兜底机制, 团队没产出就单独调 Reporter 重写, 保证用户始终能拿到报告。
>
> 拿长沙二手房数据实跑了一次, 46 轮 148k token 出了 29 张图, Reporter 写了五块带
> ANOVA 统计检验的发现: 岳麓区单价最高、开福区是洼地、精装比毛坯贵 42%。

### 4:20-5:00 反思 + 收尾

> 这个项目对我最大的价值不是堆了多少功能, 而是学会用数据说话。早期我以为 LLM 自调度
> 灵活会最好, 实测 75% 循环率打脸; 以为 MCP 一定比直连先进, 实测要多一秒进程开销
> 要权衡。**做 Agent 项目, 评估闭环比堆功能重要**, 这是我最大的收获。
>
> 80 分到 100 分我还差: 沙箱超时 OOM 防护没做、多模型对比没做、完成率低这个核心瓶颈
> 还没解决。这是我清楚知道的边界。

---

## 二、20 题 Q&A 示例答 (精简版, 自己再展开)

> 每题给核心答 + 文件锚点。答不全就回去读对应代码。

### 1. 为什么选 AutoGen 而不是 LangGraph?

AutoGen 原生多 Agent 协作 (GroupChat + 发言选择器 + 终止条件), 开箱即用;
LangGraph 是单图状态机, 多 Agent 要自己搭节点边。我这个"4 Agent 线性协作 + 返工回路"
场景, AutoGen 的 GroupChat 直接对上。LangGraph 更适合需要精细控制状态流转的复杂工作流。
我之前的 RAG 项目用的是 LangChain, 这个项目特意切到 AutoGen 补多框架经验。
(锚点: teams/team_factory.py)

### 2. 三种 GroupChat 模式本质差异? W4 实测? 选哪种?

- round_robin: RoundRobinGroupChat 固定顺序轮转, 不调模型做选择。
- selector: SelectorGroupChat + selector_func, 我用确定性状态机硬编码 Analyst→Coder→Reviewer→Reporter。
- llm_selector: SelectorGroupChat 不传 selector_func, 模型自己选下一个发言人。
实测: RR 完成率 25% 零循环最快; selector 误用最低 3.3% 但完成 0; llm_selector 循环 75% 最费 token。
据此选确定性调度为主 —— llm 自调度不可靠, RR 虽快但误用高。
(锚点: teams/team_factory.py 的 _selector_func)

### 3. RestrictedPython 真能拦住所有危险代码吗?

不能 100%, 我也没用 RestrictedPython, 用的是 3 层防御: 正则剥 import → AST 静态扫描
受控标识符 → 受控 exec。能拦 import os / open / __import__ 这类显式危险调用,
但绕过方法存在 (比如走已 import 模块的属性链 __builtins__), 所以 W3.3 沙箱加固是
诚实留的 TODO。真实生产要上容器隔离 + seccomp。
(锚点: tools/code_sandbox.py)

### 4. SchemaMemory 怎么判断该刷新? 怎么验证省 token?

不刷新 —— SchemaMemory 是基于 CSV 静态元信息 (列名/dtype/缺失率/类别数),
数据不变 schema 不变, 没有刷新需求。验证: 跑了对照实验, 同一宽表 verbose 朴素 dump
vs compact 压缩, prompt token 从 878k 降到 733k, 降 16.5%, 写在 results/token_compare.json。
诚实注: 不是严格单变量, compact 组 agent 行为也变了 (画 334 张图 vs 14 张), completion token 反涨。
(锚点: memory/schema_memory.py, experiments/token_compare.py)

### 5. 对话摘要压缩会不会丢关键信息?

会, 这是压缩的固有代价。ConversationMemory 用滚动窗口, 超窗口的旧消息压缩成摘要。
我没做严格的"信息保留率"量化验证, 这是局限。当前靠摘要保留关键决策 (分析思路、返工意见),
丢的是过程性闲聊。要严格验证可以做"压缩前后报告质量对比", 留作改进。
(锚点: memory/conversation_memory.py)

### 6. 多 Agent 之间怎么传递上下文? 广播还是路由?

AutoGen GroupChat 是**广播** —— 每条 message 进共享消息列表, 所有 Agent 都看得到。
不是点对点路由。所以每个 Agent 看到全队历史, 靠 system message 约束它只关注自己职责相关的。
这也是 token 涨得快的原因之一 (每轮都带全历史)。
(锚点: teams/team_factory.py, AutoGen GroupChat 机制)

### 7. 终止条件怎么设计? 为什么 TERMINATE + MaxMessage?

两条: TextMmention("TERMINATE") 让 Reporter 主动收尾; MaxMessage(30-40) 兜底防跑飞。
没用 PASS_FINAL 触发终止 —— PASS 在我的设计里是 Reviewer 标记"通过"的状态信号,
不是终止信号, 终止权交给 Reporter 的 TERMINATE。MaxMessage 是硬上限, 保证不无限烧 token。
(锚点: teams/team_factory.py 的 _term)

### 8. token 怎么统计? 哪些消息带 models_usage?

从 AutoGen message 的 models_usage 字段取 (RequestUsage dataclass, prompt_tokens +
completion_tokens)。**只有 LLM 推理产生的消息带 models_usage**, 工具结果消息和纯用户
消息是 None。所以统计时要跳过 None。prompt 和 completion 分开算, W4 benchmark 里
avg_tokens 是两者之和。
(锚点: main.py 的 _usage_of, eval/metrics.py 的 token_efficiency)

### 9. MCP 比 function calling 多解决什么? 双路取舍?

function calling 是框架内 Python 函数直连, 换框架工具层要重写。MCP 把"工具长什么样、
怎么调"标准化成 JSON-RPC, 同一个 server 能被 Claude Desktop / Cursor / 其它语言 client
复用, 工具层零改动跨框架。取舍: MCP 每次调用起子进程握手多 ~1s 开销, FastMCP 生成的
schema 描述不如直连读 docstring 完整, 偶发参数名错误。所以双路并存, 不强行只用 MCP。
(锚点: tools/mcp_server.py, agents/coder_agent.py 的 _FlatMcpTool)

### 10. 工具误用率怎么定义? 为什么 selector 最低?

误用 = 工具调用报错或参数与 schema 不符 (eval/metrics.py 的 extract_tool_calls 正则
提取 [tool_name] 头 + 报错关键词检测)。selector 误用最低 3.3%, 因为确定性顺序让 Coder
专注执行不被调度噪声干扰; RR 固定顺序不区分返工需求误用 16.4%; llm_selector 调度混乱误用 15%。
(锚点: eval/metrics.py)

### 11. 循环检测策略? 75% 循环率怎么算?

loop_detection: 同一 Agent 连续 3 次近似发言 (内容相似度阈值) 判定循环。
75% = 4 个数据集里 llm_selector 有 3 个触发循环检测。漏报风险: 相似度阈值定高会漏;
误报风险: 阈值定低把正常迭代当循环。当前阈值是经验值, 没做精确调参, 这是局限。
(锚点: eval/metrics.py 的 loop_detection)

### 12. 几百列 schema 还会爆 token, 怎么进一步压?

当前 SchemaMemory 压缩元信息但列多还是长。进一步: 按列重要性排序只保留 top-N
(基于 dtype + 缺失率 + 业务相关性打分); 或分块 schema 按需注入 (Analyst 第一轮只给概览,
Coder 画某列时才注入该列详情)。这些是改进方向, 当前没做。
(锚点: memory/schema_memory.py, 改进 TODO)

### 13. Reviewer 返工会不会无限循环? 12 次只完成 1 次为什么?

会, 这正是 W4 完成率低的主因。返工循环 (Analyst→Coder→Reviewer 反复) 吃满 MaxMessage,
Reporter 没机会收尾。处理: MaxMessage 硬上限兜底 + 触发后单独调 Reporter 重写 (兜底机制)。

**W5 追踪到一个具体根因并修复**: LLM 误把"想要的图名"塞进 save_dir 参数
(如传 `results/plots/sepal_scatter.png`), 沙箱 `_ensure_dir` 不校验地把 `sepal_scatter.png`
当目录建, 真图存进 `sepal_scatter.png/plot_xxx.png`, 路径变成 `xxx.png\plot_xxx.png`。
Reviewer 反复拦"非法路径"让 Coder 改, 但 Coder 改不掉 (它传的 save_dir 本身就是这格式),
陷入死循环吃满消息预算。修法: `_ensure_dir` 检测图片后缀就剥离成父目录。
**修复后实测同数据集 token 从 157k 降到 72k (-54%), 轮数 46→31, 耗时 181s→97s** ——
证明返工循环里有相当一部分是这个路径污染 bug 造成的。

12 次只完成 1 次 (trends×round_robin) 是真实痛点, 不全是 bug —— 还有消息预算 vs
调度策略的根本矛盾。修了这个 bug 后完成率应改善, 但 80→100 分仍需解决动态 MaxMessage
或提前触发 Reporter 的策略。
(锚点: tools/data_tools.py 的 _ensure_dir, main.py 的 _reporter_fallback)

### 14. 沙箱超时 / OOM 怎么处理?

**超时已做 (W3.3)**: run_code 在子进程里 exec, 主进程 `join(timeout)` 兜底 (multiprocessing,
非 signal.alarm —— Windows 无 SIGALRM)。默认 30s, 超时 terminate 子进程返回明确错误,
Agent 能继续走不卡死整个 run。踩过一个坑: Windows spawn 模式要 pickle 传参, code object
不可 pickle, 所以编译挪到子进程内做, 只传源码字符串。14 项单元测试覆盖 (tests/test_code_sandbox.py)。
**OOM 内存限制留 TODO**: Windows 无 rlimit, 仅靠超时间接兜底 (OOM 通常先拖慢再超时);
真生产建议容器 + cgroups。面试如实说"超时做了, 内存限制是诚实留的边界"。
(锚点: tools/code_sandbox.py 的 _exec_child/run_code, tests/test_code_sandbox.py)

### 15. 多模型对比做过吗? 为什么用 qwen 不用 gpt-4o?

没做严格多模型对比, 这是局限。用 qwen-plus 是因为: 国内 DashScope OpenAI 兼容模式
便宜好调试, 实习项目预算有限; qwen-plus 中文指令理解够用。gpt-4o 理论上调度更稳,
但成本高 5-10 倍, 对这个验证性项目不划算。如果要上生产对比, 会跑 gpt-4o-mini / qwen-plus
/ deepseek 三家同任务对比。
(锚点: config.py, .env)

### 16. AutoGen v0.2 和 v0.4 为什么选 v0.4?

v0.2 是 ConversableAgent 老架构, 单体 agent 互聊; v0.4 拆成 Core (消息层) + AgentChat
(高层 API) + Ext (扩展), 架构更清晰, GroupChat 和条件终止是 first-class 支持。
我这个多 Agent 协作场景 v0.4 的 GroupChat 直接对上, v0.2 要自己管对话轮转。且 v0.4 是
当前主推版本, 学新不学旧。
(锚点: requirements.txt autogen-agentchat/core/ext)

### 17. 为什么不做 MagenticOne? 怎么判断的?

读源码 + 评估: MagenticOne 是固定 5-agent (Orchestrator+WebSurfer+FileSurfer+Coder+
ComputerTerminal), 为网页浏览/文件浏览设计, 不能替换成我的 4 个数据分析 agent;
import 链强制拉 playwright (重浏览器栈 + 浏览器二进制下载), 与表格数据分析场景错配。
强行接入等于装一套用不上的浏览器自动化。判断依据: 架构错配, 不是能力问题。改用
llm_selector 做第三模式, 反而量化了 LLM 自调度的不可靠性, 更有说服力。
(锚点: README "为什么不用 MagenticOne")

### 18. 数据集脏 (列名带空格/中文乱码/编码) 工具怎么扛?

列名带空格: 工具参数用列名传字符串, pandas 支持空格列名 (df["col name"]), 没问题。
中文列名: 同上, pandas 原生支持。编码混乱: main.py 读 CSV 没显式指定 encoding,
依赖 pandas 默认 utf-8, 非 utf-8 文件会报错 —— 这是没处理的边界, 真实场景要加
encoding 自动探测 (chardet)。实测我用的是 utf-8 合成数据, 没踩这个坑。
(锚点: main.py 读 CSV 处, data_tools.py)

### 19. 和之前 RAG 项目能力交叉吗? 怎么讲区别?

不交叉, 讲法: RAG 项目是"检索-生成" —— 知识库问答, 核心是 embedding + 向量检索 +
生成; 这个项目是"决策-编码-执行"多 Agent —— 核心是 Agent 协作 + 工具调用 + 评估闭环。
一个是让模型"知道", 一个是让模型"会做"。面试官不爱听"也是大模型应用", 要讲清
能力维度不同: RAG 补的是知识检索, 多 Agent 补的是任务编排和工具使用。
(锚点: 简历项目段两项目对比)

### 20. 80 分项目长什么样, 100 分还差什么?

80 分 (现状): 4 Agent 协作跑通 + 3 模式对比有数据 + MCP 双路 + 记忆压缩 + 评估闭环 +
业务演示。100 分还差: (1) 沙箱超时/OOM 防护 (W3.3); (2) 完成率低的核心瓶颈没解决
(消息预算 vs 返工循环的权衡, 可能要动态 MaxMessage 或提前触发 Reporter);
(3) 多模型对比没做; (4) Streamlit 看板没做; (5) 对话摘要信息保留率没量化。
清楚知道边界在哪, 比假装全做完更值钱。
(锚点: ROADMAP 未勾选项)

---

## 三、练习建议

1. **先背 5 分钟自述**, 录音听 3 遍, 卡壳的地方标出来重练。
2. **20 题分两轮**: 第一轮逐题看示例答, 不熟的去翻代码锚点; 第二轮盖住答案自测,
   能口头讲出来才算过。
3. **高频追问预警**: 第 2、7、10、13、17 题最容易被深挖 (都是你做了实测/决策的点),
   这几题要能讲到代码细节, 不能只停在结论。
4. **诚实题 (14、20) 别装**: 面试官更信"知道哪里不行"的人, 装全做完反而露怯。
