import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# GUI
import tkinter as tk
from tkinter import ttk

from es_test import search_es
from ReAct import ReActAgent
from LLM_BASE import HelloAgentsLLM
from TOOL import ToolExecutor

# ----------------- 工具与 Agent 基础配置 -----------------

tool_executor = ToolExecutor()
search_description = (
    "用于在本系统的 Elasticsearch 知识库中检索与用户问题相关的业务文档，"
    "适合在需要“查资料 / 找背景信息 / 补充上下文”时调用。它面向的是已经导入 ES 的各类深度学习知识文档，"
    "包括会议、论文与模型SOTA信息（wp_event、paper、sota）、GPU/LLM 参数配置（gpu、llm）、数据集与教程"
    "（wp_dataset、wp_notebook）、新闻与百科（topic、wp_post、wp_wiki）等。"
    "工具输入是一段自然语言查询或关键字句子，工具会在索引中的 all_text 字段上执行 BM25 关键词检索"
    "（多个词为 OR 关系），返回相关度最高的 Top-K 文档，用于后续回答生成或 RAG 场景的上下文补充。"
)
tool_executor.registerTool("KnowledgeBaseSearch", search_description, search_es)

# 每批最大并发线程数（根据你接口 QPS 和机器情况调）
MAX_WORKERS = 8


# ----------------- 通用加载函数 -----------------

def load_questions(input_path: str):
    """从 txt 或 json 文件加载问题列表，一行/一条一个问题"""
    questions = []
    if input_path.endswith(".json"):
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                questions = [
                    q if isinstance(q, str) else q.get("question")
                    for q in data
                ]
            elif isinstance(data, dict):
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
    else:
        raise ValueError(f"Unsupported file type: {input_path}")
    questions = [q for q in questions if q]
    return questions


# ----------------- 单条问题的并行处理逻辑 -----------------
import time

def safe_process_single_question(*args, max_seconds=180, **kwargs):
    """
    在单独线程中执行 process_single_question，如果超过 max_seconds 还没返回，
    就认为 TIMEOUT，返回一个特殊结构。
    """
    result_container = {}
    exc_container = {}

    def target():
        try:
            result_container["value"] = process_single_question(*args, **kwargs)
        except Exception as e:
            exc_container["error"] = e

    t = threading.Thread(target=target)
    t.daemon = True
    start = time.time()
    t.start()
    t.join(timeout=max_seconds)

    if t.is_alive():
        # 超时：构造一个 TIMEOUT 的结果
        test_id, idx, question, gt_should_call = args
        timeout_md = []
        timeout_md.append(f"### Question {idx}: {question}\n")
        timeout_md.append(f"- **Ground Truth Should Call Tool:** {gt_should_call}")
        timeout_md.append(f"- **Predicted Should Call Tool:** TIMEOUT")
        timeout_md.append(f"- **Tools Used:** None\n")
        timeout_md.append("**Steps:**\n")
        timeout_md.append("1. **Thought:** TIMEOUT（该样本在设定时间内未完成）")
        timeout_md.append("   - **Action:** None")
        timeout_md.append("   - **Final Answer:** TIMEOUT\n")
        timeout_md.append("\n---\n")

        return {
            "idx": idx,
            "correct": 0,
            "md": "\n".join(timeout_md),
        }

    if "error" in exc_container:
        # 把异常也转成一个“错误样本”
        test_id, idx, question, gt_should_call = args
        err = exc_container["error"]
        err_md = []
        err_md.append(f"### Question {idx}: {question}\n")
        err_md.append(f"- **Ground Truth Should Call Tool:** {gt_should_call}")
        err_md.append(f"- **Predicted Should Call Tool:** ERROR")
        err_md.append(f"- **Tools Used:** None\n")
        err_md.append("**Steps:**\n")
        err_md.append(f"1. **Thought:** ERROR（异常：{err}）")
        err_md.append("   - **Action:** None")
        err_md.append("   - **Final Answer:** ERROR\n")
        err_md.append("\n---\n")

        return {
            "idx": idx,
            "correct": 0,
            "md": "\n".join(err_md),
        }

    # 正常返回
    return result_container.get("value")

def process_single_question(test_id: int, idx: int, question: str, gt_should_call: bool):
    """
    并行 worker：处理一条问题，返回
    - idx: 问题序号
    - correct: 当前样本意图是否预测正确 (0/1)
    - md: 该问题对应的 Markdown 日志片段
    """
    # 为避免线程之间状态共享，每个问题独立创建 LLM 和 Agent
    llm_client = HelloAgentsLLM()
    agent = ReActAgent(llm_client, tool_executor)

    agent.clear_memory()
    _ = agent.run(question)
    steps = agent.step_log  # ReActAgent 在 run 中填充的 step 级日志

    # 统计本轮使用过的工具（不包含 Finish）
    used_tools = []
    for step in steps:
        act = (step.get("action") or "").strip()
        # 约定：工具步一定有 observation，Finish 步没有 observation
        if act and act != "Finish" and step.get("observation"):
            used_tools.append(act)
    used_tools = list(set(used_tools))  # 去重

    # 意图预测：是否调用过任意工具
    predicted_should_call = len(used_tools) > 0
    is_correct = int(predicted_should_call == gt_should_call)

    # 生成 Markdown 日志
    md_lines = []
    md_lines.append(f"### Question {idx}: {question}\n")
    md_lines.append(f"- **Ground Truth Should Call Tool:** {gt_should_call}")
    md_lines.append(f"- **Predicted Should Call Tool:** {predicted_should_call}")
    md_lines.append(f"- **Tools Used:** {used_tools or 'None'}\n")
    md_lines.append("**Steps:**")

    for i, step in enumerate(steps, 1):
        thought = step.get("thought", "")
        action = step.get("action", "")
        action_input = step.get("action_input", "")
        final_answer_step = step.get("final_answer", "")
        observation = step.get("observation", "")

        md_lines.append(f"\n{i}. **Thought:** {thought}")
        md_lines.append(f"   - **Action:** {action}")
        if action_input:
            md_lines.append(f"   - **Action Input:** {action_input}")
        if observation:
            md_lines.append(f"   - **Observation:** {observation}")
        if final_answer_step:
            md_lines.append(f"   - **Final Answer:** {final_answer_step}")

    md_lines.append("\n---\n")

    return {
        "idx": idx,
        "correct": is_correct,
        "md": "\n".join(md_lines),
    }


# ----------------- 测试集配置 -----------------

test_sets = [
    {
        "id": 1,
        "file": "question1.txt",
        "should_call_tool": True,   # question1：数据库内问题 → 应调用工具
    },
    {
        "id": 2,
        "file": "question2.txt",
        "should_call_tool": True,   # question2：业务相关问题 → 仍希望调用工具
    },
    {
        "id": 3,
        "file": "question3.txt",
        "should_call_tool": False,  # question3：业务无关 → 不希望调用工具
    },
]

# ----------------- 进度 & 结果的全局状态 -----------------

progress_totals = {}      # {test_id: total_num}
progress_completed = {}   # {test_id: done_num}
results_by_test = {}      # {test_id: [result_dict, ...]}
summary_lines = []        # 汇总信息，用于 result.txt
tests_done = False        # 所有测试是否完成

state_lock = threading.Lock()  # 保护 progress_* 和 tests_done


# ----------------- 主测试逻辑（在后台线程中执行） -----------------

def run_all_tests():
    global tests_done

    for cfg in test_sets:
        test_id = cfg["id"]
        file_path = cfg["file"]
        gt_should_call = cfg["should_call_tool"]
        questions = cfg.get("questions", [])

        if not questions:
            summary = (
                f"Test Set {test_id} ({file_path}) - "
                f"Total: 0, Correct: 0, Accuracy: 0.0000"
            )
            print(summary)
            summary_lines.append(summary)
            continue

        # 当前测试集并行处理
        results = []
        with ThreadPoolExecutor(max_workers=(int)(MAX_WORKERS*0.7)) as pool:
            futures = []
            for idx, question in enumerate(questions, 1):
                futures.append(
                    pool.submit(
                        safe_process_single_question, test_id, idx, question, gt_should_call
                    )
                )

            for fut in as_completed(futures):
                r = fut.result()
                results.append(r)
                # 更新进度（由 GUI 定时读取）
                with state_lock:
                    progress_completed[test_id] += 1

        # 排序（保证问题顺序）
        results.sort(key=lambda r: r["idx"])
        results_by_test[test_id] = results

        total = len(results)
        correct = sum(r["correct"] for r in results)
        accuracy = correct / total if total > 0 else 0.0

        # 生成当前测试集的 Markdown 日志
        log_lines = []
        for r in results:
            log_lines.append(r["md"])

        md_filename = f"agent_test_log_{test_id}.md"
        with open(md_filename, "w", encoding="utf-8") as log_file:
            log_file.write("\n".join(log_lines))

        summary = (
            f"Test Set {test_id} ({file_path}) - "
            f"Total: {total}, Correct: {correct}, "
            f"Accuracy: {accuracy:.4f}"
        )
        print(summary)
        summary_lines.append(summary)

    # 所有测试集完成后，写 result.txt
    with open("result.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines))

    print("All tests finished. Summary written to result.txt")
    print("Per-set logs written to agent_test_log_1.md / 2.md / 3.md")

    with state_lock:
        tests_done = True


# ----------------- GUI：弹窗 + 进度条 -----------------

def create_gui():
    root = tk.Tk()
    root.title("RAG Agent Batch Progress")

    progress_bars = {}
    progress_labels = {}

    for cfg in test_sets:
        test_id = cfg["id"]
        file_path = cfg["file"]

        frame = ttk.Frame(root)
        frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame, text=f"{file_path}").pack(anchor="w")

        pb = ttk.Progressbar(frame, orient="horizontal",
                             mode="determinate", length=300, maximum=100)
        pb.pack(fill="x")

        lbl = ttk.Label(frame, text="0/0")
        lbl.pack(anchor="e")

        progress_bars[test_id] = pb
        progress_labels[test_id] = lbl

    def update_progress():
        with state_lock:
            done_flag = tests_done
            # 更新每个测试集的进度条和标签
            for cfg in test_sets:
                test_id = cfg["id"]
                total = progress_totals.get(test_id, 0)
                done = progress_completed.get(test_id, 0)

                if total > 0:
                    ratio = done / total
                    value = int(ratio * 100)
                else:
                    value = 0
                    ratio = 0.0

                pb = progress_bars[test_id]
                lbl = progress_labels[test_id]

                pb["value"] = value
                lbl.config(text=f"{done}/{total}")

        if not done_flag:
            # 还没结束就继续刷新
            root.after(200, update_progress)
        else:
            # 完成后再等一会儿自动关闭窗口
            root.after(2000, root.destroy)

    root.after(200, update_progress)

    return root


# ----------------- main：预加载问题 + 启动 GUI + 后台线程 -----------------

if __name__ == "__main__":
    # 预加载问题，初始化进度数据
    for cfg in test_sets:
        test_id = cfg["id"]
        file_path = cfg["file"]

        questions = load_questions(file_path)
        cfg["questions"] = questions

        with state_lock:
            progress_totals[test_id] = len(questions)
            progress_completed[test_id] = 0
        results_by_test[test_id] = []

    # 创建 GUI
    root = create_gui()

    # 在后台线程中执行所有测试（并行调用 LLM + 工具）
    worker_thread = threading.Thread(target=run_all_tests, daemon=True)
    worker_thread.start()

    # 进入 GUI 主循环（阻塞，直到窗口关闭）
    root.mainloop()

    # GUI 关闭后（tests_done 已设置，result.txt 和 md 也已写完）
    print("GUI closed. All done.")
