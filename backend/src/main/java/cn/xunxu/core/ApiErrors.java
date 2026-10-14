package cn.xunxu.core;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.*;
import org.springframework.dao.DataAccessException;
import java.util.Map;
@RestControllerAdvice
public class ApiErrors {
  @ExceptionHandler(IllegalArgumentException.class)
  ResponseEntity<?> invalid(IllegalArgumentException e){return ResponseEntity.badRequest().body(Map.of("error",e.getMessage()));}
  @ExceptionHandler(DataAccessException.class)
  ResponseEntity<?> database(DataAccessException e){return ResponseEntity.status(409).body(Map.of("error","数据库完整性或并发校验失败，研究数据未提交。"));}
  @ExceptionHandler(org.springframework.web.servlet.resource.NoResourceFoundException.class)
  ResponseEntity<?> missing(Exception e){return ResponseEntity.status(404).body(Map.of("error","接口不存在或已移除。"));}
  @ExceptionHandler(Exception.class)
  ResponseEntity<?> failure(Exception e){System.err.println(e);return ResponseEntity.status(500).body(Map.of("error","服务处理失败，请查看本地服务日志。"));}
}
