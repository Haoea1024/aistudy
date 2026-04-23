import os
import glob
from tqdm import tqdm
from pydantic import create_model, Field
from typing import List, Set, Union, Dict

from .pdf_processor import extract_content
from .llm_extractor import extract_structured_data

def get_dynamic_schema(fields: List[Union[str, Dict]]):
    annotations = {}
    for f in fields:
        if isinstance(f, str):
            annotations[f] = (str, ...)
        elif isinstance(f, dict):
            name = f.get("name")
            desc = f.get("description", "")
            if name:
                annotations[name] = (str, Field(description=desc))
    
    if not annotations:
        annotations["content"] = (str, ...)
    return create_model("RuleSchema", **annotations)

def parse_pages(page_val) -> Set[int]:
    if isinstance(page_val, int):
        return {page_val}
    if isinstance(page_val, str):
        if "-" in page_val:
            try:
                start, end = map(int, page_val.split("-"))
                return set(range(start, end + 1))
            except ValueError:
                pass
        elif page_val.isdigit():
            return {int(page_val)}
    return set()

def process_directory(directory: str, page_settings: List[dict] | None = None) -> List[dict]:
    pdf_files = glob.glob(os.path.join(directory, "*.pdf"))
    results = []
    
    for pdf in tqdm(pdf_files, desc="Processing PDFs"):
        try:
            pdf_result = {}
            if page_settings:
                for rule in page_settings:
                    target_pages = parse_pages(rule.get("page", 0))
                    page_type = rule.get("type", "both")
                    fields = rule.get("fields", [])
                    
                    content = extract_content(pdf, target_pages, page_type)
                    schema = get_dynamic_schema(fields)
                    
                    data = extract_structured_data(content, schema)
                    if data:
                        pdf_result.update(data.model_dump())
            else:
                content = extract_content(pdf, None, "both")
                schema = get_dynamic_schema(["content"])
                data = extract_structured_data(content, schema)
                if data:
                    pdf_result.update(data.model_dump())
                    
            if pdf_result:
                results.append(pdf_result)
        except Exception as e:
            print(f"Error processing {pdf}: {e}")
            
    return results
