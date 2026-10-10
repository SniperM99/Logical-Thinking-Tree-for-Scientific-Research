package cn.xunxu.core;
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Map;
class AiClientTest {
 @Test void serviceValidationReasonIsShownAndSecretLikeDetailsAreHidden() throws Exception {
  var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
  server.createContext("/validation",exchange->{byte[] body="{\"detail\":\"回答与思想结果被截断\"}".getBytes(StandardCharsets.UTF_8);exchange.getResponseHeaders().set("Content-Type","application/json");exchange.sendResponseHeaders(502,body.length);exchange.getResponseBody().write(body);exchange.close();});
  server.createContext("/private",exchange->{byte[] body=("{\"detail\":\"sk-"+"fake-test-value\"}").getBytes(StandardCharsets.UTF_8);exchange.getResponseHeaders().set("Content-Type","application/json");exchange.sendResponseHeaders(502,body.length);exchange.getResponseBody().write(body);exchange.close();});server.start();
  try{var client=new AiClient("http://127.0.0.1:"+server.getAddress().getPort());assertEquals("回答与思想结果被截断",assertThrows(AiClient.AiFailure.class,()->client.call("/validation",Map.of())).getMessage());assertEquals("模型服务暂时未能返回有效结果",assertThrows(AiClient.AiFailure.class,()->client.call("/private",Map.of())).getMessage());}finally{server.stop(0);}
 }
}
