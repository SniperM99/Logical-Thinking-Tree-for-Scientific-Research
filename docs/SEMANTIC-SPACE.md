# 循序：问答核心概念的空间量化

2026-10-10 实现。原理论 V1.0 / V1.1 保留。

## 两个层次的实际坐标

DeepSeek 提取每轮问答的主要/辅助思想及最多五个核心概念。每条思想的完整语义表述，以及每个短核心概念，分别输入本地 BGE 中文嵌入模型，生成 512 维、L2 归一化的数值向量。思想之间的研究意图比较使用完整思想的向量；短概念坐标保留用于检视和后续研究，当前不直接把泛化词（例如 JEPA）当作节点生成依据。

模型：BAAI/bge-small-zh-v1.5，Xenova ONNX 量化转换。固定转换版本 `75c43b069aac4d136ba6bc1122f995fedcfd2781`，文件 SHA256 记录在本地 manifest，加载时校验。来源：[原模型](https://huggingface.co/BAAI/bge-small-zh-v1.5)、[转换模型](https://huggingface.co/Xenova/bge-small-zh-v1.5)。执行在本机 CPU，嵌入无需另外购买 API。DeepSeek 仍承担对话、概念提取和候选研究意图判断。

模型与维度相同才允许比较。余弦相似度 `dot(a,b)/(norm(a)*norm(b))`，余弦距离 `1-similarity`。相似度不是概率或科研结论的可信度。

## 从距离到研究节点

当前试验候选阈值为相似度 0.60；这是第一版参数，需要更多真实科研资料评估。进入候选的跨问答思想，由 DeepSeek 区分 `same_intent`、`related`、`distinct`。仅共享研究对象不足以判定同一研究问题，目标和适用条件必须兼容。没有模型判定时不自动归并。

Java 检查同研究空间、同上下文锚点、相同坐标模型、至少两个不同 QA。采用完整连接约束，各成员之间均须判定同意图，避免一个泛化思想串联不相关分支。同一 QA 的多个辅助思想不能制造多个独立证据。满足条件的有效簇自动生成节点，已有节点只强化证据；多个已存在节点的结构合并仍需人工审核。父节点总结不被新节点反向修改。

当前没有用一次单问答自动判定“独立新思想”的机制；这一分支保留人工独立思想标记。大量思想的全对比较和模型成本仍需后续索引、增量候选和队列优化。

## 原始证据与版本

历史 256 维文字哈希坐标保持原样，不再用于语义距离。`thought_coordinates` 增加不可变编码版本，记录思想/问答/锚点、模型、维度、完整向量、概念向量、时间、输入摘要。出生向量和既有工作向量均不被覆盖。

`thought_links` 保存坐标版本间的距离、意图判断与理由；语义簇单独标记 `basis=semantic`。旧分类簇和历史问答判断保留。重新量化不创建新问答，也不修改会话锚点；同一模型已有编码会复用，避免反复生成节点和重复模型请求。移植上下文由当前锚点所属空间隔离，显示模型版本不改变图结构。

## 界面与 API

在研究空间右上方打开“思想空间”。可选思想查看原始问答、核心概念、各概念 512 维向量的前八维和范数、近邻相似度/距离、同意图判断及原因。二维图为 PCA/SVD 投影，按同尺度显示；投影坐标不用于聚类和父子关系判定，添加数据后投影位置可能变化。

- `GET /api/thought-space?space_id=...`：量化坐标、投影、近邻和簇。
- `POST /api/thought-space/reindex {space_id}`：已有问答版本化编码并重判生长。
- 新会话每轮 `/api/qa` 自动使用真实嵌入和语义判定。

## 安装与验收

AI 服务使用 `.runtime/ai-venv`；依赖见 `ai-engine/requirements.txt`。新部署执行 `python3 -m venv .runtime/ai-venv`、`.runtime/ai-venv/bin/pip install -r ai-engine/requirements.txt`、`python3 ai-engine/install-model.py`，再启动 `scripts/run-ai.sh`。`/health` 报告模型是否 ready。模型或依赖未就绪会明确报错，不静默退回文字哈希。

Java 13 项规则测试、Python 12 项测试，以及 React 构建均通过。`scripts/verify-semantic-space.py` 验证用户测试空间原始 QA、出生坐标、会话及父节点总结未变；结果见 `semantic-verification.json`。12 条思想、52 个核心概念已量化，1 个同意图关系形成新研究节点。`scripts/verify-semantic-growth.py` 使用独立控制输入验证不同标题的同研究问题自动生长、每轮判断留存和重复量化去重；结果见对应 JSON。

## 回答与思想合并请求（2026-10-10 更新）

普通聊天通过 Python `/research-turn` 一次调用 DeepSeek，返回 `{answer, thoughts}`。`answer` 单独显示给用户，思想及核心概念经结构和原文引用校验后，在本地计算语义坐标。Java 直接使用返回的本地分析，不再为普通聊天调用 `/analyze` 做第二次思想提取。

每轮 QA 的 `generation` 记录模式、模型、回答/提取请求数与服务实际返回的 token usage。格式无效或输出被截断时整轮不提交，且不自动增加提取请求；重试由用户发起。人工导入已有回答时仍可单独提取思想，人工指定思想的兼容路径保留。

相近思想的候选意图判断仍按需独立请求。因此“一次”仅指回答＋思想提取，并非保证整轮永远只请求一次模型。坐标计算默认在本地完成。

验收：Java 13 项、Python 15 项测试通过；Python 测试核验 provider 调用仅一次、上下文历史顺序、512 维坐标、无效格式不追加请求。真实双轮 DeepSeek 验收见 `combined-verification.json`，包含服务返回的 token usage，并检查参数追问、历史判断留存及请求重放去重。

为避免 JSON 模式偶发空响应，合并接口采用强制调用 `deliver_research_turn` 的函数参数返回两部分结果；这里只解析数据，不执行外部工具，也不追加模型轮次。该格式由 [DeepSeek Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/) 支持，禁用 thinking 后使用。用户“只回复数字”等限制仅应用于 answer 字段。
