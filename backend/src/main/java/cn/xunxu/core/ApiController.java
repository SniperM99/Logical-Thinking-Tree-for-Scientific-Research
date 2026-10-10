package cn.xunxu.core;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import java.util.*;

@RestController
@RequestMapping("/api")
public class ApiController {
  final GraphService core;final DeviceService devices;final AiClient ai;
  public ApiController(GraphService core,DeviceService devices,AiClient ai){this.core=core;this.devices=devices;this.ai=ai;}
  @Bean ApplicationRunner seed(@Value("${xunxu.seed}")boolean enabled){return args->{if(enabled)core.seed();};}
  @GetMapping("/health") Object health(){return Map.of("ok",true,"framework","1.1","version","0.1.0","final_write_authority","Java Research Graph Core");}
  @GetMapping("/state") Object state(@RequestParam(name="space_id",required=false)String sid){return core.state(sid);}
  @GetMapping("/context") Object context(@RequestParam(name="node_id")String nid){return core.context(nid);}
  @GetMapping("/conversations/{id}") Object conversation(@PathVariable String id){return core.conversation(id);}
  @PostMapping("/spaces") Object space(@RequestBody Map<String,Object>d){return core.createSpace(d);}
  @PostMapping("/nodes") Object node(@RequestBody Map<String,Object>d){return core.createNode(d);}
  @PostMapping("/conversations") Object conv(@RequestBody Map<String,Object>d){return core.conversation(d);}
  @PostMapping("/qa") Object qa(@RequestBody Map<String,Object>d){return core.qa(d);}
  @PostMapping("/qa/{id}/growth/retry") Object retryGrowth(@PathVariable String id){return core.retryGrowth(id);}
  @PostMapping("/proposals") Object propose(@RequestBody Map<String,Object>d){return core.propose(d);}
  @PostMapping("/proposals/{id}/approve") Object approve(@PathVariable String id){return core.approve(id);}
  @PostMapping("/proposals/{id}/reject") Object reject(@PathVariable String id){return core.reject(id);}
  @PostMapping("/audit/{id}/undo") Object undo(@PathVariable String id){return core.undo(id);}
  @PostMapping("/resources") Object resource(@RequestBody Map<String,Object>d){return core.resource(d);}
  @PostMapping("/runs") Object run(@RequestBody Map<String,Object>d){return core.createRun(d);}
  @PostMapping("/runs/{id}/events") Object event(@PathVariable String id,@RequestBody Map<String,Object>d){return core.report(id,d);}
  @GetMapping("/transplants/{id}/context") ResponseEntity<String> nutrient(@PathVariable String id){return ResponseEntity.ok().contentType(MediaType.parseMediaType("text/markdown;charset=UTF-8")).header("Content-Disposition","attachment; filename=research-context.md").body(core.transplantContext(id));}
  @GetMapping("/devices") Object deviceList(){return devices.devices();}
  @PostMapping("/devices/register") Object register(@RequestBody Map<String,Object>d){return devices.register(d);}
  @PostMapping("/devices/heartbeat") Object heartbeat(@RequestBody Map<String,Object>d){return devices.heartbeat(d);}
  @PostMapping("/jobs/claim") Object claim(@RequestBody Map<String,Object>d){return devices.claim(d);}
  @PostMapping("/runs/{id}/dispatch") Object dispatch(@PathVariable String id,@RequestBody Map<String,Object>d){return devices.dispatch(id,d);}
  @PostMapping("/runs/{id}/report") Object report(@PathVariable String id,@RequestBody Map<String,Object>d){return devices.report(id,d);}
  @GetMapping("/ai/health") Object aiHealth(){return ai.health();}
  @PostMapping("/candidates") Object candidates(@RequestBody Map<String,Object>d){return core.repo.read(g->ai.call("/candidates",GraphService.map("context",core.scoped(g,GraphService.s(d,"node_id")),"count",d.getOrDefault("count",3),"retained_titles",d.getOrDefault("retained_titles",List.of()))));}
  @GetMapping("/thought-space") Object thoughtSpace(@RequestParam(name="space_id")String sid){return core.thoughtSpace.view(sid);}
  @PostMapping("/thought-space/reindex") Object reindex(@RequestBody Map<String,Object>d){return core.thoughtSpace.reindex(GraphService.s(d,"space_id"));}
  @GetMapping("/export") ResponseEntity<Object> export(){return ResponseEntity.ok().header("Content-Disposition","attachment; filename=xunxu-backup.json").body(core.repo.read(g->g.rows));}
}
