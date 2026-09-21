-- Migration 0002: auth columns + users RLS.
-- Apply ONLY to a database created from the original v1 schema.
-- Fresh installs get all of this from backend/db-init/01-schema.sql.
ALTER TABLE users    ADD COLUMN IF NOT EXISTS password_hash text;
ALTER TABLE students ADD COLUMN IF NOT EXISTS activation_code text;
ALTER TABLE students ADD COLUMN IF NOT EXISTS claimed_at timestamptz;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS t_users ON users;
CREATE POLICY t_users ON users USING (app_role() = 'owner' OR id = app_user());
