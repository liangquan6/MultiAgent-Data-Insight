# W1-W5 代码级行动表

> 时间锚点: 5 周内完成, 对应暑假实习投递节奏。每周目标可独立验收。
> "坐实简历能力"标注 🎯: 表示这一步做完, 简历里某条能力就不再虚。

## W1  跑通 + 读源码 (目标: 不靠抄, 能讲清 AutoGen 内部)

### 1.1 环境与 Hello World
- [x] `pip install -r requirements.txt` 装好
- [x] `.env` 填 Key (DashScope qwen-plus, OpenAI 兼容模式)
- [ ] 跑官方 quickstart 写进 `docs/w1_quickstart.md` — 未单独产出 quickstart 文档, 但 W2 已用 4 Agent 端到端跑通, 等价覆盖

### 1.2 读源码 (重点, 简历要讲得出)
- [ ] `autogen_agentchat/agents/AssistantAgent` —— 构造参数、tool 注册流程
- [ ] `teams/RoundRobinGroupChat` 与 `SelectorGroupChat` —— 何时换发言人、终止条件如何触发
- [ ] `conditions/Termination` 全家桶: `TextMention` / `MaxMessage` / `TokenUsage`
- [ ] `models/OpenAIChatCompletionClient` —— tool schema 怎么从函数 docstring 生成
- 产出: 仅 `docs/w1_AssistantAgent_map.md` 1 张, 缺另外 4 张 (低优先, 不影响项目能跑)

### 1.3 数据准备
- [x] 数据集放进 `data/` + 填好 `eval/datasets_meta.json` (4 集: iris/wide_synth/trends/mixed)
      - 改用合成集而非 Kaggle 10 集: 外部下载慢/不稳, 且评测关心 Agent 协作行为非数据真实性,
        合成集能精确控制结构覆盖不同坑 (理由见 data/make_datasets.py 文档头)
- [x] 验收: `python main.py --data data/iris.csv --mode round_robin` 跑出 4 Agent 对话 + 报告 + 图

## W2  4 Agent 骨架 + 工具集 P0  (🎯 坐实"工具编排")

### 2.1 让沙箱可执行 LLM 代码
- [x] `tools/code_sandbox.py` 单元测试: tests/test_code_sandbox.py 14 项 (W3.3 补, 覆盖黑名单拦截/白名单注入/正常执行/超时兜底)
- [x] 新增工具 `run_code(code)`: 接 LLM 生成的 pandas 片段, 走沙箱返回 stdout + plot (ROADMAP 原名 run_pandas_code, 实际命名 run_code)
- [x] CoderAgent 工具表换成 `[run_code, plot_distribution, box_plot, scatter_plot, groupby_aggregate, correlation_heatmap, detect_outliers]`

### 2.2 工具调度真实可用
- [x] Analyst 用 load_csv / profile_dataset 真拿到 schema, 注入 SchemaMemory
- [x] CoderAgent 按思路调用工具执行可视化 (6 个画图/检测工具)
- [x] ReviewerAgent 检查产出, 错了给"返工"意见让 CoderAgent 再来一轮 (W4 实测 Reviewer 真拦截 Coder 误调用)
- 验收: 在 4 个数据集上端到端跑出"图 + 报告" (W4 benchmark 12 次跑批 + iris/housing 实跑均验证)

## W3  记忆 + 沙箱 + MCP  (🎯 坐实"记忆管理" + "MCP")

### 3.1 记忆接入
- [x] SchemaMemory 注入到 task 文本, 验证: 不再每轮把全 schema 塞给模型
- [x] ConversationMemory 接入 Team 对话, 跨轮历史可持久化 + 续聊
- [x] 做对照实验: 「无记忆 vs SchemaMemory」, 单次分析 token 消耗, 写入 `results/token_compare.json` 🎯
      - 结果(宽表 50 列 200 行): verbose 总 887,974 vs compact 755,717, 省 14.9%。
      - 核心假设成立: compact 把 prompt token 砍掉 16.5% (878k→733k), 证明 schema 压缩直接降上下文成本。
      - 但 completion token 反涨 2.3x (9.9k→22.4k): compact 组 agent 发散到画 334 张图 vs verbose 14 张,
        agent 行为随 schema 内容变了, 不是严格单变量对照 → 净节省被稀释, 因果归因偏弱。
      - 改进(留 W4 复跑): 固定工具调用上限或多次取均值, 用「prompt_tokens/轮」这类窄指标。

### 3.2 MCP
- [x] `pip install mcp`, 把 `plot_distribution` / `correlation_heatmap` 用 MCP Server 协议暴露
      - `tools/mcp_server.py` 用 FastMCP 暴露全部 6 个工具, transport=stdio。
- [x] AutoGen 端用 MCP client 调用 (走 stdio transport)
      - `agents/coder_agent.py` 加 `transport` 分支; `_FlatMcpTool` 把 MCP 返回的
        `list[TextContent]` 拍平成纯字符串, 保住下游 `[tool(params)] plot_xxx.png` 路径前缀。
      - `build_team`/`build_coder_agent` 异步化; main.py 加 `--transport mcp`。
      - 验证: iris 走 mcp 端到端出报告 (23 图 / 160k token / 209s), 兜底路径补报告。
- [x] 写一段 README "为什么用 MCP" 的说明: 统一工具协议、和 Claude Desktop 通用 🎯
- 备注(留 W4 量化): MCP 每次调用起子进程握手 (~1s/次开销); FastMCP 生成的 schema 描述
  不如直连完整, 偶发 LLM 参数名错误。direct vs mcp 同集对比放 W4。

### 3.3 沙箱加固
- [x] 限制执行时长: run_code 在子进程里 exec, 主进程 join(timeout) 兜底 (multiprocessing,
      非 signal.alarm —— Windows 无 SIGALRM); 默认 30s, 超时 terminate 子进程返回明确错误,
      Agent 能继续走不卡死整个 run。code object 不可 pickle, 编译挪到子进程内做。
- [x] 单元测试: tests/test_code_sandbox.py 14 项 (黑名单拦截 6 + 白名单注入 2 + 正常执行 3 + 超时兜底 3)
- [ ] 资源限制 (内存 OOM): Windows 无 rlimit, 仅靠超时间接兜底 (OOM 通常先拖慢再超时);
      真生产建议容器 + cgroups。诚实留 TODO。
- 验收: `python -m unittest tests.test_code_sandbox -v` 14 项全过; while True 死循环 3s 被终止。

## W4  协作模式对比 + Agent 评测  (🎯 坐实"多 Agent 协作" + "Agent 评测")

### 4.1 协作模式 (MagenticOne 评估后排除, 改用 llm_selector 第三模式)
- [x] 评估 MagenticOne: 源码确认是固定 5-agent (Orchestrator+WebSurfer+FileSurfer+Coder+
      Terminal), 为网页/文件浏览任务设计, 不能塞入本项目 4 个数据分析 agent; import 链强制拉
      playwright (重浏览器栈), 与表格数据分析场景错配 → 排除 (工程判断, 写进 README)。
- [x] 第三模式改用 `llm_selector`: SelectorGroupChat 不传 selector_func, 让模型自调度。
      这是 W2 用确定性状态机替代的失败方案, W4 量化它: 预期循环/低完成率, 证明确定性调度必要。
- [x] `team_factory.build_team("llm_selector")` 分支 + MaxMessage 调 40 (给自调度空间)。

### 4.2 评测跑批
- [x] `python -m eval.benchmark` 跑 4 数据集 × 3 模式 = 12 次, 写入 `results/benchmark.json`
      (合成数据集: iris/wide_synth/trends/mixed, 见 data/make_datasets.py)
- [x] 补 `eval/metrics.py` 真实统计: loop_detection / first_pass_rate / tool_misuse_rate
      (含 extract_tool_calls 正则提取工具调用 + 报错判定)
- [x] benchmark 增量落盘 (每跑完一条写一次, 防中途崩丢全部) + error 行容错
- [ ] Streamlit 看板: `streamlit run dashboard.py` 展示三模式对比柱状图 (可选, 优先级低)
- 验收: README 的"协作模式对比"表填上真实数字。
- 实测结果(4 数据集 × 3 模式, results/benchmark.json):
  - round_robin: 完成率 25% / 循环 0% / 38 轮 / 271k token / 156s / 误用 16.4%
  - selector(确定性): 完成率 0% / 循环 0% / 46 轮 / 278k token / 182s / 误用 3.3%(最低)
  - llm_selector(模型自调度): 完成率 0% / 循环 75% / 63 轮 / 394k token / 263s / 误用 15%
  - 核心结论: LLM 自调度循环率 75%, 证实 W2 改用确定性调度的必要性;
    确定性状态机工具误用最低; 无模式能可靠在消息上限内完成(返工循环吃满 MaxMessage)。

## W5  业务绑定 + 对外发布

### 5.1 业务故事
- [x] 选定场景: 长沙二手房挂牌分析 (合成数据 data/changsha_housing.csv, 300×13, 含缺失)
      - 选二手房而非教务: 中介店长"有数据没分析师"痛点更普世, 演示叙事更顺。
- [x] 业务文: docs/BUSINESS_STORY.md (痛点画像 + 使用故事 + 实跑结果 + 为什么多 Agent)
- [x] README 加"业务故事"章节 + 实跑报告链接 (results/changsha_housing_report.md)
- [ ] 录一段 90s demo 视频 (OBS 或微信录屏即可) — 待用户自行录制

### 5.2 发布三件套
- [x] README 终稿: 架构图 + 对比表 + 快速开始 + 业务故事 + 文档索引
- [x] 博客草稿: docs/BLOG_DRAFT.md (知乎/掘金向, 含真实跑批数据 + 三个工程决策)
- [x] 简历: RESUME_TEMPLATE.md 项目段已用真实 W4 数字 (12 次跑批 + 三模式指标)

### 5.3 面试模拟
- [x] 5 分钟项目自述稿: docs/INTERVIEW_PREP.md (一句话→痛点→架构→三决策→量化→反思, 带时间轴)
- [x] 20 题 Q&A 示例答: docs/INTERVIEW_PREP.md (每题核心答 + 代码锚点, 含高频追问预警)
- [ ] 用户自行: 录音自测 5min 自述 + 逐题口头过 20 题 (文档已备好, 练习靠用户)

## 颗粒度参考: 每天该花多久

- W1: 2 h/天 (读懂为主)
- W2-W3: 3-4 h/天 (主力编码期)
- W4: 3 h/天 (评测 + 修 bug)
- W5: 2 h/天 (写作 + 录像)

跑不通优先级: W2 > W3 > W4 > W1 源码 > W5。
源码读不懂别死磕, 先把项目跑通再回头读。