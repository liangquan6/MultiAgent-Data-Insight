# 简历项目描述模板

> 数字用你 W4 跑出来的真实值替换 X / Y。Repo URL 填上线后的 GitHub 地址。
> 篇幅控制在简历一栏内 5-6 条, STAR 结构 + 量化, 不要写空泛形容词。

---

## MultiAgent-Data-Insight｜基于 AutoGen 二开的数据分析多 Agent 系统
独立开发 · 2026.07-2026.08 · https://github.com/你/MultiAgent-Data-Insight

**情景**: 企业日常数据分析依赖人工写 pandas、出图、写报告, 流程重复、门槛高, 难以快速覆盖一线业务见数需求。

**任务**: 基于 Microsoft AutoGen v0.4 设计端到端多 Agent 数据分析系统, 输入 CSV 自动产出可视化图表 + 结构化分析报告, 并沉淀可复用的 Agent 评测能力。

**工作**:
1. 设计四层解耦架构 (入口层-Agent 协作层-记忆层-工具沙箱层), 用工厂模式管理模型实例, OpenAI / DashScope 切换只改 .env (裸模型需手传 ModelInfo 绕过 AutoGen 白名单校验, 已踩坑修复)
2. 实现 4 Agent (分析师-编码员-审查员-报告员) 线性协作; LLM 当发言选择器实测循环率 75% (qwen 会陷入 Analyst/Coder 互相庆祝), 改用确定性状态机硬编码发言顺序保证报告员被调用到
3. 自定义 6 个数据工具 + 3 层防御沙箱 (正则剥 import → AST 静态扫描 → 受控 exec), 拦截 `import os / open / __import__` 等危险调用; 加进程级超时兜底 (multiprocessing 子进程 exec + join timeout, 防 LLM 写死循环卡死整个 run; Windows spawn 下 code object 不可 pickle 的坑已修), 14 项单元测试覆盖
4. 用 FastMCP 把 6 个工具以 stdio 协议暴露, 直连 / MCP 双路可切; 踩并修两个坑: MCP 返回的 list[TextContent] 被 str() 破坏下游图路径前缀 (写适配子类拍平)、子进程 import 路径缺失被误导为连接关闭
5. 设计 SchemaMemory 压缩 DataFrame 元信息 + 对话历史滚动摘要 + jsonl 持久化续聊; 对照实验测得单轮 prompt token 下降 16.5% (宽表 50 列, verbose 16.5%→compact)
6. 搭建 Agent 行为评测 (完成率/循环检测/token 效率/工具误用率), 4 数据集 × 3 模式 12 次跑批: RoundRobin 完成率 25%/零循环/最快、确定性 Selector 工具误用最低 3.3%、LLM 自调度循环率 75% 最费 token; 评估后排除 MagenticOne (固定 5-agent 网页浏览导向, 场景错配) 改用模型自调度做对照, 据此选定确定性调度为主

**成果**: 4 数据集 12 次跑批 data 已落 `results/benchmark.json`; 实测发现并量化"消息上限与返工循环矛盾"——无模式能稳定在消息上限内完成 (仅 trends×RoundRobin 一次出真报告), 主因是 Analyst→Coder→Reviewer 返工吃满 MaxMessage、报告员错过收尾窗口。
**W5 定位并修复两个返工死锁源** (从"发现问题"到"定位根因"闭环):
① 路径污染 bug — LLM 把"想要的图名"塞进 save_dir, 沙箱 _ensure_dir 把 `.png` 当目录建, 真图存进 `xxx.png/plot_xxx.png`, Reviewer 反复拦"非法路径"但 Coder 改不掉 (它传的参数本就是这格式)。修: _ensure_dir 检测图片后缀剥离成父目录 + 单测覆盖。实测 token -54%/轮 46→31/耗时 -46%。
② Reviewer 不可达子任务判定 — Analyst 提建派生列 (如 petal_ratio=a/b) 但工具集无 add_column, Reviewer 不知工具边界一味要求返工, Coder 反复试报错的工具"装作干活", 双方卡死。修: Reviewer system_message 显式列工具清单 + 加"能力外子任务判定为不可达并跳过"规则, 配套让 Coder 诚实报告边界。实测不再兜底/轮 46→9/token 142k→12.7k (-91%)/耗时 152s→46s/图 62→5 (去重)。两修复均在 prompt/工具层, 不碰沙箱安全。项目博客 + 对比表见 README。
选用 AutoGen 而非 LangGraph 的判断: 业务需要多角色串行协作 + 终止协议, AutoGen 内置 GroupChat 抽象直接契合; 评估 MagenticOne 后因其为网页浏览导向、强依赖 playwright 而排除。

---

## 面试可能追问 20 题 (对着练, 答不出就回去补代码)

1. 为什么选 AutoGen 而不是 LangGraph? 各自适合什么场景?
2. 你对比的三种 GroupChat 模式本质差异? W4 实测数据分别怎么样, 据此你选哪种?
3. RestrictedPython 真能拦住所有危险代码吗? 有没有绕过方法?
4. SchemaMemory 怎么判断该刷新? 不刷新会怎样? 你怎么验证它真省了 token?
5. 对话摘要压缩会不会丢关键信息? 怎么验证?
6. 多 Agent 之间怎么传递上下文? GroupChat 的 message 是广播还是路由?
7. 终止条件怎么设计? 为什么用 TERMINATE + MaxMessage 两条, 而 PASS_FINAL 不触发终止?
8. token 消耗怎么统计? prompt / completion 分开算了吗? 哪些消息带 models_usage 哪些不带?
9. MCP 比 function calling 多解决了什么? 你的项目里它和价值在哪? 双路可切有什么取舍?
10. 工具误用率怎么定义? 误用率高怎么改? 为什么确定性 Selector 误用最低?
11. 循环检测的具体策略? 漏报和误报怎么权衡? llm_selector 75% 循环率怎么算出来的?
12. 数据集 schema 几百列时 token 还会爆, 你怎么进一步压?
13. ReviewerAgent 返工机制会不会陷入无限循环? 你的处理? 为什么 W4 12 次只完成 1 次?
14. 沙箱执行超时 / OOM 怎么处理? (W3.3 未做, 诚实回答现状)
15. 多模型对比做过吗? qwen-plus 在你这个任务表现怎么样? 为什么用 qwen 不用 gpt-4o?
16. AutoGen v0.2 (ConversableAgent) 和 v0.4 (Core+AgentChat) 你为什么选 v0.4?
17. 为什么不做 MagenticOne? 你怎么判断的? 评估了什么?
18. 数据集脏 (列名带空格 / 中文乱码 / 编码混乱) 你的工具怎么扛?
19. 和你之前的 RAG 客服项目, 能力上交不交叉? 怎么和面试官讲清区别?
20. 80 分的项目长什么样, 100 分的还差什么? (自我反思题, 加分)

---

## 简历写法 4 个铁律

1. **不写虚假数字**: W4 跑不出来就不写百分比, 写"完成评测脚本, 待跑批"
2. **不堆术语**: 一次出现 ≤2 个英文框架名, 读者会跳过
3. **每条动词开头**: 实现 / 设计 / 对比 / 搭建, 不要"参与了"
4. **和上一个 RAG 项目讲清区别**: 一个是"检索-生成"RAG, 一个是"决策-编码-执行"多 Agent, 面试官不爱听"也是大模型应用"