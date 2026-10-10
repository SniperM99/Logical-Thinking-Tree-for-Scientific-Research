-- Research Graph Core domain collections. JSONB keeps versioned evidence snapshots,
-- generated columns enforce graph identity and relational integrity in PostgreSQL.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE graph_revision (id integer PRIMARY KEY CHECK(id=1), revision bigint NOT NULL);
INSERT INTO graph_revision VALUES (1,0);
CREATE TABLE spaces (id text PRIMARY KEY, body jsonb NOT NULL CHECK(body->>'id'=id));
CREATE TABLE nodes (id text PRIMARY KEY, body jsonb NOT NULL CHECK(body->>'id'=id));
CREATE TABLE relations (id text PRIMARY KEY, body jsonb NOT NULL CHECK(body->>'id'=id));
CREATE TABLE conversations (id text PRIMARY KEY, body jsonb NOT NULL CHECK(body->>'id'=id));
CREATE TABLE qas (id text PRIMARY KEY, body jsonb NOT NULL CHECK(body->>'id'=id));
CREATE TABLE thoughts (id text PRIMARY KEY, body jsonb NOT NULL CHECK(body->>'id'=id));
CREATE TABLE clusters (id text PRIMARY KEY, body jsonb NOT NULL CHECK(body->>'id'=id));
CREATE TABLE refs (id text PRIMARY KEY, body jsonb NOT NULL CHECK(body->>'id'=id));
CREATE TABLE runs (id text PRIMARY KEY, body jsonb NOT NULL CHECK(body->>'id'=id));
CREATE TABLE events (id text PRIMARY KEY, body jsonb NOT NULL CHECK(body->>'id'=id));
CREATE TABLE resources (id text PRIMARY KEY, body jsonb NOT NULL CHECK(body->>'id'=id));
CREATE TABLE proposals (id text PRIMARY KEY, body jsonb NOT NULL CHECK(body->>'id'=id));
CREATE TABLE audit (id text PRIMARY KEY, body jsonb NOT NULL CHECK(body->>'id'=id));
CREATE TABLE transplants (id text PRIMARY KEY, body jsonb NOT NULL CHECK(body->>'id'=id));
CREATE TABLE summaries (id text PRIMARY KEY, body jsonb NOT NULL CHECK(body->>'id'=id));
CREATE TABLE devices (id text PRIMARY KEY, body jsonb NOT NULL CHECK(body->>'id'=id));
CREATE TABLE jobs (id text PRIMARY KEY, body jsonb NOT NULL CHECK(body->>'id'=id));

ALTER TABLE spaces ADD COLUMN root_id text GENERATED ALWAYS AS (body->>'root_id') STORED;
ALTER TABLE nodes ADD COLUMN space_id text GENERATED ALWAYS AS (body->>'space_id') STORED;
ALTER TABLE nodes ADD COLUMN parent_id text GENERATED ALWAYS AS (body->>'parent_id') STORED;
ALTER TABLE nodes ADD CONSTRAINT node_space_fk FOREIGN KEY(space_id) REFERENCES spaces(id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE nodes ADD CONSTRAINT node_parent_fk FOREIGN KEY(parent_id) REFERENCES nodes(id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE spaces ADD CONSTRAINT space_root_fk FOREIGN KEY(root_id) REFERENCES nodes(id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE conversations ADD COLUMN anchor_id text GENERATED ALWAYS AS (body->>'anchor_id') STORED;
ALTER TABLE conversations ADD CONSTRAINT conversation_anchor_fk FOREIGN KEY(anchor_id) REFERENCES nodes(id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE qas ADD COLUMN conversation_id text GENERATED ALWAYS AS (body->>'conversation_id') STORED;
ALTER TABLE qas ADD CONSTRAINT qa_conversation_fk FOREIGN KEY(conversation_id) REFERENCES conversations(id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE thoughts ADD COLUMN qa_id text GENERATED ALWAYS AS (body->>'qa_id') STORED;
ALTER TABLE thoughts ADD COLUMN original_embedding vector;
ALTER TABLE thoughts ADD COLUMN working_embedding vector;
ALTER TABLE thoughts ADD CONSTRAINT thought_qa_fk FOREIGN KEY(qa_id) REFERENCES qas(id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE refs ADD COLUMN node_id text GENERATED ALWAYS AS (body->>'node_id') STORED;
ALTER TABLE refs ADD COLUMN thought_id text GENERATED ALWAYS AS (body->>'thought_id') STORED;
ALTER TABLE refs ADD CONSTRAINT ref_node_fk FOREIGN KEY(node_id) REFERENCES nodes(id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE refs ADD CONSTRAINT ref_thought_fk FOREIGN KEY(thought_id) REFERENCES thoughts(id) DEFERRABLE INITIALLY DEFERRED;
CREATE UNIQUE INDEX ref_unique ON refs(node_id,thought_id);
ALTER TABLE runs ADD COLUMN node_id text GENERATED ALWAYS AS (body->>'node_id') STORED;
ALTER TABLE runs ADD CONSTRAINT run_node_fk FOREIGN KEY(node_id) REFERENCES nodes(id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE events ADD COLUMN run_id text GENERATED ALWAYS AS (body->>'run_id') STORED;
ALTER TABLE events ADD COLUMN event_id text GENERATED ALWAYS AS (body->>'event_id') STORED;
ALTER TABLE events ADD CONSTRAINT event_run_fk FOREIGN KEY(run_id) REFERENCES runs(id) DEFERRABLE INITIALLY DEFERRED;
CREATE UNIQUE INDEX event_unique ON events(run_id,event_id);
CREATE INDEX node_space_index ON nodes(space_id);
CREATE INDEX node_parent_index ON nodes(parent_id);
CREATE INDEX qa_conversation_index ON qas(conversation_id);
CREATE INDEX relation_type_index ON relations((body->>'type'));
CREATE INDEX cluster_space_index ON clusters((body->>'space_id'));
CREATE UNIQUE INDEX qa_request_unique ON qas(conversation_id,(body->>'request_id')) WHERE body->>'request_id' IS NOT NULL;
CREATE TABLE outbox (id text PRIMARY KEY, aggregate_id text, event_type text NOT NULL, payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), published_at timestamptz);
CREATE OR REPLACE FUNCTION preserve_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_TABLE_NAME='qas' AND OLD.body IS DISTINCT FROM NEW.body THEN
  RAISE EXCEPTION 'Original QA evidence is immutable';
 END IF;
 IF TG_TABLE_NAME='conversations' AND (OLD.body->'anchor_id' IS DISTINCT FROM NEW.body->'anchor_id' OR OLD.body->'context_snapshot' IS DISTINCT FROM NEW.body->'context_snapshot') THEN
  RAISE EXCEPTION 'Conversation origin and context snapshot are immutable';
 END IF;
 IF TG_TABLE_NAME='thoughts' AND OLD.body->'original_vector' IS DISTINCT FROM NEW.body->'original_vector' THEN
  RAISE EXCEPTION 'Thought birth coordinate is immutable';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER qa_immutable BEFORE UPDATE ON qas FOR EACH ROW EXECUTE FUNCTION preserve_evidence();
CREATE TRIGGER conversation_origin_immutable BEFORE UPDATE ON conversations FOR EACH ROW EXECUTE FUNCTION preserve_evidence();
CREATE TRIGGER thought_origin_immutable BEFORE UPDATE ON thoughts FOR EACH ROW EXECUTE FUNCTION preserve_evidence();
