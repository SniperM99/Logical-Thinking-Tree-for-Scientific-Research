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
    assertEquals(0,objects(second.get("created_nodes")).size());verify(ai,never()).call(eq("/chat"),any());verify(ai,never()).call(eq("/analyze"),any());
    var restored=obj(service.conversation(s(conv,"id")));assertEquals(2,restored.get("turn_count"));
    var saved=obj(obj(restored.get("assessments")).get(s(obj(first.get("qa")),"id")));
    assertEquals(0,objects(saved.get("created_nodes")).size()); // Later growth must not rewrite the earlier judgment.
    assertEquals(root,obj(restored.get("conversation")).get("anchor_id"));
    var qaViews=objects(restored.get("qas"));assertNull(qaViews.get(0).get("primary_node_id"));assertNull(qaViews.get(1).get("primary_node_id"));assertEquals(1,graph.all("nodes").size());assertTrue(graph.all("refs").isEmpty());assertTrue(graph.all("relations").isEmpty());verify(ai,never()).call(eq("/qa-ownership"),any());verify(ai,never()).call(eq("/growth-placements"),any());
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

}
