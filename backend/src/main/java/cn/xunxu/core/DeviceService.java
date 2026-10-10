package cn.xunxu.core;
import cn.xunxu.core.GraphRepository.Graph;
import org.springframework.stereotype.Service;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.*;
import static cn.xunxu.core.GraphService.*;

@Service
public class DeviceService {
  final GraphRepository repo;final GraphService graph;
  public DeviceService(GraphRepository repo,GraphService graph){this.repo=repo;this.graph=graph;}
  Map<String,Object> auth(Graph g,Map<String,Object> data){var d=g.get("devices",s(data,"device_id"));String token=s(data,"device_token");check(token!=null&&java.security.MessageDigest.isEqual(digest(token).getBytes(),s(d,"token_hash").getBytes()),"设备认证失败");return d;}
  public Object register(Map<String,Object> data){return repo.write(g->{byte[] secret=new byte[32];new SecureRandom().nextBytes(secret);String token=HexFormat.of().formatHex(secret),deviceId=id("device");var d=map("id",deviceId,"name",text(data.get("name"),"设备名"),"workspace",text(data.get("workspace"),"执行工作区"),"token_hash",digest(token),"created_at",now(),"last_seen",now());g.put("devices",d);graph.audit(g,"register_device",deviceId,null);return map("device_id",deviceId,"device_token",token);});}
  public Object heartbeat(Map<String,Object> data){return repo.write(g->{var d=auth(g,data);d.put("last_seen",now());return map("ok",true,"device_id",d.get("id"));});}
  public Object devices(){return repo.read(g->g.all("devices").stream().map(d->{var sanitized=new LinkedHashMap<>(d);sanitized.remove("token_hash");return sanitized;}).toList());}
  public Object dispatch(String rid,Map<String,Object> data){return repo.write(g->{var run=g.get("runs",rid);graph.open(g,s(run,"node_id"));var d=g.get("devices",s(data,"device_id"));check(eq(run.get("status"),"pending"),"仅待执行 Run 可派发；重试创建新 Run");Object raw=data.get("argv");check(raw instanceof List<?> list&&!list.isEmpty()&&list.size()<=100&&list.stream().allMatch(x->x instanceof String t&&!t.isEmpty()&&t.length()<10000),"命令必须为参数数组，不使用 shell");String cwd=Objects.toString(data.getOrDefault("cwd","."));check(!cwd.startsWith("/")&&!Arrays.asList(cwd.replace('\\','/').split("/")).contains(".."),"执行目录必须为设备工作区内相对路径");long timeout=data.containsKey("timeout_seconds")?number(data,"timeout_seconds"):3600;check(timeout>=1&&timeout<=86400,"超时必须为 1～86400 秒");var job=map("id",id("job"),"run_id",rid,"device_id",d.get("id"),"argv",raw,"cwd",cwd,"timeout_seconds",timeout,"status","queued","created_at",now(),"space_id",run.get("space_id"));g.put("jobs",job);run.put("status","dispatched");run.put("device",d.get("name"));run.put("execution_mode","device_agent");graph.touch(g.get("nodes",s(run,"node_id")));graph.audit(g,"dispatch_run",map("run_id",rid,"job_id",job.get("id"),"device_id",d.get("id")),s(run,"space_id"));return job;});}
  public Object claim(Map<String,Object> data){return repo.write(g->{var d=auth(g,data);d.put("last_seen",now());var queued=g.all("jobs").stream().filter(j->eq(j.get("device_id"),d.get("id"))&&eq(j.get("status"),"queued")).findFirst();if(queued.isEmpty())return map("job",null);var job=queued.get();job.put("status","accepted");job.put("claimed_at",now());job.put("lease_expires_at",Instant.now().plusSeconds(120).toString());return map("job",job);});}
  public Object report(String rid,Map<String,Object> data){return repo.write(g->{var device=auth(g,data);var job=g.get("jobs",s(data,"job_id"));check(eq(job.get("run_id"),rid)&&eq(job.get("device_id"),device.get("id")),"设备任务归属错误");check(!eq(job.get("status"),"queued"),"任务尚未领取");var event=graph.runEvent(g,rid,data);job.put("status",g.get("runs",rid).get("status"));job.put("updated_at",now());device.put("last_seen",now());return event;});}
}
