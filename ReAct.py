import re
from LLM_BASE import HelloAgentsLLM
from TOOL import ToolExecutor
from typing import List, Dict

class ReActAgent:
    def __init__(self, llm_client: HelloAgentsLLM, tool_executor: ToolExecutor, max_steps: int = 5):
        self.llm_client = llm_client
        self.tool_executor = tool_executor
        self.max_steps = max_steps
        # Conversation memory for multi-turn dialogue (list of {'role': ..., 'content': ...} messages)
        self.conversation: List[Dict[str, str]] = []
        # Log of thought/action/observation steps for the current question (for debugging/testing)
        self.step_log: List[Dict[str, str]] = []

    def clear_memory(self):
        """Reset the conversation history for a new session."""
        self.conversation = []
        self.step_log = []

    def run(self, question: str):
        # Reset chain-of-thought history for this query (but keep conversation history)
        self.history = []               # Stores "Action: ..."/"Observation: ..." for prompt context
        self.step_log = []             # Reset step-by-step log for this run
        current_step = 0

        while current_step < self.max_steps:
            current_step += 1
            print(f"--- 第 {current_step} 步 ---")
            # Get tool descriptions and format current execution history
            tools_desc = self.tool_executor.getAvailableTools()
            history_str = "\n".join(self.history)
            # Format conversation history from previous turns (if any)
            if self.conversation:
                convo_lines = []
                for msg in self.conversation:
                    if msg["role"] == "user":
                        convo_lines.append(f"用户: {msg['content']}")
                    elif msg["role"] == "assistant":
                        convo_lines.append(f"助手: {msg['content']}")
                chat_history_str = "\n".join(convo_lines)
            else:
                chat_history_str = ""

            # Build the ReAct prompt with available tools, conversation history, current question, and past steps
            # prompt = (
            #     "你是一个深度学习技术学习网站的问答与对话助手，擅长回答深度学习理论、模型训练实践、GPU/LLM 参数配置、数据集与论文信息、教学教程相关的问题。"
            #     "你可以通过思考分析用户的问题，然后调用合适的工具（例如基于 Elasticsearch 的知识检索工具）来获取本站已有业务文档中的信息，最终给出准确、清晰、可执行的答案。\n\n"
            #     "## 可用工具\n"
            #     f"{tools_desc}\n\n"
            #     "## 工作流程\n"
            #     "请严格按照以下格式进行回应，每次只能执行一个步骤:\n\n"
            #     "Thought: 分析当前问题，思考需要什么信息或采取什么行动（例如：需要查哪类索引：会议/论文、GPU、LLM、数据集、教程、百科等）。\n"
            #     "Action: 选择一个行动，格式必须是以下之一:\n"
            #     "- `{{tool_name}}[{{tool_input}}]` - 调用指定工具（调用知识库检索工具对 all_text 字段做关键词检索）\n"
            #     "- `Finish[最终答案]` - 当你有足够信息给出最终答案时\n\n"
            #     "## 重要提醒\n"
            #     "1. 每次回应必须包含 Thought 和 Action 两部分，Action 后面可以是工具调用也可以是 Finish，需严格按照上面格式。\n"
            #     "2. 工具调用的格式必须严格遵循：工具名[参数]，参数中要包含清晰的检索意图（如关键术语、模型名、GPU 型号、任务类型等）。\n"
            #     "3. 只有当你确信已经从工具结果中获得了足够且可信的业务信息，能够回答用户问题时，才使用 Finish 输出最终答案。\n"
            #     "4. 如果工具返回的信息不够或偏离问题焦点，可以调整检索关键词或索引范围，继续使用相同工具或其他工具获取补充信息，然后再回答。\n"
            #     "5. 当问题与本站业务知识密切相关（例如：深度学习基础概念与公式、具体 GPU/LLM 配置对比、某个任务的 SOTA 情况、某篇论文/会议/数据集介绍、某篇教程的具体步骤等）时，优先调用 KnowledgeBaseSearch 等检索工具，从已有 JSON/ES 索引中检索相关文档，然后基于检索结果进行总结与归纳。\n"
            #     "6. 当问题与深度学习及相关 AI 技术无关时，请先判断该问题是否为一般常识性问题：\n"
            #     "   - 如果是一般常识且你有把握，可以直接回答；\n"
            #     "   - 如果与本站业务完全无关且不是常识性问题，则将“抱歉，我无法回答该问题，这超出了本站深度学习知识范围。”视为最终答案，并使用 Finish 输出。\n"
            #     "7. 回答与本站业务相关的问题时，要尽可能引用和整合工具返回的文档内容（例如教程步骤、论文摘要、GPU/LLM 关键参数、数据集描述等），用你自己的话做结构化总结，而不是简单复制原文。\n"
            # )
            prompt = (
                "你是一个深度学习技术学习网站的问答与对话助手，擅长回答深度学习理论、模型训练实践、GPU/LLM 参数配置、数据集与论文信息、教学教程相关的问题。"
                "你会先分析用户问题，必要时调用工具（例如基于 Elasticsearch 的知识检索工具）从本站业务文档中检索信息，然后给出准确、清晰、可执行的答案。\n\n"
                "## 可用工具\n"
                f"{tools_desc}\n\n"
                "## 输出协议（必须严格遵守）\n"
                "你每次回复只能执行一个步骤，要么是工具步骤，要么是结束步骤，并且步骤必须严格按照以下格式输出（使用英文冒号 ':'，不要使用中文冒号 '：'）：\n\n"
                "   - 若选择调用工具，回复格式如下：\n"
                "Thought: <你的分析与下一步计划>  （例如：需要查哪类索引：会议/论文、GPU、LLM、数据集、教程、百科等） \n"
                "Action: <tool_name>           （tool_name 必须来自“可用工具”列表，且大小写完全一致）\n"
                "Action Input: <tool_input>    （必须单行；写清楚检索意图/关键词/限定条件）\n\n"
                "   - 若选择结束，回复格式如下：\n"
                "Thought: <为什么现在可以结束>\n"
                "Action: Finish\n"
                "Final Answer: <最终答案，可多行；必须是整个输出的最后一部分>\n\n"
                "## 重要提醒（高优先级）\n"
                "1) 除上述字段外，不要输出任何其它内容（不要解释格式、不要加标题、不要使用 Markdown、不要用代码块、不要加反引号）。\n"
                "2) 工具步骤中：Action Input 必须是单行文本；不要换行、不要写成 JSON、不要加多余括号。\n"
                "3) 结束步骤中：必须同时出现 Action: Finish 与 Final Answer:；Final Answer 之后不得再输出任何字符或字段。\n"
                "4) 当问题与本站业务知识密切相关时，优先使用检索工具获取依据，再总结作答。\n"
                "5) 若问题与本站业务无关：\n"
                "   - 若属于简单常识且你有把握，可直接结束并给 Final Answer；\n"
                "   - 否则用结束步骤输出：抱歉，我无法回答该问题，这超出了本站深度学习知识范围。\n\n"
                "## 示例（只用于学习格式，不要复述）\n"
                "示例A（工具步骤）：\n"
                "Thought: 用户问的是 GRPO 的定义和与 PPO 区别，我需要检索本站的 RLHF/对齐文档。\n"
                "Action: KnowledgeBaseSearch\n"
                "Action Input: GRPO 与 PPO 区别 目标函数 训练流程\n\n"
                "示例B（结束步骤）：\n"
                "Thought: 已从检索结果得到定义、优势与适用条件，可以直接组织回答。\n"
                "Action: Finish\n"
                "Final Answer: GRPO 是……（此处省略）\n"
            )

            if chat_history_str:
                prompt += f"## 对话历史\n{chat_history_str}\n"
            prompt += (
                "## 当前任务\n"
                f"**Question:** {question}\n\n"
                "## 执行历史\n"
                f"{history_str}\n"
                "现在开始你的推理和行动:"
            )

            # Call the LLM with the composed prompt
            messages = [{"role": "user", "content": prompt}]
            response = self.llm_client.think(messages)
            if response is None:
                print("LLM 返回了空响应，终止。")
                break

            # Parse the LLM output to extract Thought and Action
            # thought, action = self._parse_output(response)
            # if thought:
            #     print(f"Thought: {thought}")
            # if not action:
            #     print("未能解析到 Action，终止。")
            #     break
            # if action.startswith("Finish"):
            #     m = re.match(r"Finish\[(.*)\]\s*$", action, flags=re.DOTALL)
            #     final_answer = (m.group(1).strip() if m else action[len("Finish["):].rstrip("]").strip())

            # # If the model decides to finish with an answer
            # # if action.startswith("Finish"):
            # #     # Extract the final answer from Finish[...] 
            # #     match = re.match(r"Finish\[(.*)\]", action)
            # #     final_answer = match.group(1) if match else ""
            #     print(f"Final Answer: {final_answer}")
            #     # Log this final step (thought and finish action) in the step-by-step log
            #     step_entry = {"action": action}
            #     if thought:
            #         step_entry["thought"] = thought
            #     self.step_log.append(step_entry)
            #     # Append the user question and final answer to conversation memory
            #     self.conversation.append({"role": "user", "content": question})
            #     self.conversation.append({"role": "assistant", "content": final_answer})
            #     return final_answer

            # # Otherwise, parse the tool name and input from the Action
            # tool_name, tool_input = self._parse_action(action)
            # ------------------------以上是旧版解析--------------------------------
            # ------------------------稳健解析start--------------------------------
            parsed = self._parse_step(response)
            thought = parsed.get("thought")
            action = parsed.get("action")
            action_input = parsed.get("action_input")
            final_answer = parsed.get("final_answer")

            if thought:
                print(f"Thought: {thought}")
            if not action:
                print("未能解析到 Action，终止。")
                break

            # Finish
            if action == "Finish":
                print(f"Final Answer: {final_answer}")
                step_entry = {"action": "Finish", "final_answer": final_answer}
                if thought:
                    step_entry["thought"] = thought
                self.step_log.append(step_entry)

                self.conversation.append({"role": "user", "content": question})
                self.conversation.append({"role": "assistant", "content": final_answer})
                return final_answer

            # Tool step
            tool_name = action
            tool_input = action_input
            if not tool_input:
                print("解析到工具但缺少 Action Input，终止。")
                break

            print(f"行动：{tool_name} | Action Input: {tool_input}")
            tool_func = self.tool_executor.getTool(tool_name)
            observation = tool_func(tool_input) if tool_func else f"工具 {tool_name} 未找到。"
            print(f"Observation: {observation}")

            # 建议把 Action Input 写入 history（否则下一轮模型看不到它当时搜了什么）
            self.history.append(f"Thought: {thought}" if thought else "Thought: ")
            self.history.append(f"Action: {tool_name}")
            self.history.append(f"Action Input: {tool_input}")
            self.history.append(f"Observation: {observation}")

            step_entry = {"thought": thought, "action": tool_name, "action_input": tool_input, "observation": observation}
            self.step_log.append(step_entry)
            # --------------------稳健解析end------------------------

            if not tool_name or tool_input is None:
                # If action format is not recognized, skip this step
                continue
            print(f"行动：{tool_name}[{tool_input}]")
            print(f"Observation: {observation}")

            # Append this action and observation to history for the next step's prompt
            self.history.append(f"Action: {action}")
            self.history.append(f"Observation: {observation}")
            # Log this step in detail for debugging/testing
            step_entry = {"action": action, "observation": observation}
            if thought:
                step_entry["thought"] = thought
            self.step_log.append(step_entry)

        print("达到最大步骤数，终止。")
        return None



    def _parse_output(self, text: str):
        _THOUGHT_RE = re.compile(r"^\s*Thought\s*[:：]\s*(.*)\s*$", re.MULTILINE)
        _ACTION_RE  = re.compile(r"^\s*Action\s*[:：]\s*(.*)\s*$",  re.MULTILINE)
        text = text.strip()

        thoughts = _THOUGHT_RE.findall(text)
        thought = thoughts[-1].strip() if thoughts else None  # 取最后一个 Thought

        action_matches = list(_ACTION_RE.finditer(text))
        if not action_matches:
            return thought, None

        # 取最后一个 Action: 行
        last = action_matches[-1]
        action_line = last.group(1).strip().strip("`")  # 兼容模型输出反引号

        # 如果是 Finish，但这一行没闭合 ]，则从原始输出里做跨行提取兜底
        if action_line.startswith("Finish[") and "]" not in action_line:
            m = re.search(r"Action\s*[:：]\s*Finish\[(.*)\]\s*$", text, flags=re.DOTALL)
            if m:
                action_line = "Finish[" + m.group(1).strip() + "]"
            else:
                # 兜底：把 Action: 后面的所有内容当作答案（避免返回空串）
                action_line = "Finish[" + text[last.end():].strip() + "]"

        return thought, action_line
    
    # 新的模板解析器
    def _parse_step(self, text: str):
        """
        Parse one model step under the new protocol:
        - Tool step:
            Thought: ...
            Action: <tool_name>
            Action Input: <single line>
        - Finish step:
            Thought: ...
            Action: Finish
            Final Answer: <multi-line until end>
        Returns dict: {thought, action, action_input, final_answer}
        """
        if not text:
            return None

        text = text.replace("\r\n", "\n").strip()

        THOUGHT_RE = re.compile(r"^\s*Thought\s*[:：]\s*(.*)\s*$", re.MULTILINE)
        ACTION_RE  = re.compile(r"^\s*Action\s*[:：]\s*(.*)\s*$",  re.MULTILINE)
        AIN_RE     = re.compile(r"^\s*Action Input\s*[:：]\s*(.*)\s*$", re.MULTILINE)

        thoughts = THOUGHT_RE.findall(text)
        thought = thoughts[-1].strip() if thoughts else None

        actions = ACTION_RE.findall(text)
        action = actions[-1].strip().strip("`") if actions else None
        if not action:
            return {"thought": thought, "action": None, "action_input": None, "final_answer": None}

        # Finish step: Action: Finish + Final Answer: (multi-line to end)
        if action.lower() == "finish":
            m = re.search(r"^\s*Final Answer\s*[:：]\s*([\s\S]*)\Z", text, flags=re.MULTILINE)
            final_answer = m.group(1).strip() if m else ""
            return {"thought": thought, "action": "Finish", "action_input": None, "final_answer": final_answer}

        # Tool step: Action Input is required (prefer last one)
        ains = AIN_RE.findall(text)
        action_input = ains[-1].strip().strip("`") if ains else None
        return {"thought": thought, "action": action, "action_input": action_input, "final_answer": None}


    def _parse_action(self, action_text: str):
        """Parse the action string to get the tool name and its input."""
        match = re.match(r"(\w+)\[(.*)\]", action_text)
        if match:
            return match.group(1), match.group(2)
        return None, None
