-- New encodings are append-only versions, never replacements for birth evidence.
CREATE TABLE thought_coordinates(id text PRIMARY KEY,body jsonb NOT NULL CHECK(body->>'id'=id));
ALTER TABLE thought_coordinates ADD COLUMN thought_id text GENERATED ALWAYS AS(body->>'thought_id') STORED;
ALTER TABLE thought_coordinates ADD CONSTRAINT coordinate_thought_fk FOREIGN KEY(thought_id) REFERENCES thoughts(id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE thought_coordinates ADD COLUMN embedding vector;
CREATE INDEX coordinate_space_index ON thought_coordinates((body->>'space_id'),(body->>'method'));
CREATE TABLE thought_links(id text PRIMARY KEY,body jsonb NOT NULL CHECK(body->>'id'=id));
CREATE INDEX thought_links_space_index ON thought_links((body->>'space_id'));
CREATE OR REPLACE FUNCTION protect_semantic_encoding() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Semantic encoding history cannot be deleted'; END IF;
 IF OLD.body IS DISTINCT FROM NEW.body THEN RAISE EXCEPTION 'Semantic encoding versions are immutable'; END IF;
 IF OLD.embedding IS NOT NULL AND OLD.embedding IS DISTINCT FROM NEW.embedding THEN RAISE EXCEPTION 'Semantic encoding cannot be replaced'; END IF;
 IF NEW.embedding IS DISTINCT FROM (NEW.body->>'vector')::vector THEN RAISE EXCEPTION 'Semantic embedding must match encoding version'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER coordinate_version_immutable BEFORE UPDATE OR DELETE ON thought_coordinates FOR EACH ROW EXECUTE FUNCTION protect_semantic_encoding();
