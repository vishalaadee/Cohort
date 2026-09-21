-- Migration 0007: configurable CR permission grants.
--
-- Do not patch production schemas by hand. CR access is tracked here as
-- membership-level JSON data, and application code maps it to a fixed allow-list.

ALTER TABLE memberships
  ADD COLUMN IF NOT EXISTS permissions jsonb;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'memberships_permissions_array_chk'
  ) THEN
    ALTER TABLE memberships
      ADD CONSTRAINT memberships_permissions_array_chk
      CHECK (permissions IS NULL OR jsonb_typeof(permissions) = 'array');
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS memberships_college_role_status_idx
  ON memberships (college_id, role, status);

DROP POLICY IF EXISTS t_memberships ON memberships;
CREATE POLICY t_memberships ON memberships
  USING (
       app_role() = 'owner'
    OR user_id = app_user()
    OR (college_id = app_college() AND app_role() = 'admin')
  )
  WITH CHECK (
       app_role() = 'owner'
    OR user_id = app_user()
    OR (college_id = app_college() AND app_role() = 'admin')
  );

DROP POLICY IF EXISTS t_users ON users;
CREATE POLICY t_users ON users
  USING (
       app_role() = 'owner'
    OR id = app_user()
    OR (
      app_role() = 'admin'
      AND EXISTS (
        SELECT 1 FROM memberships m
        WHERE m.user_id = users.id
          AND m.college_id = app_college()
          AND m.status = 'active'
      )
    )
  );
