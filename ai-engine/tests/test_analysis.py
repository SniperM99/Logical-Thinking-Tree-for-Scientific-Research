import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from pydantic import ValidationError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from main import AnalyzeRequest, CandidatesRequest, ScopedContext, ChatRequest, analyze, candidates, coordinates, chat_endpoint


class StatelessAnalysis(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ,{},clear=True)
        self.env.start()
        self.context = {'space_id':'space1','node_id':'parent','direct_summary':'父节点问题',
                        'ancestors':[{'node_id':'root','title':'根目标','summary':'原始背景'}]}

    def tearDown(self):
        self.env.stop()

    def request(self,**extra):
        return AnalyzeRequest(qa_id='qa1',question='研究思想 A 和 B',answer='保留证据',context=self.context,**extra)

    def test_chat_uses_only_admitted_conversation_turns_in_order(self):
        request=ChatRequest(question='继续验证它',context=self.context,history=[{'qa_id':'earlier','question':'学习率实验','answer':'控制初始权重'}])
        with patch.dict(os.environ,{'XUNXU_MODEL':'test-model'}):
            with patch('main.provider_request',return_value={'choices':[{'message':{'content':'连续回答'}}]}) as model:
                self.assertEqual(chat_endpoint(request)['answer'],'连续回答')
                messages=model.call_args.args[1]['messages']
                self.assertEqual([m['role'] for m in messages],['system','user','assistant','user'])
                self.assertEqual(messages[-2]['content'],'控制初始权重')
                self.assertEqual(messages[-1]['content'],'继续验证它')

    def test_model_extracts_thoughts_and_receives_known_intents(self):
        with patch.dict(os.environ,{'XUNXU_MODEL':'deepseek-flash'}):
            with patch('main.provider_request',return_value={'choices':[{'message':{'content':'{"thoughts":[{"text":"研究思想 A","topic":"稳定问题","excerpt":"研究思想 A"}]}'}}]}) as model:
                result=analyze(self.request(intent_catalog=['稳定问题']))
                self.assertEqual(result['thoughts'][0]['topic'],'稳定问题')
                self.assertEqual(result['thoughts'][0]['proposal']['minimum_distinct_qas'],2)
                self.assertIn('稳定问题',model.call_args.args[1]['messages'][1]['content'])
                self.assertFalse(result['writes_performed'])

    def test_model_fabricated_excerpt_is_rejected(self):
        with patch.dict(os.environ,{'XUNXU_MODEL':'deepseek-flash'}):
            with patch('main.provider_request',return_value={'choices':[{'message':{'content':'{"thoughts":[{"text":"X","topic":"X","excerpt":"不存在的研究证据"}]}'}}]}):
                with self.assertRaises(HTTPException):analyze(self.request())

    def test_one_main_multiple_auxiliary_and_stable_triggers(self):
        req=self.request(thoughts=[{'text':'研究思想 A','topic':'研究问题','excerpt':'研究思想 A'},
                                  {'text':'思想 B','topic':'另一个问题','excerpt':'B'}])
        first,second=analyze(req),analyze(req)
        self.assertFalse(first['writes_performed'])
        self.assertEqual([x['role'] for x in first['thoughts']],['main','auxiliary'])
        self.assertEqual([x['trigger_id'] for x in first['thoughts']],[x['trigger_id'] for x in second['thoughts']])
        for thought in first['thoughts']:
            self.assertEqual(len(thought['original_coordinate']),512)
            self.assertTrue(thought['semantic_embedding'])
            self.assertEqual(thought['original_coordinate'],thought['working_coordinate'])
            self.assertFalse(thought['proposal']['create_automatically'])
            self.assertEqual(thought['proposal']['minimum_distinct_qas'],2)

    def test_cross_space_and_fabricated_excerpt_rejected(self):
        with self.assertRaises(HTTPException):
            analyze(self.request(existing_nodes=[{'node_id':'foreign','space_id':'space2','title':'X'}]))
        with self.assertRaises(HTTPException):
            analyze(self.request(thoughts=[{'text':'思想','topic':'T','excerpt':'原文不存在'}]))

    def test_nutrition_context_preserves_approved_transplant_path(self):
        context=ScopedContext(**self.context,nutrition_context='根目标 → 原父节点 → 移植节点')
        self.assertEqual(context.nutrition_context,'根目标 → 原父节点 → 移植节点')
        self.assertEqual(ScopedContext(**self.context).nutrition_context,'')
        result=candidates(CandidatesRequest(context=context))
        self.assertFalse(result['writes_performed'])

    def test_scope_does_not_accept_descendant_or_global_summary_fields(self):
        with self.assertRaises(ValidationError):
            ScopedContext(**self.context,descendants=[{'title':'子孙结果'}])
        with self.assertRaises(ValidationError):
            ScopedContext(**self.context,global_summary='兄弟成果')

    def test_equal_title_match_is_only_candidate_and_retained_candidates_preserved(self):
        result=analyze(self.request(thoughts=[{'text':'研究问题','topic':'主题'}],
            existing_nodes=[{'node_id':'existing','space_id':'space1','title':'主题'}]))
        proposal=result['thoughts'][0]['proposal']
        self.assertEqual(proposal['matched_node_candidates'],['existing'])
        self.assertTrue(proposal['requires_intent_validation'])
        result=candidates(CandidatesRequest(context=self.context,count=2,retained_titles=['人工保留方向']))
        self.assertEqual(len(result['candidates']),2)
        self.assertEqual(result['retained_titles'],['人工保留方向'])
        self.assertEqual(result['type'],'hypothesis_validation')

    def test_configured_embedding_is_real_provider_result_and_bad_dimensions_fail(self):
        with patch.dict(os.environ,{'XUNXU_EMBEDDING_MODEL':'example-model'}):
            with patch('main.provider_request',return_value={'data':[{'index':0,'embedding':[0.1,0.2]}]}):
                vectors,method,semantic=coordinates(['研究'])
                self.assertEqual(vectors,[[0.1,0.2]])
                self.assertTrue(semantic)
                self.assertEqual(method,'provider:example-model')
            with patch('main.provider_request',return_value={'data':[{'index':0,'embedding':[float('nan')]}]}):
                with self.assertRaises(HTTPException):coordinates(['研究'])

if __name__=='__main__':unittest.main()
