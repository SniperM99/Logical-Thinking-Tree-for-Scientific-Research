package cn.xunxu.core;

import cn.xunxu.core.GraphRepository.Graph;
import static cn.xunxu.core.GraphService.*;
import java.util.*;

/** Decide research ownership before creating a node; never mutate original QA or its anchor. */
final class QaOwnershipEngine {
  final GraphService core; final AiClient ai;
  QaOwnershipEngine(GraphService core,AiClient ai){this.core=core;this.ai=ai;}
  String current(Graph g,Map<String,Object> conversation,Map<String,Object> before){
    var history=g.all("qas").stream().filter(q->eq(q.get("conversation_id"),conversation.get("id"))&&(before==null||number(q,"turn_index")<number(before,"turn_index"))).sorted(Comparator.comparingLong((Map<String,Object> q)->number(q,"turn_index")).reversed()).toList();
    for(var q:history){var r=g.rows.get("relations").get("qa_primary_"+s(q,"id"));if(r!=null&&usable(g,s(r,"target_id"),s(conversation,"space_id")))return s(r,"target_id");}
    return s(conversation,"anchor_id");
  }
  boolean usable(Graph g,String id,String sid){if(id==null||!g.rows.get("nodes").containsKey(id))return false;var n=core.node(g,id);if(!eq(n.get("space_id"),sid)||flag(n,"hidden")||flag(n,"archived"))return false;try{core.open(g,id);return true;}catch(IllegalArgumentException e){return false;}}
  List<Map<String,Object>> assign(Graph g,String sid,String onlyQa){
    var created=new ArrayList<Map<String,Object>>();
    var questions=new ArrayList<>(g.all("qas"));questions.sort(Comparator.comparing(q->Objects.toString(q.get("created_at"),"")));
    for(var q:questions){String qid=s(q,"id");if(!eq(q.get("space_id"),sid)||(onlyQa!=null&&!eq(qid,onlyQa)))continue;var previous=g.rows.get("relations").get("qa_primary_"+qid);if(previous!=null&&!eq(previous.get("assignment_status"),"pending"))continue;
      var main=g.all("thoughts").stream().filter(t->eq(t.get("qa_id"),qid)&&eq(t.get("role"),"main")).findFirst().orElse(null);if(main==null)continue;
      var conv=g.get("conversations",s(q,"conversation_id"));String active=current(g,conv,q);core.open(g,active);
      var candidates=new ArrayList<Map<String,Object>>();var source=core.thoughtSpace.latest(g,sid).stream().filter(c->eq(c.get("thought_id"),main.get("id"))).findFirst().orElse(null);
      for(var n:g.all("nodes")){String nid=s(n,"id");if(!usable(g,nid,sid))continue;if(q.get("created_at")!=null&&n.get("created_at")!=null&&java.time.Instant.parse(s(n,"created_at")).isAfter(java.time.Instant.parse(s(q,"created_at"))))continue;
        var evidence=g.all("qas").stream().filter(prior->{var r=g.rows.get("relations").get("qa_primary_"+s(prior,"id"));return r!=null&&eq(r.get("target_id"),nid)&&!eq(prior.get("id"),qid)&&(eq(prior.get("conversation_id"),q.get("conversation_id"))?number(prior,"turn_index")<number(q,"turn_index"):prior.get("created_at")!=null&&q.get("created_at")!=null&&java.time.Instant.parse(s(prior,"created_at")).isBefore(java.time.Instant.parse(s(q,"created_at"))));}).toList();
        double similarity=-1;if(source!=null)for(var c:core.thoughtSpace.latest(g,sid)){var owner=g.rows.get("relations").get("qa_primary_"+s(c,"qa_id"));if(owner!=null&&eq(owner.get("target_id"),nid)&&evidence.stream().anyMatch(e->eq(e.get("id"),c.get("qa_id")))&&ThoughtSpaceEngine.compatible(source,c))similarity=Math.max(similarity,ThoughtSpaceEngine.cosine(ThoughtSpaceEngine.vector(source),ThoughtSpaceEngine.vector(c)));}
        candidates.add(map("node_id",nid,"parent_id",n.get("parent_id"),"ancestor_ids",ancestorIds(g,nid),"title",n.get("title"),"research_goal",n.get("summary"),"similarity",similarity,"is_current",eq(nid,active),"is_space_entry",eq(nid,g.get("spaces",sid).get("root_id")),"evidence",evidence.stream().map(e->map("qa_id",e.get("id"),"turn_index",e.get("turn_index"),"question",e.get("question"))).toList()));
      }
      if(source!=null)for(int offset=0;offset<candidates.size();offset+=128){var batch=candidates.subList(offset,Math.min(offset+128,candidates.size()));var encoded=ai.call("/coordinates",map("texts",batch.stream().map(c->c.get("title")).toList()));if(encoded!=null&&eq(encoded.get("method"),source.get("method"))&&encoded.get("vectors") instanceof List<?> vectors&&vectors.size()==batch.size()){for(int i=0;i<batch.size();i++){var raw=(List<?>)vectors.get(i);if(raw.size()==ThoughtSpaceEngine.vector(source).size()&&raw.stream().allMatch(v->v instanceof Number)){var vector=new ArrayList<Number>();for(var v:raw)vector.add((Number)v);double sim=ThoughtSpaceEngine.cosine(ThoughtSpaceEngine.vector(source),vector);batch.get(i).put("similarity",Math.max(((Number)batch.get(i).get("similarity")).doubleValue(),sim));}}}}
      candidates.sort(Comparator.comparingDouble((Map<String,Object> c)->((Number)c.get("similarity")).doubleValue()).reversed());
      var required=new LinkedHashSet<String>();required.add(active);required.addAll(ancestorIds(g,active));required.add(s(conv,"anchor_id"));var shortlist=new ArrayList<Map<String,Object>>();for(String id:required)for(var c:candidates)if(eq(c.get("node_id"),id)&&shortlist.size()<32)shortlist.add(c);for(var c:candidates)if(shortlist.size()<Math.max(8,required.size())&&shortlist.size()<32&&!shortlist.contains(c))shortlist.add(c);
      var history=g.all("qas").stream().filter(p->eq(p.get("conversation_id"),q.get("conversation_id"))&&number(p,"turn_index")<number(q,"turn_index")).sorted(Comparator.comparingLong(p->number(p,"turn_index"))).toList();if(history.size()>8)history=history.subList(history.size()-8,history.size());
      var request=map("qa_id",qid,"question",q.get("question"),"thought",map("text",main.get("text"),"topic",main.get("topic"),"core_concepts",main.get("core_concepts")),"current_node_id",active,"candidates",shortlist,"history",history.stream().map(p->map("qa_id",p.get("id"),"primary_node_id",owner(g,p),"question",p.get("question"),"answer_excerpt",Objects.toString(p.get("answer"),"").substring(0,Math.min(1200,Objects.toString(p.get("answer"),"").length())))).toList());
      Map<String,Object> decision;try{decision=ai.call("/qa-ownership",request);check(decision!=null,"归属判断缺失");}catch(AiClient.AiFailure failed){save(g,q,main,active,"pending",failed.getMessage(),request);throw failed;}
      String kind=s(decision,"decision"),target=s(decision,"node_id"),reason=text(decision.get("reason"),"归属理由");check(List.of("accumulate","branch","uncertain").contains(kind),"归属类型无效");
      if(eq(kind,"uncertain")){save(g,q,main,active,"pending",reason,request);continue;}
      final String chosen=target;check(shortlist.stream().anyMatch(c->eq(c.get("node_id"),chosen))&&usable(g,target,sid),"归属不属于准入候选");
      if(eq(kind,"branch")){String relation=s(decision,"branch_relation");if(eq(relation,"sibling")){String reference=s(decision,"reference_node_id");check(usable(g,reference,sid)&&shortlist.stream().anyMatch(c->eq(c.get("node_id"),reference)),"并列参照节点无效");check(eq(nodeParent(g,reference),target),"并列分支必须挂靠参照节点的共同父节点");}else if(eq(relation,"child")){check(eq(decision.get("reference_node_id"),target),"深入分支必须以研究对象为父节点");}else if(relation!=null){check(eq(relation,"independent"),"分支关系无效");}String title=text(decision.get("title"),"研究问题"),goal=text(decision.get("research_goal"),"独立研究目标"),distinction=text(decision.get("distinction"),"分支区别");check(title.length()<=200&&goal.length()<=12000,"研究问题描述过长");var duplicate=g.all("nodes").stream().filter(n->usable(g,s(n,"id"),sid)&&eq(n.get("parent_id"),chosen)&&eq(n.get("title"),title)).findFirst().orElse(null);
        if(duplicate!=null)target=s(duplicate,"id");else{var n=core.newNode(g,map("parent_id",target,"title",title,"summary",goal,"reason",reason+"；独立研究目标："+distinction),"research_problem",List.of(main.get("id")));n.put("created_by_qa_id",qid);created.add(n);target=s(n,"id");}}
      save(g,q,main,target,"resolved",reason,request);for(var cluster:g.all("clusters"))if(eq(cluster.get("space_id"),sid)&&eq(cluster.get("basis"),"semantic")&&strings(cluster,"members").contains(s(main,"id"))&&cluster.get("node_id")==null)cluster.put("node_id",target);
    }return created;
  }
  String owner(Graph g,Map<String,Object> q){var r=g.rows.get("relations").get("qa_primary_"+s(q,"id"));return r==null?null:s(r,"target_id");}
  String nodeParent(Graph g,String id){return s(core.node(g,id),"parent_id");}
  List<String> ancestorIds(Graph g,String id){var result=new ArrayList<String>();var seen=new HashSet<String>();String parent=nodeParent(g,id);while(parent!=null&&seen.add(parent)){result.add(parent);parent=nodeParent(g,parent);}return result;}
  void save(Graph g,Map<String,Object> q,Map<String,Object> main,String target,String status,String reason,Object evidence){String qid=s(q,"id"),sid=s(q,"space_id");var old=g.rows.get("relations").get("qa_primary_"+qid);if(old!=null)core.audit(g,"qa_ownership_previous",new LinkedHashMap<>(old),sid);
    var removed=g.all("refs").stream().filter(r->eq(r.get("qa_id"),qid)&&eq(r.get("space_id"),sid)).map(r->s(r,"id")).toList();for(String id:removed)g.rows.get("refs").remove(id);
    core.ref(g,target,qid,s(main,"id"),"strong");var rel=map("id","qa_primary_"+qid,"type","qa_primary_node","space_id",sid,"qa_id",qid,"thought_id",main.get("id"),"source_id",g.get("conversations",s(q,"conversation_id")).get("anchor_id"),"target_id",target,"assignment_status",status,"reason",reason,"evidence",evidence,"created_at",now());g.put("relations",rel);core.audit(g,"assign_qa_primary_node",rel,sid);
  }
  void defer(Graph g,String sid,String qid,String reason){var q=g.get("qas",qid);var main=g.all("thoughts").stream().filter(t->eq(t.get("qa_id"),qid)&&eq(t.get("role"),"main")).findFirst().orElseThrow();save(g,q,main,current(g,g.get("conversations",s(q,"conversation_id")),q),"pending",reason,map("deferred",true));}
}
