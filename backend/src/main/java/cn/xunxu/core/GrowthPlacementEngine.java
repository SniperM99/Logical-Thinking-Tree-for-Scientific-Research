package cn.xunxu.core;

import cn.xunxu.core.GraphRepository.Graph;
import static cn.xunxu.core.GraphService.*;
import java.util.*;

/** Conversation chronology proposes logical parents; immutable anchors and coordinates stay intact. */
final class GrowthPlacementEngine {
  final GraphService core;
  final AiClient ai;
  GrowthPlacementEngine(GraphService core,AiClient ai){this.core=core;this.ai=ai;}

  List<Map<String,Object>> evidence(Graph g,Map<String,Object> node,String conversation){
    var ids=new LinkedHashSet<String>();
    for(String tid:strings(node,"evidence"))if(g.rows.get("thoughts").containsKey(tid))ids.add(s(g.get("thoughts",tid),"qa_id"));
    for(var ref:g.all("refs"))if(eq(ref.get("node_id"),node.get("id"))&&eq(ref.get("strength"),"strong"))ids.add(s(ref,"qa_id"));
    return g.all("qas").stream().filter(q->ids.contains(s(q,"id"))&&(conversation==null||eq(q.get("conversation_id"),conversation)))
      .sorted(Comparator.comparingLong(q->number(q,"turn_index"))).toList();
  }
  Map<String,Object> turn(Map<String,Object> q){
    return map("qa_id",q.get("id"),"turn_index",q.get("turn_index"),"question",q.get("question"),"answer_excerpt",Objects.toString(q.get("answer"),"").substring(0,Math.min(1600,Objects.toString(q.get("answer"),"").length())));
  }
  double similarity(Graph g,List<Map<String,Object>> coordinates,Map<String,Object> child,Map<String,Object> parent,List<Map<String,Object>> childQas,List<Map<String,Object>> parentQas){
    var childIds=childQas.stream().map(q->s(q,"id")).toList();var parentIds=parentQas.stream().map(q->s(q,"id")).toList();
    var childThoughts=new HashSet<>(strings(child,"evidence"));var parentThoughts=new HashSet<>(strings(parent,"evidence"));
    for(var r:g.all("refs"))if(eq(r.get("strength"),"strong")){if(eq(r.get("node_id"),child.get("id")))childThoughts.add(s(r,"thought_id"));if(eq(r.get("node_id"),parent.get("id")))parentThoughts.add(s(r,"thought_id"));}
    double max=-1;
    for(var a:coordinates)if(childThoughts.contains(s(a,"thought_id"))&&childIds.contains(s(a,"qa_id")))
      for(var b:coordinates)if(parentThoughts.contains(s(b,"thought_id"))&&parentIds.contains(s(b,"qa_id"))&&ThoughtSpaceEngine.compatible(a,b))
        max=Math.max(max,ThoughtSpaceEngine.cosine(ThoughtSpaceEngine.vector(a),ThoughtSpaceEngine.vector(b)));
    return max;
  }
  long branchFloor(Graph g,Map<String,Object> node,String cid,long fallback){
    var tids=new LinkedHashSet<>(strings(node,"evidence"));for(var r:g.all("refs"))if(eq(r.get("node_id"),node.get("id"))&&eq(r.get("strength"),"strong"))tids.add(s(r,"thought_id"));
    return tids.stream().filter(tid->g.rows.get("thoughts").containsKey(tid)).map(tid->g.get("thoughts",tid)).filter(t->eq(t.get("role"),"main")).map(t->g.get("qas",s(t,"qa_id"))).filter(q->eq(q.get("conversation_id"),cid)).mapToLong(q->number(q,"turn_index")).min().orElse(fallback);
  }
  long ownConversationCount(Graph g,Map<String,Object> node){return evidence(g,node,null).stream().map(q->s(q,"conversation_id")).filter(Objects::nonNull).distinct().count();}
  void place(Graph g,String sid,List<Map<String,Object>> created){
    var coordinates=core.thoughtSpace.latest(g,sid);var createdIds=created.stream().map(n->s(n,"id")).toList();
    var pending=new ArrayList<Map<String,Object>>();var metadata=new LinkedHashMap<String,Map<String,Object>>();
    for(var child:g.all("nodes")){
      if(!eq(child.get("space_id"),sid)||child.get("parent_id")==null||flag(child,"archived")||flag(child,"frozen")||flag(child,"hidden")||!strings(child,"sources").isEmpty())continue;
      try{core.open(g,s(child,"id"));}catch(IllegalArgumentException frozen){continue;}
      var own=evidence(g,child,null);if(own.isEmpty())continue;
      for(String cid:own.stream().map(q->s(q,"conversation_id")).filter(Objects::nonNull).distinct().toList()){
        if(!g.rows.get("conversations").containsKey(cid))continue;
        var conversation=g.get("conversations",cid);String anchor=s(conversation,"anchor_id");
        if(!g.rows.get("nodes").containsKey(anchor)||!eq(core.node(g,anchor).get("space_id"),sid))continue;
        var childQas=evidence(g,child,cid);long first=number(childQas.get(0),"turn_index"),last=number(childQas.get(childQas.size()-1),"turn_index");long floor=branchFloor(g,child,cid,last);if(floor<=1)continue;
        var candidates=new ArrayList<Map<String,Object>>();var allowed=core.descendants(g,anchor);var forbidden=core.descendants(g,s(child,"id"));
        for(var parent:g.all("nodes")){
          String pid=s(parent,"id");if(eq(pid,anchor)||!allowed.contains(pid)||forbidden.contains(pid)||flag(parent,"archived")||flag(parent,"hidden")||flag(parent,"frozen"))continue;
          try{core.open(g,pid);}catch(IllegalArgumentException frozen){continue;}
          var parentQas=evidence(g,parent,cid).stream().filter(q->number(q,"turn_index")<floor).toList();if(parentQas.isEmpty())continue;
          double sim=similarity(g,coordinates,child,parent,childQas,parentQas);if(sim<0)continue;
          long prior=number(parentQas.get(parentQas.size()-1),"turn_index");
          candidates.add(map("node_id",pid,"title",parent.get("title"),"level",parent.getOrDefault("research_level","question"),"similarity",sim,"prior_turn",prior,"evidence",parentQas.stream().map(this::turn).toList(),"rank",0.7*sim+0.3*(double)prior/floor));
        }
        candidates.sort(Comparator.comparingDouble((Map<String,Object> c)->((Number)c.get("rank")).doubleValue()).reversed());
        if(candidates.size()>5)candidates=new ArrayList<>(candidates.subList(0,5));if(candidates.isEmpty())continue;
        var sequence=g.all("qas").stream().filter(q->eq(q.get("conversation_id"),cid)&&number(q,"turn_index")<=last).sorted(Comparator.comparingLong(q->number(q,"turn_index"))).map(this::turn).toList();
        var request=map("child",map("node_id",child.get("id"),"title",child.get("title"),"level",child.getOrDefault("research_level","question"),"evidence",childQas.stream().map(this::turn).toList()),"candidates",candidates,"sequence",sequence,"anchor_id",anchor,"conversation_id",cid);
        String key="placement_"+digest(core.repo.encode(request)).substring(0,24);
        if(g.rows.get("relations").containsKey(key)){var previous=g.get("relations",key);var pid=s(previous,"proposal_id");if(pid==null||!g.rows.get("proposals").containsKey(pid))continue;var old=g.get("proposals",pid);if(!eq(old.get("status"),"pending")||eq(old.get("fingerprint"),core.fingerprint(g,sid)))continue;}
        request.put("id",key);pending.add(request);metadata.put(key,map("child_id",child.get("id"),"candidate_ids",candidates.stream().map(c->c.get("node_id")).toList(),"anchor_id",anchor,"conversation_id",cid,"evidence",request));
      }
    }
    for(int start=0;start<pending.size();start+=10){
      var batch=pending.subList(start,Math.min(start+10,pending.size()));var response=ai.call("/growth-placements",map("requests",batch));check(response!=null,"缺少研究生长归属判断");var decisions=objects(response.get("decisions"));check(decisions.size()==batch.size(),"生长归属判断数量不一致");var seen=new HashSet<String>();
      for(var decision:decisions){String key=s(decision,"id"),kind=s(decision,"decision"),target=s(decision,"parent_id");check(metadata.containsKey(key)&&batch.stream().anyMatch(r->eq(r.get("id"),key))&&seen.add(key)&&List.of("deepen","continue","switch","uncertain").contains(kind),"生长归属判断无效");var meta=metadata.get(key);check(!eq(kind,"deepen")||strings(meta,"candidate_ids").contains(target),"生长父节点不是准入候选");String reason=text(decision.get("reason"),"归属理由");if(eq(kind,"deepen")){long focus=number(decision,"branch_start_turn");var requestEvidence=obj(meta.get("evidence"));check(objects(requestEvidence.get("sequence")).stream().anyMatch(q->number(q,"turn_index")==focus),"分支起点不是原会话轮次");var candidate=objects(requestEvidence.get("candidates")).stream().filter(c->eq(c.get("node_id"),target)).findFirst().orElseThrow();var basis=(List<?>)decision.get("parent_evidence_turns");check(basis!=null&&!basis.isEmpty()&&basis.stream().allMatch(t->t instanceof Number n&&n.longValue()<focus&&objects(candidate.get("evidence")).stream().anyMatch(q->number(q,"turn_index")==n.longValue())),"祖先依据必须早于正式深入讨论，不能使用未来证据");}var child=core.node(g,s(meta,"child_id"));
        var record=map("id",key,"space_id",sid,"type","growth_placement_decision","source_id",child.get("id"),"target_id",target,"decision",kind,"reason",reason,"branch_start_turn",decision.get("branch_start_turn"),"parent_evidence_turns",decision.get("parent_evidence_turns"),"conversation_id",meta.get("conversation_id"),"anchor_id",meta.get("anchor_id"),"evidence",meta.get("evidence"),"created_at",now());
        if(eq(kind,"deepen")&&!eq(child.get("parent_id"),target)){
          try{core.validate(g,map("operation","move","node_id",child.get("id"),"target_id",target));}catch(IllegalArgumentException blocked){record.put("blocked_reason",blocked.getMessage());g.put("relations",record);continue;}
          String explanation="会话顺序与语义空间判断："+child.get("title")+" 是 "+core.node(g,target).get("title")+" 的深入分支。"+reason;
          if(createdIds.contains(s(child,"id"))&&ownConversationCount(g,child)==1){child.put("parent_id",target);child.put("growth_placement",key);core.touch(core.node(g,target));child.put("reason",child.get("reason")+"；"+explanation);record.put("applied_at_creation",true);core.audit(g,"place_new_growth_node",map("node_id",child.get("id"),"parent_id",target,"decision_id",key),sid);}
          else {
            for(var p:g.all("proposals"))if(eq(p.get("origin"),"conversation_growth")&&eq(p.get("node_id"),child.get("id"))&&eq(p.get("status"),"pending")&&!eq(p.get("fingerprint"),core.fingerprint(g,sid))){p.put("status","superseded");p.put("decided_at",now());}
            if(g.all("proposals").stream().noneMatch(p->eq(p.get("operation"),"move")&&eq(p.get("node_id"),child.get("id"))&&eq(p.get("target_id"),target)&&List.of("pending","rejected","approved").contains(s(p,"status")))){
            var proposal=core.propose(g,map("operation","move","node_id",child.get("id"),"target_id",target,"reason",explanation,"origin","conversation_growth","placement_decision_id",key));record.put("proposal_id",proposal.get("id"));
            }
          }
        }
        g.put("relations",record);
      }
    }
    // Fingerprints are taken after all creation-time placements in this transaction.
    for(var p:g.all("proposals"))if(eq(p.get("origin"),"conversation_growth")&&eq(p.get("status"),"pending")&&metadata.containsKey(s(p,"placement_decision_id")))p.put("fingerprint",core.fingerprint(g,sid));
  }
}
