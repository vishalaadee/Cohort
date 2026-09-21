-- Migration 0010: drive attachments (JD + up to 2 more), outbound mail log.
--
-- Additive and idempotent. Apply after 0009.
--   RDS:   ./scripts/migrate-rds.sh
--   local: docker exec -i infra-db-1 psql -U postgres -d placement < migrations/0010_attachments_and_mail.sql

-- ---------------------------------------------------------------------------
-- 1. Drive attachments — the job description and anything that travels with it.
--
--    Stored as bytea, exactly like `resumes` (0004). Not S3: a JD is a few
--    hundred KB, the file must be visible to the same RLS that governs the
--    drive, and an object store adds credentials, a lifecycle policy and a
--    second place for a tenant boundary to be got wrong. If attachments ever
--    outgrow this, the migration is to move `data` out and keep this table as
--    the metadata + permission record.
--
--    The cap of 3 per drive is enforced in the API, not here, so the officer
--    gets "you can attach at most 3 files" instead of a constraint violation.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS drive_attachments (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id   bigint NOT NULL REFERENCES colleges(id)  ON DELETE CASCADE,
  company_id   bigint NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  kind         text NOT NULL DEFAULT 'jd'
               CHECK (kind IN ('jd','form','brochure','other')),
  filename     text NOT NULL,
  mime         text NOT NULL,
  byte_size    int  NOT NULL,
  data         bytea NOT NULL,
  uploaded_by  bigint REFERENCES users(id) ON DELETE SET NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS drive_attachments_company_idx
  ON drive_attachments (college_id, company_id, created_at);

ALTER TABLE drive_attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE drive_attachments FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS t_drive_attachments ON drive_attachments;

-- Read: anyone in the college (students included — the JD is the point).
--       Whether the DRIVE is visible is decided by the companies policy and
--       the status filter in portal.py; this table does not re-litigate it.
-- Write: admin only. A CR cannot attach or remove a JD.
CREATE POLICY t_drive_attachments ON drive_attachments
  USING (app_role() = 'owner' OR college_id = app_college())
  WITH CHECK (app_role() = 'owner'
              OR (college_id = app_college() AND app_role() = 'admin'));

-- ---------------------------------------------------------------------------
-- 2. Outbound mail log.
--
--    notification_log (0009) records the DECISION to notify and gives us
--    idempotency. It does not record what happened to the actual message.
--    Until now nothing sent mail at all, so the distinction did not matter.
--    It does now: a send can fail per-recipient, and an officer asking "did
--    the students get it?" needs an answer that isn't "we wrote a row".
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mail_log (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id      bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  notification_id bigint REFERENCES notification_log(id) ON DELETE SET NULL,
  to_address      text NOT NULL,
  subject         text NOT NULL,
  status          text NOT NULL CHECK (status IN ('sent','failed','skipped')),
  error           text,
  attachments     int NOT NULL DEFAULT 0,
  sent_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS mail_log_college_idx ON mail_log (college_id, sent_at DESC);

ALTER TABLE mail_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE mail_log FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS t_mail_log ON mail_log;
CREATE POLICY t_mail_log ON mail_log
  USING (app_role() = 'owner' OR college_id = app_college())
  WITH CHECK (app_role() = 'owner'
              OR (college_id = app_college() AND app_role() = 'admin'));

-- ---------------------------------------------------------------------------
-- 3. Group address verification tokens.
--
--    colleges.notify_groups (0009) already carries {email, verified_at} per
--    group. publish_drive refuses to announce to an address with a null
--    verified_at — deliberately, so that setting the address and proving you
--    control it are two different acts. This is the missing second act.
--
--    Without it an officer (or anyone who reached an officer session) could
--    point every future announcement at an address outside the college.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS group_verifications (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id  bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  group_key   text NOT NULL CHECK (group_key IN ('students','juniors')),
  email       text NOT NULL,
  token       text NOT NULL,
  expires_at  timestamptz NOT NULL,
  consumed_at timestamptz,
  created_by  bigint REFERENCES users(id) ON DELETE SET NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (college_id, group_key, token)
);

CREATE INDEX IF NOT EXISTS group_verifications_lookup_idx
  ON group_verifications (college_id, group_key, consumed_at);
-- The token is the lookup key for the unauthenticated confirm, and it has no
-- college_id to narrow by. Without this it is a sequential scan per click.
CREATE INDEX IF NOT EXISTS group_verifications_token_idx
  ON group_verifications (token);

ALTER TABLE group_verifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE group_verifications FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS t_group_verifications ON group_verifications;
CREATE POLICY t_group_verifications ON group_verifications
  USING (app_role() = 'owner'
         OR (college_id = app_college() AND app_role() = 'admin'))
  WITH CHECK (app_role() = 'owner'
              OR (college_id = app_college() AND app_role() = 'admin'));

-- ---------------------------------------------------------------------------
-- 3b. Consuming a verification token, from a session with no tenant context.
--
--     The confirm link is opened by whoever receives mail at the group address.
--     There is no logged-in user and therefore no app.college_id, so app_college()
--     is NULL, so every RLS policy on group_verifications evaluates to NULL —
--     and the UPDATE silently matches zero rows. The link would fail with
--     "expired or already used" every single time, forever.
--
--     SECURITY DEFINER is the right tool and this is the shape that makes it
--     safe to use:
--       * it is the ONLY way in, and it is gated on a 256-bit token
--         (secrets.token_urlsafe(32)) that cannot be guessed or enumerated —
--         a wrong token returns zero rows and says nothing about why;
--       * it writes exactly two rows and returns no secret;
--       * `SET search_path = public` is not decoration. Without it, a caller
--         who can create objects could shadow a table name and have it resolve
--         inside a definer-rights function.
--     The token decides the college, so this cannot be steered across tenants.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION consume_group_verification(p_key text, p_token text)
RETURNS TABLE (out_college_id bigint, out_email text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $fn$
DECLARE
  v_college bigint;
  v_email   text;
BEGIN
  IF p_key NOT IN ('students','juniors') THEN
    RETURN;
  END IF;

  UPDATE group_verifications gv
     SET consumed_at = now()
   WHERE gv.group_key = p_key
     AND gv.token = p_token
     AND gv.consumed_at IS NULL
     AND gv.expires_at > now()
  RETURNING gv.college_id, gv.email INTO v_college, v_email;

  IF v_college IS NULL THEN
    RETURN;                      -- bad, used, or expired token
  END IF;

  -- Only confirm if the address still matches the one the token was issued
  -- for. An officer who changed the address after the mail went out must not
  -- have the old link confirm the new address.
  UPDATE colleges c
     SET notify_groups = jsonb_set(COALESCE(c.notify_groups, '{}'::jsonb),
                                   ARRAY[p_key, 'verified_at'],
                                   to_jsonb(now()::text), true)
   WHERE c.id = v_college
     AND c.notify_groups -> p_key ->> 'email' = v_email;

  IF NOT FOUND THEN
    RETURN;                      -- address changed since the mail was sent
  END IF;

  out_college_id := v_college;
  out_email := v_email;
  RETURN NEXT;
END
$fn$;

REVOKE ALL ON FUNCTION consume_group_verification(text, text) FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- 4. Grants.
--    The API connects as app_user, which is a non-superuser precisely so RLS
--    applies to it. A new table it has no grant on is a 500, not a leak — but
--    it is still a 500.
--
--    schema_migrations is written by scripts/migration-lib.sh, not here.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE
      ON drive_attachments, mail_log, group_verifications TO app_user;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
    GRANT EXECUTE ON FUNCTION consume_group_verification(text, text) TO app_user;
  END IF;
END $$;
