# 循序研究树核心：会话承接优先实验版

本版将 `conversation_graph.py` 的判别策略作为后续 Research Graph Core 的基准：先检查上一条问答的逻辑承接，再解析历史指代、回访及共同上位问题，不确定时退回 BM25 候选评分。时间相邻不等于父子；并列研究问题应找共同上位，不能机械串成链。

这是离线算法基准，尚未接入平台数据库或替换线上聊天流程。真实会话边界未知，当前测试按原始提问时间流进行；不能把数据中的“模拟对话段”当作真实会话。未来在线应用应以真实 conversation_id 限定首轮检查范围。

## 运行与数据边界

从仓库根目录运行，使用项目 AI Python 环境，并配置忽略的 `ai-engine/.env` 中的 `XUNXU_` 模型参数。模型调用会产生费用；命中缓存时不会重复调用。

实验数据目录默认 `.runtime/experiments/robot-qa-v1`，不进入 Git。准备阶段将纯问答输入与评估标签分开；思想描述、历史评分缓存及报告也保存在该目录。`conversation_graph.py` 依赖 `inputs/qa.jsonl`、`descriptors/core.jsonl`、`evaluation/labels.jsonl` 和 `scored-graph/{graph,assessments}.json`。原始父子标签仅用于输出后评估；外域范围过滤使用原表节点类型。没有真实会话 ID，不声明为同会话实验。

```sh
python experiments/qa_space/conversation_graph.py
python experiments/qa_space/build_conversation_comparison.py
python -m unittest discover -s experiments/qa_space -p 'test_*.py'
```

HTML 构建器使用仓库中的无数据模板 `tree-template.html`；原评分版保留为对照。输出 `research-tree-conversation.html` 与 `research-tree-conversation-comparison.html`，自下而上展示。对照页面左侧需要另行生成的原评分 HTML；本目录提供算法实验脚本，不是全新平台的一键安装入口。

## 当前结果与限制

本轮 114 条主题内问答全部关联，加主题根共 115 节点，25 条交叉虚线；13 条域外问答排除。原表 86 条父子标注匹配 45 条（52.33%）。原评分版只有 23 条问答入树，91 条待复核，存在父节点待复核引起的连锁阻塞。

Q1.1 正确回指 Q1；Q3.2 仍被判为 Q3.1 的深化，原表标为 Q3 的子节点。覆盖率提升不代表准确率足够。引用校验只确认文本存在，不证明关系正确。评分未校准，虚线仍沿用旧评分第二、第三名的结果，尚未独立验证。后续需专门评估兄弟/深化区分及真实会话边界，不能把当前结果直接视为生产级判别规则。

## 关系判别 V2（实验 A）

在 `codex/relation-classification-v2` 中，`relation_v2.py` 增加研究目标、目标包含及替代关系解释，并用上一版 AI 父节点及其上位作为对比提示。旧图是待检查的提案，不是标准答案；原表父标注没有进入模型输入。检索和问答节点粒度保持基线，未接入平台。

`relation_v2_question_guard.py` 是第二轮探索修订：以问题自身目标判定范围，核心描述只作消歧，避免把描述中提到的方法或后续方向扩大为父问题的范围。此次数据已经被检查过，所有结果均为开发集探索，不是留出验证。

```sh
python experiments/qa_space/relation_v2.py
python experiments/qa_space/relation_v2_question_guard.py
python experiments/qa_space/evaluate_relation_v2.py --variant relation-v2-question-guard
python experiments/qa_space/build_relation_v2_comparison.py --variant relation-v2-question-guard
```

第一轮保存在 `relation-v2/`，第二轮保存在 `relation-v2-question-guard/`。比较统计同时列出正确关系增益、损失、待复核及兄弟误接成子节点的案例；不能只以已连线精度判断改进。HTML 详情显示研究目标及关系解释。核心描述引用通过不代表语义正确；存在歧义和未通过校验的问答仍需复核。

## 待判定资源池

构建 V2 HTML 后运行 `python experiments/qa_space/resource_pool.py`。未入树问答按 AI 的 `proposal.parent_id` 放到建议归属节点的资源池，保留完整内容与核心描述。建议目标未入树或缺失时进入未放置公共池，并保留建议目标；不按时间上一问放置、不追溯祖先、不建立隐藏父子链。节点详情与工具栏均可查看，暂存不改变图结构及父节点准确率。重复运行替换原资源池块。

## 严格逐条增量生长

`incremental_growth.py` 从空主题根开始，不读取旧树或原始父子/域外标注。每条 QA 先读取刚提交的节点与上一问实际归属，进行局部判断；不确定、请求检索或引用未通过时，才使用已处理问答索引检索。索引增量维护 BM25 统计和512维向量，当前候选搜索仍为线性扫描，不宣称 ANN。每问最多一次局部及一次扩大检索模型请求。

同问题补充直接放到已有节点资源池，不创建节点。新分支只追加一个节点，持久化坐标；同层占位向两边寻找空位，不改旧坐标、父边或顺序。疑似旧结构错误不自动重构。未确定问答按建议目标暂存；域外问答保留档案。每步保存原子检查点、树版本、事件和实际 token 用量，失败后重新运行从最后一次提交继续，已完成记录不重新判别。

```sh
python experiments/qa_space/incremental_growth.py --theme 智能制造 --budget 10
python experiments/qa_space/evaluate_incremental_growth.py
python experiments/qa_space/build_incremental_page.py
```

输出目录 `.runtime/experiments/robot-qa-v1/incremental-growth/`。主题、研究范围、候选预算可以通过 `--theme`、`--scope`、`--budget` 指定；检查点配置或输入变化时拒绝混用，独立实验应换 `--dataset` 目录。`--limit` 可用于分批执行，同一配置再运行会继续。

当前仍为离线时间流，无真实会话ID；在线平台事务、跨设备并发、人工结构治理、任务队列尚未接入。思想描述沿用预先准备的资料，其模型生成成本未计入当前 token。模型缓存命中次数与实际请求分开统计。节点描绘直接读取保存的位置；不重新运行树布局算法。

## 独立交互实验页面

运行 `scripts/run-standalone-lab.sh`，打开 `http://127.0.0.1:5174/research-tree-incremental.html`。该服务替代原5174静态服务器，仍提供其他导出页面，依赖此前生成的 `.runtime/exports/research-tree-incremental.html` 模板。

页面支持新研究空间、从当前选中节点新建会话、多轮问答、刷新恢复、失败后的单独生长重试。每轮一次模型请求同时生成回答和约80字核心描述；再局部判别，必要时扩大检索。使用同一份增量提交规则，旧节点坐标和父边不会改写。同问题进入资源池，不确定保留待判定；原始问答先保存，生长失败不会丢失回答。请求标识防止重复写入。

私有状态位于 `.runtime/standalone-lab/state.json`，密钥仅从 `ai-engine/.env` 读取，不发往浏览器。研究空间、会话、向量与增量事件独立于Java平台数据库。本地服务绑定127.0.0.1；平台接入代码已通过git stash备份并撤下。语义判别仍为实验级，不能把自动连线视为正确关系保证。

独立服务增加挂根检查：局部判别为新方向或拟归根时，无论引用是否通过，都先检索已有空间，再对候选做最终判断。最终仍挂根必须说明没有更直接候选；确认信息缺失或矛盾则暂存待判定。每轮保存 `growth_trace`，记录局部提案、检索触发、候选问答和节点。只影响新增问答，不自动修改已保存的根下分支。有限候选检索不能证明全空间不存在更直接归属，仍需复核。

最终归属规则现改为：每条新问答都检索已有空间，不仅挂根或新方向。局部判别之后，复用历史向量并进行词法检索，获取最多10条问答候选，加入对应节点与祖先，将 `local_proposal` 和候选一起提交最终模型比较。局部深化、同问题补充或域外判定也不能跳过此步骤。新增问答通常为回答/核心一次、局部判别一次、最终比较一次模型调用；检索本身不调用大模型，不重新编码旧向量或重排旧结构。已有错误连线不自动迁移。
