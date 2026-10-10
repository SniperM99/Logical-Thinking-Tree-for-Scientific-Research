-- Use only an acceptance database populated by verify-integration.py.
BEGIN;
DO $$
DECLARE qa text; thought text; conv text; blocked boolean;
BEGIN
 SELECT id INTO STRICT qa FROM qas LIMIT 1;
 SELECT id INTO STRICT thought FROM thoughts LIMIT 1;
 SELECT id INTO STRICT conv FROM conversations LIMIT 1;
 blocked:=false;
 BEGIN UPDATE qas SET body=jsonb_set(body,'{answer}','"overwritten"'::jsonb) WHERE id=qa;
 EXCEPTION WHEN OTHERS THEN blocked:=true; END;
 IF NOT blocked THEN RAISE EXCEPTION 'QA overwrite was accepted'; END IF;
 blocked:=false;
 BEGIN DELETE FROM qas WHERE id=qa;
 EXCEPTION WHEN OTHERS THEN blocked:=true; END;
 IF NOT blocked THEN RAISE EXCEPTION 'Permanent evidence deletion was accepted'; END IF;
 blocked:=false;
 BEGIN UPDATE conversations SET body=jsonb_set(body,'{context_snapshot}','{}'::jsonb) WHERE id=conv;
 EXCEPTION WHEN OTHERS THEN blocked:=true; END;
 IF NOT blocked THEN RAISE EXCEPTION 'Conversation origin snapshot overwrite accepted'; END IF;
 blocked:=false;
 BEGIN UPDATE thoughts SET original_embedding='[1,0]'::vector WHERE id=thought;
 EXCEPTION WHEN OTHERS THEN blocked:=true; END;
 IF NOT blocked THEN RAISE EXCEPTION 'Birth embedding overwrite accepted'; END IF;
 RAISE NOTICE 'PASS permanent QA, origin snapshot and birth embedding protection';
END $$;
ROLLBACK;
