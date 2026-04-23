from pydantic import BaseModel
from openai import OpenAI
from typing import Type, TypeVar
import os

T = TypeVar('T', bound=BaseModel)

def extract_structured_data(context: str, schema: Type[T], max_retries: int = 2) -> T | None:
    client = OpenAI(
        base_url=os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.getenv("OPENAI_API_KEY", "ollama")
    )
    model = os.getenv("LLM_MODEL", "qwen2.5")
    
    # 动态把要求抽取的 schema 拼接到 Prompt 里
    schema_json = schema.model_json_schema()
    prompt = (
        f"You are an expert data extraction assistant. "
        f"Extract information from the provided context and output ONLY valid JSON format.\n"
        f"The JSON MUST perfectly match this JSON Schema:\n{schema_json}\n\n"
        f"Context:\n{context}\n\n"
        f"Remember, your response must contain the word 'json' in some form and be a parsable JSON string."
    )
    
    for attempt in range(max_retries + 1):
        try:
            # 使用最兼容的通用调用方式
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                extra_body={"enable_thinking": False}
                # 兼容阿里的要求，有些模型必须声明 json_object
                # response_format={"type": "json_object"}
            )
            raw_json_str = response.choices[0].message.content
            
            # --- 新增响应清洗逻辑 ---
            # 如果大模型返回带 ```json 或 ``` 的 Markdown 包裹逻辑，进行剥离
            cleaned_json = raw_json_str.strip()
            if cleaned_json.startswith("```"):
                # 寻找第一个换行符之后的内容，直到最后一个 ``` 之前
                lines = cleaned_json.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned_json = "\n".join(lines).strip()
            # ----------------------
            
            # 手动反序列化大返回的纯文本 Json 为 Pydantic 对象
            return schema.model_validate_json(cleaned_json)
        except Exception as e:
            if attempt == max_retries:
                print(f"Failed to extract after {max_retries} retries: {e}")
                return None
    return None
