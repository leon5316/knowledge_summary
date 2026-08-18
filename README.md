# 知识总结与拓扑内核 (knowledge-summary)

一个基于 Python 的**知识总结与拓扑内核**：解析多种文件格式（SQL / PDF / DOC / DOCX / TXT / Python / HTML / Notebook / CSV / JSON 等）或整个项目文件夹，生成一份**可供 LLM 直接阅读的知识库**，其中既包含分层摘要（总体理解），也包含**定位索引**（每个实体 / 关键词都能指回源文件的精确行号或页码）。

## 特性

- **多格式解析**：`.py` `.sql` `.pdf` `.doc` `.docx` `.txt` `.md` `.rst` `.html` `.ipynb` `.csv` `.tsv` `.json` `.jsonl` `.log` 等，注册表式架构，易扩展。
- **项目文件夹总结**：递归扫描 + 忽略规则（`.git`、`node_modules`、`__pycache__`、输出目录自身等）+ 大小限制。
- **双通道拓扑**：
  - 静态分析（无需 LLM）：Python 用 AST 提取函数 / 类 / 导入 / 继承 / 调用关系；SQL 用语句解析提取表 / 列 / 视图 / 索引 / 外键 / 读取关系。
  - LLM 通道：从文本中补全语义实体与关系（concept / api / business_object 等）。
- **可配置 LLM 内核**：`openai_compatible`（DeepSeek / OpenAI / vLLM 等任意兼容服务）、`ollama`（本地）、`anthropic`、`none`（离线静态模式，不调用任何 LLM）。
- **全部配置集中**在 `default_config.yaml`，可用用户配置文件覆盖，API Key 只从环境变量读取。
- **输出位置**：在被总结内容所在目录下生成 `<源目录>/knowledge/`，绝不修改源文件。

## 安装

```bash
pip install -r requirements.txt        # 核心依赖
# 可选: pdfminer.six（PDF 备用解析器）、anthropic（Claude 提供方）
```

## 快速开始

```bash
# 总结当前目录（离线静态模式，无需任何 LLM）
python main.py . --provider none

# 总结单个文件
python main.py ./report.pdf

# 总结整个项目，使用默认 openai_compatible（需设置 base_url / API Key）
python main.py ./src

# 使用自定义配置文件
python main.py ./src --config my_config.yaml

# 查看解析后的配置（脱敏）
python main.py --show-config
```

LLM 调用示例（DeepSeek）：

```bash
export LLM_API_KEY=sk-xxx
python main.py ./src --provider openai_compatible --model deepseek-chat \
    --base-url https://api.deepseek.com/v1
```

本地 Ollama：

```bash
python main.py ./src --provider ollama --model qwen2.5:7b
```

## 输出结构（`<源目录>/knowledge/`）

| 文件 | 内容 |
|---|---|
| `00_README.md` | 给未来 LLM 的"使用手册"：推荐阅读顺序与回答流程 |
| `01_overview.md` | 全局总览：主题、模块职责、实体关系图谱（文本版） |
| `02_summary.md` | 分层摘要：全局 → 文件级 → 块级 |
| `03_topology.json` | 结构化实体 / 关系图谱（每条带来源指针） |
| `04_locate_index.json` | 定位索引：实体名 / 关键词 → `file` + `line_start~line_end`（或页码）+ 摘录 + 块 ID |
| `chunks/` 或 `chunks_bundle.md` | 分块原文 + 块摘要 |
| `manifest.json` | 生成元信息、配置指纹（用于判断知识库是否过期）、统计 |

**给 LLM 的使用路径**：先读 `01_overview.md` 总体理解 → 针对问题查 `04_locate_index.json` 定位 → 按指针回源文件精读。

## 配置

所有可配置项见 [default_config.yaml](default_config.yaml)，主要分组：

- `general`：输出目录名、忽略规则、大小限制、未知扩展名处理
- `llm`：provider / model / base_url / api_key_env / temperature / 并发 / 重试 / 失败降级
- `chunking`：块大小、重叠、语义边界
- `summarization`：摘要层级、语言
- `extractors`：各格式解析选项（pdf 解析器选择、doc 工具选择等）
- `topology`：静态分析 / LLM 关系 / 关键词概念开关
- `locate_index`：摘录长度、关键词数量
- `storage`：chunks 写入策略

用户配置示例 `my_config.yaml`（默认已生成英文总结，如需中文可覆盖）：

```yaml
llm:
  provider: ollama
  model: qwen2.5:7b
chunking:
  max_chunk_chars: 6000
summarization:
  languages: [zh]      # 默认 [en] 生成英文总结；改为 [zh] 生成中文
topology:
  include_keywords_as_concepts: false
```

## 开发

```bash
python -m pytest tests/          # 运行测试套件
```

## 目录结构

```
knowledge_summary/
├── default_config.yaml      # 所有可配置项（单一入口）
├── main.py                  # CLI 入口
├── knowledge_summary/       # 内核包
│   ├── config.py            # 配置加载/合并/指纹
│   ├── pipeline.py          # 主流水线
│   ├── chunking.py          # 分块 + 位置追踪
│   ├── summarizer.py        # 分层摘要
│   ├── topology.py          # 静态分析 + LLM 双通道拓扑
│   ├── locate_index.py      # 定位索引
│   ├── storage.py           # knowledge/ 写入
│   ├── models.py            # 数据模型
│   ├── llm/                 # LLM 抽象层（openai_compatible / ollama / anthropic / local）
│   └── extractors/          # 文件解析器（按扩展名注册）
├── tests/                   # pytest 测试
└── examples/                # 示例项目与生成结果
```
