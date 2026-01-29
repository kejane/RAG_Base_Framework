from typing import Any, Dict, List, Optional

class ToolExecutor:
    def __init__(self):
        self.tools: Dict[str, Dict[str, Any]] = {}

    def registerTool(self, name: str, description: str, func: callable):
        if name in self.tools:
            raise ValueError(f"Tool with name {name} is already registered.")
        self.tools[name] = {"description": description, "func": func}
        print(f"Registered tool: {name}")

    def getTool(self, name: str) -> callable:
        return self.tools.get(name, {}).get("func")

    def getAvailableTools(self) -> str:
        '''
        Returns a formatted string listing all available tools with their descriptions.
        '''
        return "\n".join([f"- {name}: {info['description']}" for name, info in self.tools.items()])


if __name__ == "__main__":
    from es_test import search_es
    from ReAct import ReActAgent
    from LLM_BASE import HelloAgentsLLM

    executor = ToolExecutor()
    search_description = " 用于在本系统的 Elasticsearch 知识库中检索与用户问题相关的业务文档，适合在需要“查资料 / 找背景信息 / 补充上下文”时调用。它面向的是已经导入 ES 的各类深度学习知识文档，包括会议与论文信息（wp_event、paper、sota）、GPU/LLM 参数配置（gpu、llm）、数据集与教程（wp_dataset、wp_notebook）、新闻与百科（topic、wp_post、wp_wiki）等。工具输入是一段自然语言查询或关键字句子，工具会在索引中的 all_text 字段上执行 BM25 关键词检索（多个词为 OR 关系），返回相关度最高的 Top-K 文档，用于后续回答生成或 RAG 场景的上下文补充。"
    executor.registerTool("KnowledgeBaseSearch", search_description, search_es)

    # 测试调用
    llmClient = HelloAgentsLLM()
    ReActAgent(llmClient, executor).run("证明一下勾股定理，并画图说明") #自行推理出月的指代，自行选定了调用本地知识库，输入选词“夜神月 父亲”
    #ReActAgent(llmClient, executor).run("《巨人》中里维是谁？")
    #ReActAgent(llmClient, executor).run("《巨人》中里维的身体怎么样?") #自行推理出巨人的指代，里维的指代，选定了调用本地知识库，输入选词“进击的巨人》 里维·耶格尔 身体状况” 嵌入模型能识别对应到残疾位置