package cn.xunxu.core;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import java.util.*;
import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
@Component
public class AiClient {
  private final RestClient client;
  public AiClient(@Value("${xunxu.ai-url}")String url){var factory=new JdkClientHttpRequestFactory(HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).connectTimeout(Duration.ofSeconds(5)).build());factory.setReadTimeout(Duration.ofSeconds(65));this.client=RestClient.builder().requestFactory(factory).baseUrl(url).build();}
  @SuppressWarnings("unchecked")
  public Map<String,Object> call(String path,Map<String,Object> body){try{return client.post().uri(path).body(body).retrieve().body(Map.class);}catch(Exception e){throw new IllegalArgumentException("AI 引擎不可用或服务拒绝请求，请检查 Python 服务与模型配置；研究数据未提交。");}}
  @SuppressWarnings("unchecked")
  public Map<String,Object> health(){try{return client.get().uri("/health").retrieve().body(Map.class);}catch(Exception e){return Map.of("available",false,"error","Python AI 引擎未连接");}}
}
