# AssistantAgent 源码地图

源码路径: `D:\miniconda\envs\agent_proj\Lib\site-packages\autogen_agentchat\agents\_assistant_agent.py`
共 619 行, 不用全读, 只读下面标的关键行。

## 关键行速查

| 行号 | 内容 | 你要带走什么 |
|---|---|---|
| 58-72 | `AssistantAgentConfig` dataclass | 知道 Agent 官方支持的配置参数 |
| 70 | `system_message: str \| None` | system_message 默认 None, 不传不报错 |
| 74 | `class AssistantAgent` | 类入口, 继承 `BaseChatAgent` |
| 105-106 | reflect_on_tool_use 文档 | True/False 的行为差异(最常被问) |
| 275-308 | `__init__` | 看懂每个参数怎么存内部状态 |
| 302-308 | `_system_messages` | system_message 包成 SystemMessage 列表 |
| 369 | `on_messages` | 同步入口, 内部 delegate 给 on_messages_stream |
| **375** | **`on_messages_stream` 核心** | 工具调用循环核心, 重点读 |
| 401 | `_get_compatible_context` | system message 怎么拼到 LLM 请求里 |
| 493-546 | 工具执行分支 | reflect_on_tool_use=True 时怎么再调一次 LLM |
| **546** | **`_execute_tool_call`** | 工具具体怎么执行(同步/异步都支持) |
| 563 | `on_reset` | state 怎么清空 |
| 578 | `_get_compatible_context` | LLMMessage 适配不同模型 provider |
| 585-617 | `_to_config / _from_config` | 序列化/反序列化(简历可讲"组件可序列化") |

## 你读源码时打开这个文件, 从 375 开始聚焦读

350-560 这段是 Agent 的核心循环。读完你能回答:
- 一次 on_messages_stream 调用, 最多会循环多少次? (取决于模型返回几次 tool_calls)
- system_message 是每次都拼上下文还是只在第一次?
- 工具调用结果用 ToolCallExecutionResult 还是 ModelClientStreamingChunkEvent?

## 末尾留笔记的几个填空

读完在 docs/w1_AssistantAgent.md 里答出来:

1. system_message 注入时机: [你答]
2. 工具 schema 生成在哪个类: [你答]  (提示: 不在这个文件, 在 base_chat_agent 或 tools 模块, 顺追过去)
3. reflect_on_tool_use=False 时, tool 返回什么消息类型: [ToolCallSummaryMessage]
4. 你画的循环状态图(ASCII 即可): [你画]
5. 你项目里 4 个 Agent 哪个该开 reflect_on_tool_use=True? 为什么? [你答]