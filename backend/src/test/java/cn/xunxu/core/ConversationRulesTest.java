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
  @BeforeEach @SuppressWarnings("unchecked") void setup(){graph=new Graph();repository=mock(GraphRepository.class);ai=mock(AiClient.class);var mapper=new ObjectMapper();when(repository.write(any())).thenAnswer(inv->{Object result=((Function<Graph,Object>)inv.getArgument(0)).apply(graph);graph.revision++;return result;});when(repository.read(any())).thenAnswer(inv->((Function<Graph,Object>)inv.getArgument(0)).apply(graph));when(repository.encode(any())).thenAnswer(inv->mapper.writeValueAsString(inv.getArgument(0)));when(repository.decode(anyString())).thenAnswer(inv->mapper.readValue((String)inv.getArgument(0),Map.class));service=new GraphService(repository,ai);var sp=obj(service.createSpace(map("title","会话测试","goal","ROOT_CONTEXT")));root=s(sp,"root_id");space=s(sp,"id");}

  @Test void spaceEntryKeepsRootAndEachTurnAssessment(){
    var conv=obj(service.conversation(map("space_id",space)));
    assertEquals(root,conv.get("anchor_id"));assertEquals("space",conv.get("origin_scope"));
    when(ai.call(eq("/research-turn"),any())).thenReturn(map("answer","模型回答","analysis",map("thoughts",List.of(map("text","具体研究方向","topic","控制变量实验","excerpt","","original_coordinate",List.of(1.0,0.0),"working_coordinate",List.of(1.0,0.0),"coordinate_method","test")))));
    var d=map("conversation_id",conv.get("id"),"question","验证实验假设","request_id","turn1","expected_turn_index",0);
    var first=obj(service.qa(d));
    var second=obj(service.qa(map("conversation_id",conv.get("id"),"question","继续验证同一假设","request_id","turn2","expected_turn_index",1)));
    assertEquals(1,objects(second.get("created_nodes")).size());verify(ai,never()).call(eq("/chat"),any());verify(ai,never()).call(eq("/analyze"),any());
    var restored=obj(service.conversation(s(conv,"id")));assertEquals(2,restored.get("turn_count"));
    var saved=obj(obj(restored.get("assessments")).get(s(obj(first.get("qa")),"id")));
    assertEquals(0,objects(saved.get("created_nodes")).size()); // Later growth must not rewrite the earlier judgment.
    assertEquals(root,obj(restored.get("conversation")).get("anchor_id"));
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
    when(ai.call(eq("/intent-matches"),any())).thenThrow(new AiClient.AiFailure("研究方向判断字段缺失"));
    var result=obj(service.qa(map("conversation_id",conv.get("id"),"question","研究机制第二轮","request_id","saved2")));var qa=obj(result.get("qa"));String qid=s(qa,"id");
    assertEquals("有效回答",qa.get("answer"));assertEquals("pending",obj(result.get("growth_status")).get("status"));assertEquals(2,graph.all("qas").size());assertEquals(2,graph.all("thoughts").size());assertTrue(graph.all("thought_links").isEmpty());assertEquals(1,graph.all("nodes").size());
    var originalQa=new LinkedHashMap<>(graph.get("qas",qid));when(ai.call(eq("/intent-matches"),any())).thenAnswer(i->{var body=(Map<String,Object>)i.getArgument(1);return map("decisions",objects(body.get("pairs")).stream().map(p->map("id",p.get("id"),"decision","same_intent","reason","同一问题")).toList());});
    var retry=obj(service.retryGrowth(qid));assertEquals("complete",obj(retry.get("growth_status")).get("status"));assertEquals(originalQa,graph.get("qas",qid));assertEquals(1,objects(retry.get("created_nodes")).size());verify(ai,times(2)).call(eq("/research-turn"),any());
  }
}
