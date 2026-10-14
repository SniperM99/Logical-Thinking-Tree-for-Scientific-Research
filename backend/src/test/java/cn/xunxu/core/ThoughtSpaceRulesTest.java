package cn.xunxu.core;
import static cn.xunxu.core.GraphService.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import org.junit.jupiter.api.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import cn.xunxu.core.GraphRepository.Graph;
import java.util.function.Function;
import java.util.*;
class ThoughtSpaceRulesTest {
 Graph g;GraphService core;AiClient ai;String sid,root;ThoughtSpaceEngine engine;
 @BeforeEach @SuppressWarnings("unchecked") void setup(){g=new Graph();var repo=mock(GraphRepository.class);ai=mock(AiClient.class);var json=new ObjectMapper();when(repo.write(any())).thenAnswer(i->((Function<Graph,Object>)i.getArgument(0)).apply(g));when(repo.encode(any())).thenAnswer(i->json.writeValueAsString(i.getArgument(0)));core=new GraphService(repo,ai);var sp=obj(core.createSpace(map("title","量化测试","goal","保持祖先总结")));sid=s(sp,"id");root=s(sp,"root_id");engine=core.thoughtSpace;when(ai.call(eq("/coordinates"),any())).thenAnswer(i->{var body=(Map<String,Object>)i.getArgument(1);return map("method","semantic-test","vectors",((List<?>)body.get("texts")).stream().map(x->List.of(1.0,0.0)).toList());});}

 Map<String,Object> thought(String qa,String title,String anchor,String space){boolean first=!g.rows.get("qas").containsKey(qa);String cid="conv_"+anchor;if(!g.rows.get("conversations").containsKey(cid))g.put("conversations",map("id",cid,"space_id",space,"anchor_id",anchor));if(first)g.put("qas",map("id",qa,"turn_index",g.all("qas").size()+1,"question","验证表征预测","space_id",space,"conversation_id",cid));var t=map("id",id("thought"),"role",first?"main":"auxiliary","qa_id",qa,"text",title,"topic",title,"space_id",space,"original_vector",List.of(0.3,0.7),"vector_method","old-hash","core_concepts",List.of("表征预测"));g.put("thoughts",t);return engine.register(g,t,anchor,List.of(1.0,0.0),"semantic-test",true);}
 @Test void actualDistanceAndModelIsolation(){assertEquals(0,ThoughtSpaceEngine.cosine(List.of(1,0),List.of(0,1)));assertThrows(IllegalArgumentException.class,()->ThoughtSpaceEngine.cosine(List.of(1),List.of(1,0)));assertFalse(ThoughtSpaceEngine.compatible(map("method","A","dimension",2,"semantic",true),map("method","B","dimension",2,"semantic",true)));}

 @Test void reindexUnassignedQuestionsOnlyChangesMeasurements(){
  thought("q1","像素空间",root,sid);thought("q2","隐空间",root,sid);
  when(ai.health()).thenReturn(map("embedding",map("method","semantic-test")));
  int nodes=g.all("nodes").size();var result=obj(engine.reindex(sid));
  assertEquals(2,result.get("thought_count"));assertTrue(objects(result.get("created_nodes")).isEmpty());assertEquals(nodes,g.all("nodes").size());assertTrue(g.all("refs").isEmpty());assertTrue(g.all("clusters").isEmpty());assertTrue(g.all("relations").isEmpty());verify(ai,never()).call(eq("/intent-matches"),any());verify(ai,never()).call(eq("/qa-ownership"),any());
 }

}
