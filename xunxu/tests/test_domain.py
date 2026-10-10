import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from domain import Store, DomainError


class ResearchInvariants(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'research.db'
        self.store = Store(self.path)
        self.space = self.store.create_space('测试研究', 'ROOT_ONLY_BACKGROUND')
        self.root = self.space['root_id']

    def tearDown(self):
        self.tmp.cleanup()

    def node(self, title, parent=None, **fields):
        return self.store.create_node({'parent_id':parent or self.root, 'title':title, 'summary':title+'_DIRECT', **fields})

    def operation(self, op, node, **fields):
        return self.store.propose({'operation':op, 'node_id':node, 'reason':'研究者明确确认', **fields})

    def commit(self, op, node, **fields):
        return self.store.approve(self.operation(op,node,**fields)['id'])

    def test_context_excludes_descendants_siblings_and_preserves_snapshot(self):
        parent = self.node('PARENT')
        sibling = self.node('SIBLING_SECRET')
        conv = self.store.create_conversation({'node_id':parent['id']})
        child = self.node('CHILD_RESULT',parent['id'])
        self.store.add_qa({'conversation_id':conv['id'],'question':'子研究新证据','answer':'子研究结果',
                           'thoughts':[{'text':'子研究结果','topic':'CHILD_RESULT','node_id':child['id']}]})
        context = self.store.context(parent['id'])
        self.assertEqual(context['direct'],parent['summary'])
        self.assertEqual([x['id'] for x in context['ancestors']],[self.root])
        self.assertNotIn(sibling['summary'],json.dumps(context))
        self.assertNotIn(child['summary'],json.dumps(context))
        saved = self.store.read()['conversations'][conv['id']]
        self.assertEqual(saved['anchor_id'],parent['id'])
        self.assertEqual(saved['context_snapshot'],conv['context_snapshot'])

    def test_clusters_count_unique_qas_and_retry_does_not_duplicate(self):
        conv = self.store.create_conversation({'node_id':self.root})
        data = {'conversation_id':conv['id'],'question':'独立问题','answer':'证据', 'request_id':'first',
                'thoughts':[{'text':'同主题 A','topic':'新方向'},{'text':'同主题 B','topic':'新方向'}]}
        first = self.store.add_qa(data)
        self.assertEqual(first['created_nodes'],[])
        self.assertTrue(self.store.add_qa(data)['idempotent'])
        second = self.store.add_qa({**data,'request_id':'second'})
        self.assertEqual(len(second['created_nodes']),1)
        self.store.add_qa({**data,'request_id':'third'})
        state = self.store.state(self.space['id'])
        self.assertEqual(len([n for n in state['nodes'] if n['title']=='新方向']),1)
        self.assertEqual(len(state['qas']),3)
        self.assertEqual(len([t for t in state['thoughts'] if t['role']=='main']),3)
        self.assertTrue(second['created_nodes'][0]['evidence'])

    def test_confluence_preserves_subtrees_and_uses_distinct_growth_edges(self):
        a,b = self.node('A'),self.node('B')
        child = self.node('A_CHILD',a['id'])
        p = self.commit('confluence',a['id'],sources=[a['id'],b['id']],title='联合问题')
        joined = self.store.read()['nodes'][p['result_node_id']]
        self.assertIsNone(joined['parent_id'])
        self.assertEqual(joined['sources'],[a['id'],b['id']])
        self.assertEqual(self.store.read()['nodes'][child['id']]['parent_id'],a['id'])
        self.assertEqual(len(self.store.context(joined['id'])['sources']),2)
        self.assertEqual(self.store.state()['metrics']['depth'],2)
        with self.assertRaises(DomainError):
            self.operation('confluence',a['id'],sources=[a['id']],title='错误')
        with self.assertRaises(DomainError):
            self.operation('merge',b['id'],target_id=child['id'])

    def test_stale_approval_and_cycle_rejected_atomically(self):
        a,b = self.node('A'),self.node('B')
        child = self.node('C',a['id'])
        with self.assertRaises(DomainError):
            self.operation('move',a['id'],target_id=child['id'])
        p = self.operation('move',child['id'],target_id=b['id'])
        self.node('结构发生变化')
        with self.assertRaises(DomainError):
            self.store.approve(p['id'])
        self.assertEqual(self.store.read()['nodes'][child['id']]['parent_id'],a['id'])
        self.assertEqual(self.store.read()['proposals'][p['id']]['status'],'pending')

    def test_leaf_merge_keeps_original_identity_and_summary_history(self):
        a,b = self.node('A'),self.node('B')
        before = self.store.read()['summaries'].copy()
        result = self.commit('merge',a['id'],target_id=b['id'],title='合并方向')
        d = self.store.read()
        for n in (a,b):
            self.assertTrue(d['nodes'][n['id']]['archived'])
            self.assertEqual(d['nodes'][n['id']]['merged_into'],result['result_node_id'])
        for key,value in before.items():
            self.assertEqual(d['summaries'][key],value)
        c = self.node('非叶节点')
        self.node('后代',c['id'])
        with self.assertRaises(DomainError):
            self.operation('merge',c['id'],target_id=result['result_node_id'])

    def test_freeze_blocks_growth_hide_is_recoverable(self):
        a = self.node('A')
        child = self.node('C',a['id'])
        self.commit('freeze',a['id'])
        with self.assertRaises(DomainError):
            self.node('冻结后自动生长',child['id'])
        self.commit('unfreeze',a['id'])
        self.commit('hide',a['id'])
        self.assertTrue(self.store.read()['nodes'][child['id']]['hidden'])
        self.node('隐藏不等于冻结',child['id'])
        self.commit('restore',a['id'])
        self.assertFalse(self.store.read()['nodes'][child['id']]['hidden'])
        self.assertEqual(self.store.state()['metrics']['hidden'],0)

    def test_transplant_nutrition_excludes_sibling_preserves_anchor_and_isolates(self):
        a = self.node('移植分支')
        sibling = self.node('SECRET_SIBLING')
        child = self.node('移植后代',a['id'])
        conv = self.store.create_conversation({'node_id':a['id']})
        qa = self.store.add_qa({'conversation_id':conv['id'],'question':'原始问题','answer':'原始回答'})['qa']
        proposal = self.operation('transplant',a['id'],title='独立空间')
        nutrition = proposal['preview']['context_md']
        self.assertIn('ROOT_ONLY_BACKGROUND',nutrition)
        self.assertIn(a['summary'],nutrition)
        self.assertNotIn(sibling['summary'],nutrition)
        self.assertNotIn(child['summary'],nutrition)
        result = self.store.approve(proposal['id'])
        new = self.store.state(result['result_space_id'])
        old = self.store.state(self.space['id'])
        self.assertNotIn(a['id'],{n['id'] for n in old['nodes']})
        self.assertEqual({n['id'] for n in new['nodes']},{a['id'],child['id']})
        self.assertIsNone(self.store.read()['nodes'][a['id']]['parent_id'])
        self.assertEqual(self.store.read()['conversations'][conv['id']]['anchor_id'],a['id'])
        self.assertEqual(self.store.read()['conversations'][conv['id']]['space_id'],self.space['id'])
        self.assertEqual(self.store.read()['qas'][qa['id']],qa)
        referenced_thoughts = {r['thought_id'] for r in new['refs']}
        self.assertTrue(referenced_thoughts.issubset({t['id'] for t in new['thoughts']}))
        self.assertNotIn(sibling['summary'],json.dumps(self.store.context(child['id'])))

    def test_run_retry_events_ordering_and_no_ancestor_result_write(self):
        action = self.node('实验',kind='action')
        first = self.store.create_run({'node_id':action['id'],'device':'GPU A','parameters':{'seed':1}})
        event = self.store.report_event(first['id'],{'event_id':'start','status':'running','sequence':1})
        self.assertEqual(self.store.report_event(first['id'],{'event_id':'start','status':'running','sequence':1}),event)
        with self.assertRaises(DomainError):
            self.store.report_event(first['id'],{'event_id':'old','status':'running','sequence':1})
        self.store.report_event(first['id'],{'event_id':'failure','status':'failed','result':{'error':'timeout'}})
        second = self.store.create_run({'node_id':action['id'],'retry_of':first['id'],'device':'GPU B'})
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(second['retry_of'],first['id'])
        self.assertEqual(self.store.context(self.root)['direct'],'ROOT_ONLY_BACKGROUND')
        with self.assertRaises(DomainError):
            self.operation('transplant',action['id'])

    def test_frozen_destination_does_not_admit_internal_evidence(self):
        frozen = self.node('冻结内部集合')
        conv = self.store.create_conversation({'node_id':self.root})
        self.commit('freeze',frozen['id'])
        before = self.store.read()
        self.store.add_qa({'conversation_id':conv['id'],'question':'可引用冻结思想','answer':'新的外部证据',
                           'thoughts':[{'text':'新的外部证据','topic':'冻结内部集合','node_id':frozen['id'],'novel':True}]})
        after = self.store.read()
        internal_before = [r for r in before['refs'].values() if r['node_id']==frozen['id']]
        internal_after = [r for r in after['refs'].values() if r['node_id']==frozen['id']]
        self.assertEqual(internal_after,internal_before)
        self.assertEqual(after['nodes'][frozen['id']],before['nodes'][frozen['id']])

    def test_coordinate_approval_retains_original_and_undo_preserves_audit(self):
        conv = self.store.create_conversation({'node_id':self.root})
        self.store.add_qa({'conversation_id':conv['id'],'question':'研究 Q','answer':'研究 A'})
        thought = next(iter(self.store.read()['thoughts'].values()))
        original = thought['original_vector'][:]
        proposed = [0.0] * 256
        proposed[0] = 1.0
        self.commit('coordinate_move',self.root,thought_id=thought['id'],vector=proposed)
        changed = self.store.read()['thoughts'][thought['id']]
        self.assertEqual(changed['original_vector'],original)
        self.assertEqual(changed['working_vector'],proposed)
        self.assertEqual(changed['vector_history'][0]['vector'],original)
        audit = next(a for a in self.store.read()['audit'].values() if a['operation']=='coordinate_move')
        self.store.undo(audit['id'])
        self.assertEqual(self.store.read()['thoughts'][thought['id']]['working_vector'],original)
        self.assertIn(audit['id'],self.store.read()['audit'])
        self.commit('freeze',self.root)
        freeze_audit = next(a for a in self.store.read()['audit'].values() if a['operation']=='freeze')
        self.store.create_space('新研究','不能丢失新增内容')
        with self.assertRaises(DomainError):
            self.store.undo(freeze_audit['id'])

    def test_independent_space_isolation_and_restart_persistence(self):
        second = self.store.create_space('独立空间','PRIVATE_GOAL')
        a = self.node('A')
        conv = self.store.create_conversation({'node_id':a['id']})
        with self.assertRaises(DomainError):
            self.store.add_qa({'conversation_id':conv['id'],'question':'Q','answer':'A',
                              'thoughts':[{'text':'越界思想','node_id':second['root_id']}]})
        self.assertEqual(self.store.state(second['id'])['qas'],[])
        reopened = Store(self.path)
        self.assertEqual(reopened.read()['nodes'][a['id']],self.store.read()['nodes'][a['id']])
        self.assertEqual(reopened.state(second['id'])['nodes'][0]['summary'],'PRIVATE_GOAL')


if __name__ == '__main__':
    unittest.main()
