package cn.xunxu.core;
import static cn.xunxu.core.GraphService.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import com.fasterxml.jackson.databind.ObjectMapper;
import cn.xunxu.core.GraphRepository.Graph;
import java.util.function.Function;
import java.util.*;

class ConversationRulesTest {
  Graph graph;GraphRepository repository;GraphService service;AiClient ai;String root;String space;
  @BeforeEach @SuppressWarnings("unchecked") void setup(){graph=new Graph();repository=mock(GraphRepository.class);ai=mock(AiClient.class);var mapper=new ObjectMapper();when(repository.write(any())).thenAnswer(inv->{Object result=((Function<Graph,Object>)inv.getArgument(0)).apply(graph);graph.revision++;return result;});when(repository.read(any())).thenAnswer(inv->((Function<Graph,Object>)inv.getArgument(0)).apply(graph));when(repository.encode(any())).thenAnswer(inv->mapper.writeValueAsString(inv.getArgument(0)));when(repository.decode(anyString())).thenAnswer(inv->mapper.readValue((String)inv.getArgument(0),Map.class));service=new GraphService(repository,ai);var sp=obj(service.createSpace(map("title","会话测试","goal","ROOT_CONTEXT")));root=s(sp,"root_id");space=s(sp,"id");when(ai.call(eq("/qa-ownership"),any())).thenAnswer(i->{var b=(Map<String,Object>)i.getArgument(1);String current=s(b,"current_node_id");return eq(current,root)?map("decision","branch","node_id",root,"title",obj(b.get("thought")).get("topic"),"research_goal","独立研究目标","distinction","明确启动研究","reason","研究方向首次建立"):map("decision","accumulate","node_id",current,"reason","在当前问题上继续论证");});}

  @Test void spaceEntryKeepsRootAndEachTurnAssessment(){
    var conv=obj(service.conversation(map("space_id",space)));
    assertEquals(root,conv.get("anchor_id"));assertEquals("space",conv.get("origin_scope"));
    when(ai.call(eq("/research-turn"),any())).thenReturn(map("answer","模型回答","analysis",map("thoughts",List.of(map("text","具体研究方向","topic","控制变量实验","excerpt","","original_coordinate",List.of(1.0,0.0),"working_coordinate",List.of(1.0,0.0),"coordinate_method","test")))));
    var d=map("conversation_id",conv.get("id"),"question","验证实验假设","request_id","turn1","expected_turn_index",0);
    var first=obj(service.qa(d));
    var second=obj(service.qa(map("conversation_id",conv.get("id"),"question","继续验证同一假设","request_id","turn2","expected_turn_index",1)));
    assertEquals(0,objects(second.get("created_nodes")).size());verify(ai,never()).call(eq("/chat"),any());verify(ai,never()).call(eq("/analyze"),any());
    var restored=obj(service.conversation(s(conv,"id")));assertEquals(2,restored.get("turn_count"));
    var saved=obj(obj(restored.get("assessments")).get(s(obj(first.get("qa")),"id")));
    assertEquals(1,objects(saved.get("created_nodes")).size()); // Later growth must not rewrite the earlier judgment.
    assertEquals(root,obj(restored.get("conversation")).get("anchor_id"));
    var qaViews=objects(restored.get("qas"));assertNotNull(qaViews.get(0).get("primary_node_id"));assertEquals(qaViews.get(0).get("primary_node_id"),qaViews.get(1).get("primary_node_id"));assertNotEquals(root,qaViews.get(0).get("primary_node_id"));
    assertTrue(Boolean.TRUE.equals(obj(service.qa(d)).get("idempotent")));
    assertThrows(IllegalArgumentException.class,()->service.qa(map("conversation_id",conv.get("id"),"question","过期窗口","expected_turn_index",1)));
  }
  @Test void historyContainsOnlyTheCurrentConversation(){
    var first=obj(service.conversation(map("node_id",root)));var other=obj(service.conversation(map("node_id",root)));
    var captured=new ArrayList<Map<String,Object>>();
    when(ai.call(eq("/research-turn"),any())).thenAnswer(i->{captured.add(i.getArgument(1));return map("answer","记录参数","analysis",map("thoughts",List.of(map("text","参数研究","topic","参数研究","excerpt","","original_coordinate",List.of(1.0),"working_coordinate",List.of(1.0),"coordinate_method","test"))));});
    when(ai.call(eq("/analyze"),any())).thenReturn(map("thoughts",List.of(map("text","参数研究","topic","参数研究","excerpt","","original_coordinate",List.of(1.0),"working_coordinate",List.of(1.0),"coordinate_method","test"))));
    service.qa(map("conversation_id",first.get("id"),"question","本会话参数43871"));
    service.qa(map("conversation_id",other.get("id"),"question","另一个会话秘密87345"));
    service.qa(map("conversation_id",first.get("id"),"question","继续讨论参数"));
    var history=objects(captured.get(2).get("history"));assertEquals(1,history.size());
    assertTrue(history.toString().contains("43871"));assertFalse(history.toString().contains("87345"));
  }
 @Test @SuppressWarnings("unchecked") void growthFailurePreservesAnswerAndRetryDoesNotGenerateAnotherAnswer(){
    var conv=obj(service.conversation(map("space_id",space)));
    when(ai.call(eq("/research-turn"),any())).thenReturn(map("answer","有效回答","analysis",map("thoughts",List.of(map("text","同一具体研究机制","topic","机制研究","excerpt","","original_coordinate",List.of(1.0,0.0),"working_coordinate",List.of(1.0,0.0),"coordinate_method","semantic-test","semantic_embedding",true,"core_concepts",List.of("机制"))))));
    when(ai.call(eq("/coordinates"),any())).thenReturn(map("method","semantic-test","vectors",List.of(List.of(1.0,0.0))));
    service.qa(map("conversation_id",conv.get("id"),"question","研究机制第一轮","request_id","saved1"));
    when(ai.call(eq("/qa-ownership"),any())).thenThrow(new AiClient.AiFailure("研究方向判断字段缺失"));
    var result=obj(service.qa(map("conversation_id",conv.get("id"),"question","研究机制第二轮","request_id","saved2")));var qa=obj(result.get("qa"));String qid=s(qa,"id");
    assertEquals("有效回答",qa.get("answer"));assertEquals("pending",obj(result.get("growth_status")).get("status"));assertEquals(2,graph.all("qas").size());assertEquals(2,graph.all("thoughts").size());assertTrue(graph.all("thought_links").isEmpty());assertEquals(2,graph.all("nodes").size());
    var originalQa=new LinkedHashMap<>(graph.get("qas",qid));when(ai.call(eq("/qa-ownership"),any())).thenAnswer(i->{var body=(Map<String,Object>)i.getArgument(1);return map("decision","accumulate","node_id",body.get("current_node_id"),"reason","同一问题继续积累");});
    var retry=obj(service.retryGrowth(qid));assertEquals("complete",obj(retry.get("growth_status")).get("status"));assertEquals(originalQa,graph.get("qas",qid));assertEquals(0,objects(retry.get("created_nodes")).size());verify(ai,times(2)).call(eq("/research-turn"),any());
  }
  @Test void clarificationWithDifferentTopicStillAccumulatesWithoutCreatingNode(){
    var c=obj(service.conversation(map("space_id",space)));when(ai.call(eq("/research-turn"),any())).thenReturn(map("answer","科研回答","analysis",map("thoughts",List.of(map("text","研究JEPA","topic","JEPA研究","excerpt","","original_coordinate",List.of(1.0),"working_coordinate",List.of(1.0),"coordinate_method","test")))));
    var first=obj(service.qa(map("conversation_id",c.get("id"),"question","深入研究JEPA")));String existing=s(obj(first.get("qa")),"primary_node_id");
    when(ai.call(eq("/research-turn"),any())).thenAnswer(i->{assertEquals(existing,obj(((Map<String,Object>)i.getArgument(1)).get("context")).get("node_id"));return map("answer","机制解释","analysis",map("thoughts",List.of(map("text","解释防坍缩","topic","防坍缩机制及局限","excerpt","","original_coordinate",List.of(1.0),"working_coordinate",List.of(1.0),"coordinate_method","test"))));});
    var result=obj(service.qa(map("conversation_id",c.get("id"),"question","解释它的防坍缩机制")));assertTrue(objects(result.get("created_nodes")).isEmpty());assertEquals(existing,obj(result.get("qa")).get("primary_node_id"));assertEquals(root,givenAnchor(c));assertEquals(2,graph.all("nodes").size());
  }
  Object givenAnchor(Map<String,Object> c){return graph.get("conversations",s(c,"id")).get("anchor_id");}
  @Test void independentExperimentGetsCorrectParentBeforeCreation(){
    var c=obj(service.conversation(map("space_id",space)));when(ai.call(eq("/research-turn"),any())).thenReturn(map("answer","实验回答","analysis",map("thoughts",List.of(map("text","研究JEPA","topic","JEPA","excerpt","","original_coordinate",List.of(1.0),"working_coordinate",List.of(1.0),"coordinate_method","test")))));
    var first=obj(service.qa(map("conversation_id",c.get("id"),"question","深入研究JEPA")));String parent=s(obj(first.get("qa")),"primary_node_id");
    when(ai.call(eq("/qa-ownership"),any())).thenReturn(map("decision","branch","node_id",parent,"title","防坍缩验证实验","research_goal","通过对照实验验证防坍缩假设","distinction","独立可执行验证目标","reason","在JEPA范围内启动独立实验"));
    var result=obj(service.qa(map("conversation_id",c.get("id"),"question","我想开展独立验证实验")));var n=objects(result.get("created_nodes")).get(0);assertEquals(parent,n.get("parent_id"));assertEquals(3,graph.all("nodes").size());assertEquals("独立研究目标",service.node(graph,parent).get("summary"));assertEquals(root,givenAnchor(c));
  }
  @Test void uncertainOwnershipKeepsCurrentNodeAndNoNewBranch(){
    var c=obj(service.conversation(map("space_id",space)));when(ai.call(eq("/research-turn"),any())).thenReturn(map("answer","回答已完整保存","analysis",map("thoughts",List.of(map("text","含糊方向","topic","潜在知识点","excerpt","","original_coordinate",List.of(1.0),"working_coordinate",List.of(1.0),"coordinate_method","test")))));
    when(ai.call(eq("/qa-ownership"),any())).thenReturn(map("decision","uncertain","node_id",root,"reason","研究目标尚不明确"));var result=obj(service.qa(map("conversation_id",c.get("id"),"question","继续聊聊可能的方向")));
    assertEquals(1,graph.all("nodes").size());assertEquals(root,obj(result.get("qa")).get("primary_node_id"));assertEquals("pending",obj(result.get("qa")).get("assignment_status"));assertEquals("回答已完整保存",obj(result.get("qa")).get("answer"));
  }

  @Test void foreignOwnershipCannotCreateOrAttachAcrossSpaces(){
    var other=obj(service.createSpace(map("title","隔离空间","goal","不能跨空间归属")));var c=obj(service.conversation(map("space_id",space)));
    when(ai.call(eq("/research-turn"),any())).thenReturn(map("answer","有效回答","analysis",map("thoughts",List.of(map("text","研究问题","topic","具体问题","excerpt","","original_coordinate",List.of(1.0),"working_coordinate",List.of(1.0),"coordinate_method","test")))));
    when(ai.call(eq("/qa-ownership"),any())).thenReturn(map("decision","branch","node_id",other.get("root_id"),"title","错误跨空间节点","research_goal","目标","distinction","区别","reason","不可信判断"));
    var result=obj(service.qa(map("conversation_id",c.get("id"),"question","讨论研究问题")));assertEquals("有效回答",obj(result.get("qa")).get("answer"));assertEquals(root,obj(result.get("qa")).get("primary_node_id"));assertEquals("pending",obj(result.get("qa")).get("assignment_status"));assertEquals(2,graph.all("nodes").size());assertEquals(1,graph.all("refs").size());
  }

 @Test void parallelDirectionsKeepTheirCommonParentAndHistoryTopology(){
  var c=obj(service.conversation(map("space_id",space)));
  when(ai.call(eq("/research-turn"),any())).thenReturn(map("answer","回答","analysis",map("thoughts",List.of(map("text","研究分类","topic","世界模型分类","original_coordinate",List.of(1.0),"working_coordinate",List.of(1.0),"coordinate_method","test")))));
  String taxonomy=s(obj(obj(service.qa(map("conversation_id",c.get("id"),"question","世界模型有哪些分支"))).get("qa")),"primary_node_id");
  when(ai.call(eq("/qa-ownership"),any())).thenReturn(map("decision","branch","node_id",taxonomy,"branch_relation","child","reference_node_id",taxonomy,"title","像素研究","research_goal","像素技术谱系","distinction","独立研究对象","reason","展开分类方向"));
  String pixel=s(obj(obj(service.qa(map("conversation_id",c.get("id"),"question","像素级深度调研"))).get("qa")),"primary_node_id");
  when(ai.call(eq("/qa-ownership"),any())).thenAnswer(i->{var body=(Map<String,Object>)i.getArgument(1);assertTrue(objects(body.get("candidates")).stream().anyMatch(n->eq(n.get("node_id"),taxonomy)));assertTrue(objects(body.get("history")).stream().anyMatch(h->eq(h.get("primary_node_id"),pixel)));return map("decision","branch","node_id",taxonomy,"branch_relation","sibling","reference_node_id",pixel,"title",body.get("question"),"research_goal","独立技术谱系","distinction","分类下并列方向","reason","并列而非前一方向的子问题");});
  for(String question:List.of("隐空间也深度调研","决策规划类呢")){var result=obj(service.qa(map("conversation_id",c.get("id"),"question",question)));assertEquals(taxonomy,objects(result.get("created_nodes")).get(0).get("parent_id"));}
  assertEquals(3,service.children(graph,taxonomy).size());assertEquals(root,givenAnchor(c));
 }

}
