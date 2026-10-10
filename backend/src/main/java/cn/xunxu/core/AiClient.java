package cn.xunxu.core;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
@Component
public class AiClient {
  private final RestClient client;
  public AiClient(@Value("${xunxu.ai-url}")String url){var factory=new JdkClientHttpRequestFactory(HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).connectTimeout(Duration.ofSeconds(5)).build());factory.setReadTimeout(Duration.ofSeconds(65));this.client=RestClient.builder().requestFactory(factory).baseUrl(url).build();}
  static class AiFailure extends IllegalArgumentException {AiFailure(String message){super(message);}}
  @SuppressWarnings("unchecked")
  public Map<String,Object> call(String path,Map<String,Object> body){try{return client.post().uri(path).body(body).retrieve().body(Map.class);}catch(RestClientResponseException e){String detail="模型服务暂时未能返回有效结果";try{String value=new ObjectMapper().readTree(e.getResponseBodyAsString()).path("detail").asText();if(!value.isBlank()&&value.length()<=400&&!value.matches("(?is).*(sk-|bearer|api_key).*"))detail=value;}catch(Exception ignored){}throw new AiFailure(detail);}catch(Exception e){throw new AiFailure("无法连接 AI 引擎或模型请求超时，请稍后重试。");}}
  @SuppressWarnings("unchecked")
  public Map<String,Object> health(){try{return client.get().uri("/health").retrieve().body(Map.class);}catch(Exception e){return Map.of("available",false,"error","Python AI 引擎未连接");}}
}
