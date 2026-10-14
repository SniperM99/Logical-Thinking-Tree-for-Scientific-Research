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
