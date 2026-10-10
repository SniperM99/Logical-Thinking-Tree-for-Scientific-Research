package cn.xunxu.core;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.stereotype.Component;
import org.springframework.beans.factory.annotation.Value;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.net.URI;
import java.security.MessageDigest;
import java.nio.charset.StandardCharsets;
@Component
public class LocalAccessFilter extends OncePerRequestFilter {
  final String token;
  public LocalAccessFilter(@Value("${xunxu.server-token}")String token){this.token=token;}
  @Override protected void doFilterInternal(HttpServletRequest req,HttpServletResponse res,FilterChain chain)throws ServletException,IOException{
    String origin=req.getHeader("Origin");
    if(origin!=null){try{URI u=URI.create(origin);String authority=req.getHeader("Host");boolean localDev=("127.0.0.1".equals(u.getHost())||"localhost".equals(u.getHost()))&&(u.getPort()==5173||u.getPort()==8080);if(!u.getAuthority().equals(authority)&&!localDev){res.sendError(403,"Cross-origin mutation rejected");return;}}catch(Exception e){res.sendError(403);return;}}
    String address=req.getRemoteAddr();boolean loopback=address.equals("127.0.0.1")||address.equals("0:0:0:0:0:0:0:1")||address.equals("::1");
    if(!loopback&&req.getRequestURI().startsWith("/api")){String auth=req.getHeader("Authorization");if(token.isBlank()||auth==null||!MessageDigest.isEqual(auth.getBytes(StandardCharsets.UTF_8),("Bearer "+token).getBytes(StandardCharsets.UTF_8))){res.sendError(401,"Server token required");return;}}
    chain.doFilter(req,res);
  }
}
