-- Origin coordinates and permanent evidence cannot be bypassed by direct SQL.
CREATE OR REPLACE FUNCTION protect_evidence_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION 'Permanent research evidence cannot be deleted';
END $$;
CREATE TRIGGER qa_no_delete BEFORE DELETE ON qas FOR EACH ROW EXECUTE FUNCTION protect_evidence_delete();
CREATE TRIGGER conversation_no_delete BEFORE DELETE ON conversations FOR EACH ROW EXECUTE FUNCTION protect_evidence_delete();
CREATE TRIGGER thought_no_delete BEFORE DELETE ON thoughts FOR EACH ROW EXECUTE FUNCTION protect_evidence_delete();
CREATE OR REPLACE FUNCTION protect_birth_embedding() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.original_embedding IS NOT NULL AND OLD.original_embedding IS DISTINCT FROM NEW.original_embedding THEN
  RAISE EXCEPTION 'Thought birth embedding cannot be replaced';
 END IF;
 IF NEW.original_embedding IS NOT NULL AND NEW.original_embedding IS DISTINCT FROM (NEW.body->>'original_vector')::vector THEN
  RAISE EXCEPTION 'Thought birth embedding must match immutable evidence';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER thought_birth_embedding BEFORE UPDATE ON thoughts FOR EACH ROW EXECUTE FUNCTION protect_birth_embedding();
