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
 @BeforeEach @SuppressWarnings("unchecked") void setup(){g=new Graph();var repo=mock(GraphRepository.class);ai=mock(AiClient.class);var json=new ObjectMapper();when(repo.write(any())).thenAnswer(i->((Function<Graph,Object>)i.getArgument(0)).apply(g));when(repo.encode(any())).thenAnswer(i->json.writeValueAsString(i.getArgument(0)));core=new GraphService(repo,ai);var sp=obj(core.createSpace(map("title","量化测试","goal","保持祖先总结")));sid=s(sp,"id");root=s(sp,"root_id");engine=core.thoughtSpace;when(ai.call(eq("/coordinates"),any())).thenAnswer(i->{var body=(Map<String,Object>)i.getArgument(1);return map("method","semantic-test","vectors",((List<?>)body.get("texts")).stream().map(x->List.of(1.0,0.0)).toList());});when(ai.call(eq("/intent-matches"),any())).thenAnswer(i->{var body=(Map<String,Object>)i.getArgument(1);return map("decisions",objects(body.get("pairs")).stream().map(p->map("id",p.get("id"),"decision","same_intent","reason","同一个研究问题的不同表述")).toList());});}
 Map<String,Object> thought(String qa,String title,String anchor,String space){if(!g.rows.get("qas").containsKey(qa))g.put("qas",map("id",qa,"question","验证表征预测","space_id",space));var t=map("id",id("thought"),"qa_id",qa,"text",title,"topic",title,"space_id",space,"original_vector",List.of(0.3,0.7),"vector_method","old-hash","core_concepts",List.of("表征预测"));g.put("thoughts",t);return engine.register(g,t,anchor,List.of(1.0,0.0),"semantic-test",true);}
 @Test void actualDistanceAndModelIsolation(){assertEquals(0,ThoughtSpaceEngine.cosine(List.of(1,0),List.of(0,1)));assertThrows(IllegalArgumentException.class,()->ThoughtSpaceEngine.cosine(List.of(1),List.of(1,0)));assertFalse(ThoughtSpaceEngine.compatible(map("method","A","dimension",2,"semantic",true),map("method","B","dimension",2,"semantic",true)));}
 @Test void twoDifferentQaParaphrasesGrowOnceAndPreserveBirth(){var a=thought("q1","研究JEPA如何预测表示",root,sid);var original=new ArrayList<>((List<?>)g.get("thoughts",s(a,"thought_id")).get("original_vector"));thought("q2","潜在空间的联合嵌入预测机制",root,sid);assertEquals(1,engine.grow(g,sid).size());assertEquals(0,engine.grow(g,sid).size());assertEquals(original,g.get("thoughts",s(a,"thought_id")).get("original_vector"));assertEquals("保持祖先总结",core.node(g,root).get("summary"));}
 @Test void sameQaCannotBecomeIndependentEvidence(){thought("q1","JEPA机制一",root,sid);thought("q1","JEPA机制二",root,sid);assertTrue(engine.grow(g,sid).isEmpty());verify(ai,never()).call(eq("/intent-matches"),any());}
 @Test void sharedObjectAndSeparateContextDoNotForceGrowth(){thought("q1","JEPA机制",root,sid);thought("q2","JEPA应用",root,sid);when(ai.call(eq("/intent-matches"),any())).thenAnswer(i->{var body=(Map<String,Object>)i.getArgument(1);return map("decisions",objects(body.get("pairs")).stream().map(p->map("id",p.get("id"),"decision","related","reason","共享对象但问题不同")).toList());});assertTrue(engine.grow(g,sid).isEmpty());var sp=obj(core.createSpace(map("title","另一空间","goal","隔离")));thought("q3","JEPA机制",s(sp,"root_id"),s(sp,"id"));assertTrue(engine.grow(g,s(sp,"id")).isEmpty());}
}
