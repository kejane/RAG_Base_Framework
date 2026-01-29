import json
from es_test import search_es
from ReAct import ReActAgent
from LLM_BASE import HelloAgentsLLM
from TOOL import ToolExecutor


# 注册工具
executor = ToolExecutor()
search_description = (
    "用于在本系统的 Elasticsearch 知识库中检索与用户问题相关的业务文档，"
    "适合在需要“查资料 / 找背景信息 / 补充上下文”时调用。它面向的是已经导入 ES 的各类深度学习知识文档，"
    "包括会议、论文与模型SOTA信息（wp_event、paper、sota）、GPU/LLM 参数配置（gpu、llm）、数据集与教程"
    "（wp_dataset、wp_notebook）、新闻与百科（topic、wp_post、wp_wiki）等。"
    "工具输入是一段自然语言查询或关键字句子，工具会在索引中的 all_text 字段上执行 BM25 关键词检索"
    "（多个词为 OR 关系），返回相关度最高的 Top-K 文档，用于后续回答生成或 RAG 场景的上下文补充。"
)
executor.registerTool("KnowledgeBaseSearch", search_description, search_es)

# 初始化 Agent
llm_client = HelloAgentsLLM()
agent = ReActAgent(llm_client, executor)

# 读取问题（txt 或 json）
input_path = "questions.txt"  # 或者 "questions.json"
questions = []

if input_path.endswith(".json"):
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, list):
            # JSON 是 list，元素要么是字符串，要么是 {"question": "..."}
            questions = [q if isinstance(q, str) else q.get("question") for q in data]
        elif isinstance(data, dict):
            # JSON 是 dict，把里面的 list 合并
            for _, val in data.items():
                if isinstance(val, list):
                    for item in val:
                        if isinstance(item, str):
                            questions.append(item)
                        elif isinstance(item, dict) and "question" in item:
                            questions.append(item["question"])
elif input_path.endswith(".txt"):
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            q = line.strip()
            if q:
                questions.append(q)

# 批量测试 & 记录日志（Markdown）
log_lines = []
for idx, question in enumerate(questions, 1):
    agent.clear_memory()  # 每个问题独立运行
    answer = agent.run(question)
    steps = agent.step_log  # ReActAgent 在 run 中填充的 step 级日志

    # 统计本轮使用过的工具（不包含 Finish）
    used_tools = []
    for step in steps:
        act = (step.get("action") or "").strip()
        # 约定：工具步一定有 observation，Finish 步没有 observation
        if act and act != "Finish" and step.get("observation"):
            used_tools.append(act)
    used_tools = list(set(used_tools))  # 去重

    # 生成 Markdown 日志
    log_lines.append(f"### Question {idx}: {question}\n")
    log_lines.append("**Steps:**")

    for i, step in enumerate(steps, 1):
        thought = step.get("thought", "")
        action = step.get("action", "")
        action_input = step.get("action_input", "")
        final_answer_step = step.get("final_answer", "")
        observation = step.get("observation", "")

        log_lines.append(f"\n{i}. **Thought:** {thought}")
        log_lines.append(f"   - **Action:** {action}")
        if action_input:
            log_lines.append(f"   - **Action Input:** {action_input}")
        if observation:
            log_lines.append(f"   - **Observation:** {observation}")
        if final_answer_step:
            log_lines.append(f"   - **Final Answer:** {final_answer_step}")

    log_lines.append(f"\n**Tools Used:** {used_tools or 'None'}")
    log_lines.append("\n---\n")

# 写入日志文件
with open("agent_test_log.md", "w", encoding="utf-8") as log_file:
    log_file.write("\n".join(log_lines))

print("Test log written to agent_test_log.md")
