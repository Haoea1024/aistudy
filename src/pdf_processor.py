import pdfplumber
from pdf2image import convert_from_path
import pytesseract

from typing import Set

def extract_content(pdf_path: str, target_pages: Set[int] | None = None, page_type: str = "both") -> str:
    combined_content = []
    
    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages
        
        for i, page in enumerate(pages):
            page_num = i + 1
            
            # 若配置了指定页且当前页不在其内，跳过
            if target_pages is not None and page_num not in target_pages:
                continue
                
            text = ""
            if page_type in ["text", "both"]:
                text = page.extract_text() or ""
                
            if page_type == "text":
                if text and len(text.strip()) > 50:
                    combined_content.append(f"--- Page {page_num} (Text) ---\n{text}")
                else:
                    images = convert_from_path(pdf_path, first_page=page_num, last_page=page_num)
                    for img in images:
                        ocr_text = pytesseract.image_to_string(img)
                        combined_content.append(f"--- Page {page_num} (Scanned Text) ---\n{ocr_text}")
                        
            elif page_type == "table":
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        table_str = "\n".join([" | ".join([str(c) if c else "" for c in row]) for row in table])
                        combined_content.append(f"--- Page {page_num} (Table) ---\nTable Data:\n{table_str}")
                        
            elif page_type == "both":
                if text and len(text.strip()) > 50:
                    combined_content.append(f"--- Page {page_num} ---\n{text}")
                    tables = page.extract_tables()
                    if tables:
                        for table in tables:
                            table_str = "\n".join([" | ".join([str(c) if c else "" for c in row]) for row in table])
                            combined_content.append(f"Table Data:\n{table_str}")
                else:
                    images = convert_from_path(pdf_path, first_page=page_num, last_page=page_num)
                    for img in images:
                        ocr_text = pytesseract.image_to_string(img)
                        combined_content.append(f"--- Page {page_num} (Scanned) ---\n{ocr_text}")
                    
    return "\n".join(combined_content)
