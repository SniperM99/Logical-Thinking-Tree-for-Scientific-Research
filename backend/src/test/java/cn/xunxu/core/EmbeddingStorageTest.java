package cn.xunxu.core;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import java.util.List;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;
class EmbeddingStorageTest {
  @Test void unquantifiedAuxiliaryThoughtHasNullDatabaseVector(){var repo=new GraphRepository(mock(JdbcTemplate.class),new ObjectMapper(),mock(TransactionTemplate.class));assertNull(repo.embeddingValue(List.of()));assertNull(repo.embeddingValue(null));assertEquals("[1.0,0.0]",repo.embeddingValue(List.of(1.0,0.0)));}
}
