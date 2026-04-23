该项目实现了将pdf通过ai提取数据后通过规则引擎转换为json数据


### 1. 安装依赖
```bash
uv sync 
```

### 2. 配置你的提取规则
编辑：`config.toml` 


### 3. 运行程序
准备好 PDF 文件后，直接执行：
```bash
uv run main.py
```
程序将自动扫描 `pdfs` 中的所有 PDF，按定义的规则分层提取并将最终结果聚合到 `output`中。

## 📁 项目结构
- `main.py`: 项目入口，加载配置并分发任务。
- `src/batch_runner.py`: 负责 PDF 文件扫描、页码切分与并发调度。
- `src/pdf_processor.py`: PDF 解析核心，集成 pdfplumber 提取与 Tesseract OCR 视觉 fallback。
- `src/llm_extractor.py`: 负责 Prompt 构建、JSON Schema 生成及 LLM 交互。
- `config.toml`: 全局唯一的规则配置中心。

