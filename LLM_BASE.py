import os
from openai import OpenAI
from dotenv import load_dotenv
from typing import List, Dict

# Load environment variables from .env file
load_dotenv()

class HelloAgentsLLM:
    def __init__(self, model: str = None, apiKey: str = None, base_url: str = None, timeout: int = None):
        self.model = model or os.getenv("LLM_MODEL_ID")
        apiKey = apiKey or os.getenv("LLM_API_KEY")
        base_url = base_url or os.getenv("LLM_BASE_URL", "http://127.0.0.1:80/v1")
        timeout = timeout or int(os.getenv("LLM_TIMEOUT", "60"))  # default timeout in milliseconds

        if not all([self.model, apiKey, base_url]):
            raise ValueError("Model, API Key, and Base URL must be provided either as arguments or environment variables.")
        
        self.client = OpenAI(api_key=apiKey, base_url=base_url, timeout=timeout)

    def think(self, messages: List[Dict[str, str]], temperature: float = 0) -> str:
        print(f"[LLM] Thinking with model: {self.model}, temperature: {temperature}...")
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                stream=True,
            )
            print("[LLM] Thought complete.")
            collected_content = []
            for chunk in response:
                content = chunk.choices[0].delta.content or ""
                print(content, end="", flush=True)
                collected_content.append(content)   
            print()  # for newline after streaming
            return "".join(collected_content)
        except Exception as e:
            print(f"[LLM] Error during api call: {e}")
            return None

if __name__ == "__main__":
    llmClient = HelloAgentsLLM()
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"}
    ]
    response = llmClient.think(messages, temperature=0.7)
    if response:
        print("\n\n--- Final Response ---")
        print(response)
    