# 循序 XunXu：V1.1 系统实现

目标架构采用 **Spring Boot Java 业务服务 + FastAPI Python 智能引擎 + PostgreSQL / pgvector + React / TypeScript**。Java 是最终写入与权限审核的唯一权威；AI 引擎只分析已经准入的证据和上下文，不连接数据库、不直接创建正式节点或批准结构调整。

目录：

- `backend/`：Java 业务服务，负责研究空间、证据、节点、结构审核、Run 与持久化。
- `ai-engine/`：FastAPI 无状态分析服务，负责思想坐标建议、候选方向和可选模型回答。
- `frontend/`：React / TypeScript 研究树与档案界面。
- `xunxu/`：早期 SQLite 本地原型，仅用于已实现领域规则的回归验证，不是最终架构的业务写入入口。
- 根目录 V1.0 / V1.1 理论文件：设计规范，保留历史版本。

## 启动正式系统

本机已建立 `xunxu_core` PostgreSQL 数据库并安装 pgvector。数据库地址和用户可在 `backend/.env.example` 查看，通过环境变量覆盖；脚本不会自动读取 `.env`。新设备可用 `deploy/compose.yml` 启动 PostgreSQL、Redis 和 MinIO，先在 `deploy/.env` 填入自选凭据，随后 `docker compose --env-file deploy/.env -f deploy/compose.yml up -d`。容器 PostgreSQL 使用 5433 端口。Redis 与 MinIO 目前仅提供部署配置，业务缓存、文件上传尚未接入。

在三个终端中分别运行：

```sh
# Java 业务核心（需要 JDK 21 与 Maven；本机项目专用运行环境由脚本选取）
./scripts/run-backend.sh

# Python 分析服务（安装方式见下文）
./scripts/run-ai.sh

# React 前端
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

已打包后端位于 `backend/target/research-core-0.1.0.jar`；启动脚本优先使用它。修改 Java 源码后需重新 `./scripts/build-backend.sh`，或移走旧 jar 使用开发模式，避免运行旧代码。

打开 `http://127.0.0.1:5173`，前端 API 代理到 Java `8080`。首次启动会建立明确标记的示范空间。研究树支持节点档案、问答原文定位、思想簇生长、审核预览、共同分支、剪枝移植及 Markdown 营养包。服务端数据库为事实来源。

实际设备执行：在设备授权研究目录运行 `python3 device-agent/agent.py --server http://127.0.0.1:8080 --workspace /absolute/research-workspace --name local-device`；前端行动节点建立 Run 后选择设备，以参数数组派发命令。Agent 回传真实退出码、日志摘要和产物摘要。完整协议见 [设备 Agent](device-agent/README.md)。远程设备还需部署中心网络访问和服务令牌，当前启动参数限制本机访问。

领域实体、事件和算法边界见 [研究图架构](docs/ARCHITECTURE.md)。未配置模型时可提交人工问答；不是由模型自动生成回答。默认使用本地真实语义嵌入；模型意图判定与候选阈值仍需科研数据校准。

## 智能引擎

```sh
cd ai-engine
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8001
```

交互 API 说明位于 `http://127.0.0.1:8001/docs`。

| 接口 | 用途 | 权限边界 |
|---|---|---|
| `GET /health` | 服务及坐标模式状态 | 不读取研究数据库 |
| `POST /analyze` | 一主多辅思想与高维坐标建议 | 不写数据库；不把相同标题直接判定为相同研究意图 |
| `POST /candidates` | 同类型 2～3 个研究推进候选 | 离线模板；保留人工留存方向 |
| `POST /chat` | 调用已配置的兼容模型 | 仅接收 Java 已准入的祖先路径和当前节点上下文 |

默认采用本地 BGE 中文 512 维语义嵌入。历史 `experimental-lexical-hash-256` 出生坐标保留，并通过独立版本重新编码。匹配与聚类输出是待验证建议，最终服务必须核验独立问答数、研究意图、适用条件、冻结和已有节点承载，不能直接把词面距离转成结构父子关系。

可选环境变量：

- `XUNXU_API_BASE`、`XUNXU_API_KEY`、`XUNXU_MODEL`：兼容 Chat Completions 的模型服务。
- `XUNXU_EMBEDDING_API_BASE`、`XUNXU_EMBEDDING_API_KEY`、`XUNXU_EMBEDDING_MODEL`：兼容 Embeddings 的真实嵌入服务。配置后会实际请求服务；请求失败会返回错误，不冒充成功或悄悄切换为真实语义坐标。

密钥通过服务端环境传入，不写入研究问答或前端。真实模型质量与聚类阈值仍须科研样本校准。

## 验证

```sh
cd ai-engine
python3 -m unittest discover -s tests -v
```

Java 单元验收：在配置 JDK 后运行 `./scripts/build-backend.sh test`。真实服务集成验收：运行 `python3 scripts/verify-integration.py --output docs/integration-result.json`，脚本明确创建验收空间并保留证据。前端构建：`npm run build --prefix frontend`。

AI 测试覆盖：一主多辅、触发 ID 稳定、坐标模式声明、跨空间拒绝、引用片段真实性、禁止后代与全局总结字段、同标题仅作候选、保留人工候选、真实嵌入结果与非法返回拒绝。

SQLite 原型另有 11 项领域回归，运行 `cd xunxu && python3 -m unittest discover -s tests -v`。这些测试能验证原型的边界，不能替代 Java / PostgreSQL 最终链路的集成验收。

实际本机结果见 [验收记录](docs/VERIFICATION.md)：Java 7 项单元测试、Python 6 项测试、真实 HTTP 9 组验收及独立 Agent 执行通过。

## 进一步完善

- 真实科研样本上的思想提取、嵌入、密度聚类与上下文归属质量。
- 大规模并发与分空间事务锁、汇合来源的数据库级完整性。
- 跨设备 Agent、任务队列、断线重传、取消与实验结果完整性；登记设备与 Run 不等于远端实际执行。
- 运行中任务移植、跨边界汇合、跨父节点叶合并和复杂结构差异恢复；当前叶合并要求同父、运行中的分支移植会被拒绝。
- 自然布局在宽浅树、深链、汇合及大规模关联下的稳定性和可读性。
- 多人账户、权限与生产部署；当前本机开发服务不作为公网产品。

V1.1 的历史不可覆盖、上下文隔离、人工结构审核和自动操作幂等属于约束，不因模型或布局算法的选择而改变。

## DeepSeek 接入与自动问答验收

本机已接入 DeepSeek `deepseek-flash`。密钥仅保存在被忽略的 `ai-engine/.env`（权限 0600），不向前端返回；`./scripts/run-ai.sh` 加载配置。兼容接口说明见 [DeepSeek 官方文档](https://api-docs.deepseek.com/)。

页面右键研究节点 →「新建会话」，或使用研究空间顶部「新建会话」。在连续聊天窗口输入问题即可调用模型回答、自动提取思想，并逐轮保存判断。多个独立问答被识别为同一研究意图后，Java 会生成新节点或强化已有节点引用。第一条问答通常只积累证据。若要人工确定新思想，可使用独立思想标记。模型提取不等同于已校准的科研语义聚类；新问答出生坐标使用本地真实语义嵌入，历史出生坐标不覆盖。

真实验收空间「DeepSeek 自动生长测试」中保留两次 API 回答与自动生成的节点；结果见 `docs/deepseek-verification.json`。提交后页面自动显示回答和节点创建提示。重新运行 `scripts/verify-model-growth.py` 会调用真实付费 API 并创建新验收空间。

## 多轮研究会话

节点级会话以点击的节点为固定锚点；空间级会话以根节点为固定锚点。会话完整保存，关闭窗口后可在起始节点「问答」档案中继续会话，或由问答条目精确定位对应聊天轮次。Enter 发送，Shift + Enter 换行。首轮问题自动成为新会话标题。

Java 从服务端加载当前会话历史交给 AI，不接受客户端自行拼接的历史；祖先路径上下文独立构建，不加载兄弟会话或子孙总结。每轮原始问答不可覆盖，思想提取与证据归属、生长结果以审计快照保存；后续生长不改写前轮判断。重复发送用 request_id 去重，过期轮数会被拒绝并刷新历史。当前等待完整回答与分析结束后显示，尚未提供逐字流式输出。

真实多轮验收见 `docs/multiturn-verification.json`。默认对话携带当前会话的完整历史，达到历史加载上限时需从节点另建会话；空间级入口不将整棵树视作全局总结。

## 核心概念语义空间（2026-10-10）

右上方“思想空间”可查看真实 512 维坐标的二维投影、核心概念、近邻距离与聚类理由。历史问答已可版本化量化，新问答自动采用本地 BGE 嵌入与 DeepSeek 意图判定。详见 [语义空间实现](docs/SEMANTIC-SPACE.md)。候选阈值仍属试验参数，需要继续校准。

普通会话的回答与思想/核心概念提取已合并为一次 DeepSeek 请求，坐标随后在本地计算。候选意图判断仍按需独立调用。每轮保存实际 token usage；详见 [合并请求验收](docs/combined-verification.json)。

研究演化归属已支持同一会话的顺序证据与高维思想坐标联合判断。新节点在创建时确定深入分支位置；已有节点通过可审核的移动预览调整。见 [会话生长规则](docs/CONVERSATION-GROWTH.md) 和 [真实空间验证](docs/conversation-growth-verification.json)。

问答可靠性：有效回答和思想不会因后续归类失败而丢失。聊天内可单独“重试生长分析”，不重新生成回答；模型格式或截断错误会显示具体原因。实际多轮验收见 [可靠性验证](docs/reliability-verification.json)。
