package cn.xunxu.core;

import cn.xunxu.core.GraphRepository.Graph;
import static cn.xunxu.core.GraphService.*;
import java.util.*;
import java.time.Instant;
import java.util.stream.Collectors;

/** Versioned semantic measurements. Display projections never determine graph parents. */
final class ThoughtSpaceEngine {
  static final double CANDIDATE_SIMILARITY=0.60;
  final GraphService core; final AiClient ai;
  ThoughtSpaceEngine(GraphService core,AiClient ai){this.core=core;this.ai=ai;}
  @SuppressWarnings("unchecked") static List<Number> vector(Map<String,Object> c){return (List<Number>)c.get("vector");}
  static double cosine(List<Number> a,List<Number> b){check(a.size()==b.size()&&!a.isEmpty(),"不可比较不同维度的思想坐标");double dot=0,an=0,bn=0;for(int i=0;i<a.size();i++){double x=a.get(i).doubleValue(),y=b.get(i).doubleValue();check(Double.isFinite(x)&&Double.isFinite(y),"非法坐标");dot+=x*y;an+=x*x;bn+=y*y;}check(an>0&&bn>0,"零向量不能度量语义");return Math.max(-1,Math.min(1,dot/Math.sqrt(an*bn)));}
  static boolean compatible(Map<String,Object> a,Map<String,Object>b){return eq(a.get("method"),b.get("method"))&&eq(a.get("dimension"),b.get("dimension"))&&flag(a,"semantic")&&flag(b,"semantic");}
  Map<String,Object> register(Graph g,Map<String,Object> thought,String anchor,Object raw,String method,boolean semantic){
    check(raw instanceof List<?> v&&!v.isEmpty()&&v.size()<=4096&&v.stream().allMatch(x->x instanceof Number n&&Double.isFinite(n.doubleValue())),"思想空间坐标不合法");
    String input=s(thought,"text"),key="coord_"+digest(s(thought,"id")+"|"+method+"|"+anchor+"|"+input).substring(0,24);
    if(g.rows.get("thought_coordinates").containsKey(key))return g.get("thought_coordinates",key);
    var concepts=(List<?>)thought.getOrDefault("core_concepts",List.of(thought.get("topic")));var encoded=ai.call("/coordinates",map("texts",concepts));check(eq(encoded.get("method"),method),"核心概念与思想须使用同一语义模型");var conceptVectors=(List<?>)encoded.get("vectors");var conceptCoordinates=new ArrayList<Map<String,Object>>();for(int i=0;i<concepts.size();i++)conceptCoordinates.add(map("concept",concepts.get(i),"vector",conceptVectors.get(i)));
    var c=map("id",key,"concept_coordinates",conceptCoordinates,"thought_id",thought.get("id"),"qa_id",thought.get("qa_id"),"space_id",core.node(g,anchor).get("space_id"),"anchor_id",anchor,"method",method,"dimension",((List<?>)raw).size(),"semantic",semantic,"vector",raw,"input_digest",digest(input),"core_concepts",thought.getOrDefault("core_concepts",List.of(thought.get("topic"))),"kind","semantic_encoding_version","created_at",now());
    g.put("thought_coordinates",c);return c;
  }
  List<Map<String,Object>> latest(Graph g,String sid){
    var chosen=new LinkedHashMap<String,Map<String,Object>>();
    for(var c:g.all("thought_coordinates")){if(!eq(g.get("thoughts",s(c,"thought_id")).get("role"),"main"))continue;String anchor=s(c,"anchor_id");if(!g.rows.get("nodes").containsKey(anchor)||!eq(core.node(g,anchor).get("space_id"),sid)||!flag(c,"semantic"))continue;
      String tid=s(c,"thought_id");var old=chosen.get(tid);if(old==null||Instant.parse(s(c,"created_at")).isAfter(Instant.parse(s(old,"created_at"))))chosen.put(tid,c);}
    return chosen.values().stream().sorted(Comparator.comparing(c->s(c,"thought_id"))).toList();
  }
  String pairId(Map<String,Object>a,Map<String,Object>b){var ids=new ArrayList<>(List.of(s(a,"id"),s(b,"id")));Collections.sort(ids);return "link_"+digest(String.join("|",ids)).substring(0,24);}
  Map<String,Object> description(Graph g,Map<String,Object> c){var t=g.get("thoughts",s(c,"thought_id"));return map("role",t.get("role"),"text",t.get("text"),"topic",t.get("topic"),"core_concepts",c.get("core_concepts"),"question",g.get("qas",s(t,"qa_id")).get("question"));}
  boolean sameContext(Graph g,Map<String,Object>a,Map<String,Object>b){return eq(a.get("anchor_id"),b.get("anchor_id"))&&eq(core.node(g,s(a,"anchor_id")).get("space_id"),core.node(g,s(b,"anchor_id")).get("space_id"));}
  List<Map<String,Object>> grow(Graph g,String sid){return grow(g,sid,null);}
  List<Map<String,Object>> grow(Graph g,String sid,String triggerQa){
    var coords=latest(g,sid).stream().filter(c->eq(g.get("thoughts",s(c,"thought_id")).get("role"),"main")).toList();var pending=new LinkedHashMap<String,List<Map<String,Object>>>();
    for(int i=0;i<coords.size();i++)for(int j=i+1;j<coords.size();j++){
      var a=coords.get(i);var b=coords.get(j);if(!compatible(a,b)||!sameContext(g,a,b))continue;
      String pid=pairId(a,b);boolean mainPair=eq(g.get("thoughts",s(a,"thought_id")).get("role"),"main")&&eq(g.get("thoughts",s(b,"thought_id")).get("role"),"main");var prior=g.rows.get("thought_links").get(pid);if(prior!=null){if(mainPair&&!eq(prior.get("direction_version"),1)&&cosine(vector(a),vector(b))>=CANDIDATE_SIMILARITY&&!eq(a.get("qa_id"),b.get("qa_id")))pending.computeIfAbsent(s(a,"anchor_id"),k->new ArrayList<>()).add(map("id",pid,"left",description(g,a),"right",description(g,b)));continue;}
      double sim=cosine(vector(a),vector(b));String decision="not_evaluated",reason="距离尚未进入意图判断候选范围";
      if(eq(a.get("qa_id"),b.get("qa_id"))){decision="related";reason="同一问答的多个思想不能替代多个独立问答证据";}
      var link=map("id",pid,"space_id",sid,"a",a.get("thought_id"),"b",b.get("thought_id"),"coordinate_a",a.get("id"),"coordinate_b",b.get("id"),"method",a.get("method"),"similarity",sim,"distance",1-sim,"same_context",true,"decision",decision,"reason",reason,"created_at",now());
      g.put("thought_links",link);
      if(sim>=CANDIDATE_SIMILARITY&&!eq(a.get("qa_id"),b.get("qa_id")))pending.computeIfAbsent(s(a,"anchor_id"),k->new ArrayList<>()).add(map("id",pid,"left",description(g,a),"right",description(g,b)));
    }
    for(var entry:pending.entrySet())for(int start=0;start<entry.getValue().size();start+=10){var pairs=entry.getValue().subList(start,Math.min(start+10,entry.getValue().size()));var result=ai.call("/intent-matches",map("pairs",pairs,"context",core.scoped(g,entry.getKey())));var allowed=pairs.stream().map(p->s(p,"id")).collect(Collectors.toSet());var decisions=objects(result.get("decisions"));check(decisions.size()==allowed.size(),"意图判定数量不一致");var seen=new HashSet<String>();for(var d:decisions){String pid=s(d,"id"),decision=s(d,"decision");check(allowed.contains(pid)&&seen.add(pid)&&List.of("same_intent","related","distinct","not_evaluated").contains(decision),"意图判定无效");var link=g.get("thought_links",pid);link.put("decision",decision);link.put("reason",text(d.get("reason"),"判断依据"));link.put("direction_checked",true);link.put("direction_version",1);link.put("direction_title",d.getOrDefault("direction_title",""));link.put("direction_reason",d.getOrDefault("direction_reason",""));}}
    var created=new ArrayList<Map<String,Object>>();
    // Complete-link assignment prevents a broad bridging thought from chaining unrelated questions.
    var groups=new ArrayList<List<Map<String,Object>>>();
    for(var c:coords){List<Map<String,Object>> target=null;for(var group:groups){boolean fits=true;for(var member:group){if(!compatible(c,member)||!sameContext(g,c,member)){fits=false;break;}var link=g.rows.get("thought_links").get(pairId(c,member));if(link==null||!eq(link.get("decision"),"same_intent")){fits=false;break;}}if(fits){target=group;break;}}if(target==null){target=new ArrayList<>();groups.add(target);}target.add(c);}
    for(var group:groups){var first=group.get(0);String anchor=s(first,"anchor_id"),method=s(first,"method");var tids=group.stream().map(c->s(c,"thought_id")).toList();
      var existing=g.all("clusters").stream().filter(c->eq(c.get("basis"),"semantic")&&eq(c.get("anchor_id"),anchor)&&eq(c.get("coordinate_method"),method)&&strings(c,"members").stream().anyMatch(tids::contains)).toList();
      // Never join two already materialized nodes: that remains a human structural operation.
      var holders=g.all("clusters").stream().filter(c->!eq(c.get("basis"),"research_direction")&&eq(c.get("anchor_id"),anchor)&&c.get("node_id")!=null&&strings(c,"members").stream().anyMatch(tids::contains)).map(c->s(c,"node_id")).distinct().toList();if(holders.size()>1)continue;
      var cluster=existing.stream().filter(c->c.get("node_id")!=null).findFirst().orElse(existing.isEmpty()?null:existing.get(0));
      if(cluster==null){cluster=map("id",id("cluster"),"space_id",sid,"anchor_id",anchor,"topic",g.get("thoughts",s(first,"thought_id")).get("topic"),"members",new ArrayList<String>(),"node_id",null,"version",0,"basis","semantic","coordinate_method",method);g.put("clusters",cluster);}
      // Accumulation is allowed only for this consistent group; existing evidence is never removed.
      var members=strings(cluster,"members");for(String tid:tids)if(!members.contains(tid))members.add(tid);
      cluster.put("version",number(cluster,"version")+1);cluster.put("updated_at",now());
      var distinct=members.stream().map(tid->g.get("thoughts",tid).get("qa_id")).collect(Collectors.toSet());cluster.put("distinct_qa_count",distinct.size());
      if(cluster.get("node_id")==null&&!holders.isEmpty())cluster.put("node_id",holders.get(0));
      try{core.open(g,anchor);}catch(IllegalArgumentException frozen){continue;}
      if(cluster.get("node_id")!=null){String target=s(cluster,"node_id");try{core.open(g,target);}catch(IllegalArgumentException frozen){continue;}for(String tid:members)core.ref(g,target,s(g.get("thoughts",tid),"qa_id"),tid,"strong").put("strength","strong");}
    }
    created.addAll(core.assignQaNodes(g,sid));
    new GrowthPlacementEngine(core,ai).place(g,sid,created);
    return created;
  }
  // Direction evidence is independent of exact-intent clusters; it never reparents existing nodes.
  List<Map<String,Object>> growDirections(Graph g,String sid,List<Map<String,Object>> coords,String triggerQa){
    var created=new ArrayList<Map<String,Object>>();var groups=new LinkedHashMap<String,List<Map<String,Object>>>();
    for(var link:g.all("thought_links")){String title=Objects.toString(link.get("direction_title"),"").trim();if(title.isEmpty()||!eq(link.get("space_id"),sid))continue;
      var a=coords.stream().filter(c->eq(c.get("id"),link.get("coordinate_a"))).findFirst().orElse(null);var b=coords.stream().filter(c->eq(c.get("id"),link.get("coordinate_b"))).findFirst().orElse(null);if(a==null||b==null||!sameContext(g,a,b)||eq(a.get("qa_id"),b.get("qa_id"))||!eq(g.get("thoughts",s(a,"thought_id")).get("role"),"main")||!eq(g.get("thoughts",s(b,"thought_id")).get("role"),"main"))continue;
      String key=s(a,"anchor_id")+"|"+title;var group=groups.computeIfAbsent(key,k->new ArrayList<>());
      for(var candidate:List.of(a,b)){if(group.contains(candidate))continue;boolean fits=group.stream().allMatch(member->eq(member.get("id"),candidate.get("id"))||Optional.ofNullable(g.rows.get("thought_links").get(pairId(candidate,member))).map(pair->eq(pair.get("direction_title"),title)).orElse(false));if(fits)group.add(candidate);}
    }
    for(var entry:groups.entrySet()){var members=entry.getValue();if(members.stream().map(c->s(c,"qa_id")).distinct().count()<2)continue;String anchor=s(members.get(0),"anchor_id"),title=entry.getKey().substring(anchor.length()+1);
      try{core.open(g,anchor);}catch(IllegalArgumentException frozen){continue;}
      var cluster=g.all("clusters").stream().filter(c->eq(c.get("basis"),"research_direction")&&eq(c.get("anchor_id"),anchor)&&eq(c.get("topic"),title)).findFirst().orElse(null);
      if(cluster==null){cluster=map("id",id("cluster"),"space_id",sid,"anchor_id",anchor,"topic",title,"members",new ArrayList<String>(),"node_id",null,"version",0,"basis","research_direction");g.put("clusters",cluster);}
      var tids=strings(cluster,"members");for(var c:members)if(!tids.contains(s(c,"thought_id")))tids.add(s(c,"thought_id"));int count=(int)tids.stream().map(t->s(g.get("thoughts",t),"qa_id")).distinct().count();cluster.put("distinct_qa_count",count);cluster.put("version",number(cluster,"version")+1);
      if(cluster.get("node_id")==null){String content=tids.stream().map(t->s(g.get("qas",s(g.get("thoughts",t),"qa_id")),"question")).distinct().collect(Collectors.joining("\n\n"));var n=core.newNode(g,map("parent_id",anchor,"title",title,"summary","研究方向："+title+"。以下直接问答共同支持这一方向：\n\n"+content,"reason","研究方向簇："+count+" 个独立问答；主思想高维语义候选＋原始问题的共同研究方向校验；具体问题允许不同；来源 "+cluster.get("id")),"research_direction_cluster",new ArrayList<>(tids));if(triggerQa!=null)n.put("created_by_qa_id",triggerQa);n.put("research_level","direction");cluster.put("node_id",n.get("id"));created.add(n);}
      String target=s(cluster,"node_id");try{core.open(g,target);}catch(IllegalArgumentException frozen){continue;}for(String tid:tids)core.ref(g,target,s(g.get("thoughts",tid),"qa_id"),tid,"strong").put("strength","strong");
    }return created;
  }
  Object reindex(String sid){return core.repo.write(g->{g.get("spaces",sid);var refs=g.all("refs").stream().filter(r->eq(core.node(g,s(r,"node_id")).get("space_id"),sid)).toList();var ids=refs.stream().map(r->s(r,"thought_id")).collect(Collectors.toSet());var thoughts=g.all("thoughts").stream().filter(t->ids.contains(s(t,"id"))&&eq(t.get("role"),"main")).sorted(Comparator.comparing(t->s(t,"id"))).toList();check(thoughts.size()<=1000,"请分批量化大规模空间");int added=0;var health=ai.health();String activeMethod=health.get("embedding") instanceof Map<?,?> e?Objects.toString(e.get("method"),null):null;var encodedIds=latest(g,sid).stream().filter(c->eq(c.get("method"),activeMethod)).map(c->s(c,"thought_id")).collect(Collectors.toSet());var pendingThoughts=thoughts.stream().filter(t->!encodedIds.contains(s(t,"id"))).toList();
    for(int start=0;start<pendingThoughts.size();start+=128){var batch=pendingThoughts.subList(start,Math.min(start+128,pendingThoughts.size()));var missing=batch.stream().filter(t->!t.containsKey("core_concepts")).toList();var enriched=new HashMap<String,Object>();for(int offset=0;offset<missing.size();offset+=30){var chunk=missing.subList(offset,Math.min(offset+30,missing.size()));var extraction=ai.call("/concepts",map("thoughts",chunk.stream().map(t->map("id",t.get("id"),"text",t.get("text"),"topic",t.get("topic"))).toList()));for(var row:objects(extraction.get("concepts")))enriched.put(s(row,"id"),row.get("core_concepts"));}var response=ai.call("/coordinates",map("texts",batch.stream().map(t->t.get("text")).toList()));var vectors=(List<?>)response.get("vectors");check(vectors.size()==batch.size()&&flag(response,"semantic_embedding"),"需要真实语义嵌入");for(int i=0;i<batch.size();i++){var t=batch.get(i);var q=g.get("qas",s(t,"qa_id"));String anchor=s(g.get("conversations",s(q,"conversation_id")),"anchor_id");if(!eq(core.node(g,anchor).get("space_id"),sid)){anchor=refs.stream().filter(r->eq(r.get("thought_id"),t.get("id"))).map(r->s(r,"node_id")).findFirst().orElseThrow();}int before=g.all("thought_coordinates").size();var encodingInput=new LinkedHashMap<>(t);if(enriched.containsKey(s(t,"id")))encodingInput.put("core_concepts",enriched.get(s(t,"id")));register(g,encodingInput,anchor,vectors.get(i),s(response,"method"),true);added+=g.all("thought_coordinates").size()-before;}}
    var nodes=grow(g,sid);for(var status:g.all("relations"))if(eq(status.get("type"),"qa_growth_status")&&eq(status.get("space_id"),sid)&&eq(status.get("status"),"pending")){status.put("status","complete");status.put("updated_at",now());}core.audit(g,"quantify_thought_space",map("coordinate_versions_added",added,"thought_count",thoughts.size(),"created_nodes",nodes.stream().map(n->n.get("id")).toList(),"birth_coordinates_preserved",true),sid);return map("ok",true,"coordinates_added",added,"created_nodes",nodes,"thought_count",thoughts.size());});}
  Object view(String sid){return core.repo.read(g->{g.get("spaces",sid);var coords=latest(g,sid);String method=coords.isEmpty()?null:s(coords.get(coords.size()-1),"method");var visible=coords.stream().filter(c->eq(c.get("method"),method)).toList();var projected=visible.isEmpty()?map("points",List.of(),"explained_variance",List.of()):ai.call("/project",map("vectors",visible.stream().map(c->c.get("vector")).toList()));var xy=objects(projected.get("points"));var points=new ArrayList<Map<String,Object>>();var tids=visible.stream().map(c->s(c,"thought_id")).collect(Collectors.toSet());
    for(int i=0;i<visible.size();i++){var c=visible.get(i);var t=g.get("thoughts",s(c,"thought_id"));var q=g.get("qas",s(t,"qa_id"));var cluster=g.all("clusters").stream().filter(k->(eq(k.get("basis"),"research_direction")||(eq(k.get("basis"),"semantic")&&eq(k.get("coordinate_method"),method)))&&strings(k,"members").contains(s(t,"id"))).sorted(Comparator.comparingInt(k->k.get("node_id")==null?2:eq(k.get("basis"),"semantic")?0:1)).findFirst().orElse(Map.of());points.add(map("id",t.get("id"),"coordinate_id",c.get("id"),"thought_id",t.get("id"),"qa_id",q.get("id"),"conversation_id",q.get("conversation_id"),"concept_coordinates",c.get("concept_coordinates"),"question",q.get("question"),"title",t.get("topic"),"text",t.get("text"),"role",t.get("role"),"core_concepts",c.get("core_concepts"),"x",xy.get(i).get("x"),"y",xy.get(i).get("y"),"cluster_id",cluster.get("id"),"node_id",cluster.get("node_id"),"birth_method",t.get("vector_method")));}
    var pairs=new ArrayList<Map<String,Object>>();for(int i=0;i<visible.size();i++)for(int j=i+1;j<visible.size();j++){var a=visible.get(i);var b=visible.get(j);if(!compatible(a,b))continue;var saved=g.rows.get("thought_links").get(pairId(a,b));double sim=cosine(vector(a),vector(b));pairs.add(saved==null?map("a",a.get("thought_id"),"b",b.get("thought_id"),"similarity",sim,"distance",1-sim,"same_context",sameContext(g,a,b),"decision","not_evaluated","reason","尚未进行同意图判定"):saved);}
    var clusters=g.all("clusters").stream().filter(c->(eq(c.get("basis"),"research_direction")||(eq(c.get("basis"),"semantic")&&eq(c.get("coordinate_method"),method)))&&strings(c,"members").stream().anyMatch(tids::contains)).map(c->map("basis",c.get("basis"),"id",c.get("id"),"title",c.get("topic"),"thought_ids",c.get("members"),"qa_count",c.get("distinct_qa_count"),"node_id",c.get("node_id"))).toList();return map("model",map("method",method,"dimension",visible.isEmpty()?0:visible.get(0).get("dimension"),"semantic",!visible.isEmpty(),"projection","PCA-2D"),"points",points,"pairs",pairs,"clusters",clusters,"status",visible.isEmpty()?"not_indexed":"ready","explained_variance",projected.get("explained_variance"),"thresholds",map("candidate_similarity",CANDIDATE_SIMILARITY),"warning","投影仅用于观察；距离不等于研究意图或父子关系");});}
}
