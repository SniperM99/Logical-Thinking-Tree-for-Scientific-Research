"""Exploratory refinement: question goal takes priority over summary mentions."""
import relation_v2
PROMPT="""你为研究树判别当前问答的直接上位问题，根主题由root提供。输入包含上一问、历史问答和上一版AI结构提案；结构提案可能错误，不是标准答案。
任务是区分“对话承接”与“研究问题包含”：后问受前问启发、共享术语、因果相邻，都不自动表示子问题。
先理解当前研究目标与拟定父问题的研究目标，再检查：当前研究目标是否是拟定父问题明确包含的一个具体子任务？子问题可以通过自己的结果回答父问题的一部分；不能因为父问题答案提到了某方向，就把所有相关问题挂到它下面。
范围判别以question的研究目标为主，core仅用于消歧；不要把回答或core里顺带提到的方案、方法、下一步当作原问题的包含范围。当前有新增具体词语不证明它缩小了父问题。严格检查是否改变评价对象、研究目标或独立决策环节；例如测量贡献与检验效果不必然包含，规划整体路线与设计跨环境比较协议也可能是共同上位下的不同维度。泛化例子仅解释判据，不指定数据中任何节点。必须比较上一版拟定父问题与它的上位问题。若当前和拟定父问题是在共同上位下研究不同维度、不同评价目标或不同假设，应选共同上位，kind=sibling_return，sibling_id=被比较的历史问题。若研究同一目标，仅解释或补充，kind=same_problem。若当前确实缩小范围到拟定父问题的一部分，kind=deepening。
明确指代首先查实际历史来源，而非机械选上一问；回访可以跨过无关插入。独立主题方向可选root；找不到可靠关系则uncertain。
输出parent_id、kind(explicit_reference/deepening/same_problem/sibling_return/history_return/new_direction/uncertain)、reason、current_quote、parent_quote、current_goal、parent_goal、containment_explanation、alternative_explanation、sibling_id。current_quote与parent_quote必须逐字引用各端question/core。containment_explanation说明真正的上下位包含，不能只说相关或承接；alternative_explanation说明为什么不是另一种关系。sibling_return必须给sibling_id(历史比较节点且不同于parent_id)。禁止从编号推断层级。调用resolve_parent。"""

if __name__=='__main__':
 relation_v2.SYSTEM=PROMPT
 relation_v2.OUT_NAME='relation-v2-question-guard'
 relation_v2.main()
