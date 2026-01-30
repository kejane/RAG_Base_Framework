# RAG Base Framework

一个简洁的 RAG/ReAct Agent 示例工程，围绕深度学习知识库进行检索与回答。项目通过 `ToolExecutor` 注册 Elasticsearch 检索工具，并由 `ReActAgent` 以“Thought / Action / Observation”流程执行工具调用，最终输出回答。适合作为本地知识库检索与问答代理的最小可用基线。

## 目录结构

- `ReAct.py`：ReAct Agent 核心逻辑与输出协议解析。
- `TOOL.py`：工具注册与调用的执行器。
- `LLM_BASE.py`：LLM 客户端封装（OpenAI 兼容接口）。
- `es_test.py`：Elasticsearch 检索工具（BM25）。
- `run_rag_agent.py`：单批问题运行与日志输出。
- `run_agent_batch.py`：带 GUI 的批量测试与评测。
- `question1.txt` / `question2.txt` / `question3.txt`：示例问题集。
- `agent_test_log_*.md` / `result.txt`：批测输出。

## 运行前准备

### 依赖

- Python 3.9+
- Elasticsearch（本地默认 `http://localhost:9200`）
- OpenAI 兼容 API（本地/远程均可）

### 环境变量

`LLM_BASE.py` 会从环境变量读取配置：

- `LLM_MODEL_ID`：模型名称
- `LLM_API_KEY`：API Key
- `LLM_BASE_URL`：OpenAI 兼容 API 地址（默认 `http://127.0.0.1:80/v1`）
- `LLM_TIMEOUT`：请求超时（秒，默认 60）

可使用 `.env` 文件加载，例如：

```bash
LLM_MODEL_ID=your-model
LLM_API_KEY=your-key
LLM_BASE_URL=http://127.0.0.1:8000/v1
LLM_TIMEOUT=60
```

### Elasticsearch 索引

`es_test.py` 默认检索以下索引：

```
wp_event,gpu,llm,paper,sota,topic,wp_dataset,wp_notebook,wp_post,wp_wiki
```

请确认这些索引存在，且包含 `all_text` 字段，否则检索会失败。

## 使用方式

### 1. 单批运行（生成 Markdown 日志）

`run_rag_agent.py` 会读取 `questions.txt`（或 JSON 文件），执行 ReAct 推理并写入 `agent_test_log.md`。

```bash
python run_rag_agent.py
```

可以在脚本中修改 `input_path` 指向你的问题文件。

### 2. 批量评测（带 GUI）

`run_agent_batch.py` 会并行处理多组问题集，生成每组日志与汇总结果：

```bash
python run_agent_batch.py
```

输出文件：

- `agent_test_log_1.md` / `agent_test_log_2.md` / `agent_test_log_3.md`
- `result.txt`

## 输出协议与解析

`ReAct.py` 通过严格的文本协议解析模型输出：

- 工具步骤：
  - `Thought: ...`
  - `Action: <tool_name>`
  - `Action Input: <single line>`
- 结束步骤：
  - `Thought: ...`
  - `Action: Finish`
  - `Final Answer: ...`

如果工具步骤缺少 `Action Input` 或无法解析 `Action`，执行会中止。

## 常见问题

- **工具调用失败或返回空结果**：确认 ES 地址、索引名与字段是否正确；必要时调整 `es_test.py` 中的 `ES_HOST` 与 `INDICES`。
- **LLM 无响应**：检查环境变量、网络访问与模型服务端可用性。

## 扩展思路

- 在 `TOOL.py` 中注册更多工具（例如向量检索、数据库查询）。
- 在 `ReAct.py` 中完善多轮对话记忆或步骤控制逻辑。
- 在 `run_agent_batch.py` 中增加更细粒度的评测指标。
