package cn.xunxu.core;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.support.TransactionTemplate;
import java.util.*;
import java.util.function.Function;

@Repository
public class GraphRepository {
  public static final List<String> TABLES=List.of("spaces","nodes","relations","conversations","qas","thoughts","clusters","refs","runs","events","resources","proposals","audit","transplants","summaries","devices","jobs","thought_coordinates","thought_links");
  final JdbcTemplate jdbc;
  final ObjectMapper json;
  final TransactionTemplate tx;
  public GraphRepository(JdbcTemplate jdbc,ObjectMapper json,TransactionTemplate tx){this.jdbc=jdbc;this.json=json;this.tx=tx;}
  public static class Graph {
    final Map<String,LinkedHashMap<String,Map<String,Object>>> rows=new LinkedHashMap<>();
    long revision;
    Graph(){for(String table:TABLES)rows.put(table,new LinkedHashMap<>());}
    Collection<Map<String,Object>> all(String table){return rows.get(table).values();}
    Map<String,Object> get(String table,String id){var v=rows.get(table).get(id);if(v==null)throw new IllegalArgumentException("对象不存在："+table);return v;}
    void put(String table,Map<String,Object> obj){rows.get(table).put(obj.get("id").toString(),obj);}
  }
  String encode(Object obj){try{return json.writeValueAsString(obj);}catch(Exception e){throw new IllegalStateException(e);}}
  Map<String,Object> decode(String str){try{return json.readValue(str,new TypeReference<LinkedHashMap<String,Object>>(){});}catch(Exception e){throw new IllegalStateException(e);}}
  Graph load(){Graph g=new Graph();g.revision=jdbc.queryForObject("SELECT revision FROM graph_revision WHERE id=1",Long.class);for(String table:TABLES)jdbc.query("SELECT id,body::text FROM "+table,rs->{g.rows.get(table).put(rs.getString(1),decode(rs.getString(2)));});return g;}
  public <T>T read(Function<Graph,T> fn){return tx.execute(status->{jdbc.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ");return fn.apply(load());});}
  public <T>T write(Function<Graph,T> fn){return tx.execute(status->{jdbc.queryForObject("SELECT revision FROM graph_revision WHERE id=1 FOR UPDATE",Long.class);Graph g=load();var before=new HashMap<String,Map<String,String>>();for(String table:TABLES){var copy=new HashMap<String,String>();g.rows.get(table).forEach((id,body)->copy.put(id,encode(body)));before.put(table,copy);}T result=fn.apply(g);for(String table:TABLES){for(var old:before.get(table).keySet())if(!g.rows.get(table).containsKey(old))jdbc.update("DELETE FROM "+table+" WHERE id=?",old);for(var row:g.all(table)){String id=row.get("id").toString(),body=encode(row);if(body.equals(before.get(table).get(id)))continue;jdbc.update("INSERT INTO "+table+" (id,body) VALUES (?,?::jsonb) ON CONFLICT(id) DO UPDATE SET body=EXCLUDED.body",id,body);if(table.equals("thought_coordinates")){jdbc.update("UPDATE thought_coordinates SET embedding=?::vector WHERE id=?",encode(row.get("vector")),id);}if(table.equals("thoughts")){jdbc.update("UPDATE thoughts SET original_embedding=?::vector,working_embedding=?::vector WHERE id=?",encode(row.get("original_vector")),encode(row.get("working_vector")),id);}}}jdbc.update("UPDATE graph_revision SET revision=revision+1 WHERE id=1");return result;});}
  public void event(String type,String aggregate,Object payload){jdbc.update("INSERT INTO outbox(id,aggregate_id,event_type,payload) VALUES (?,?,?,?::jsonb)",UUID.randomUUID().toString(),aggregate,type,encode(payload));}
}
