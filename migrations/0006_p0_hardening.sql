-- Migration 0006: P0 delivery hardening.
--
-- Escalations must create a durable, actionable item for the placement
-- officer. A role-addressed notification keeps the workflow valid when a
-- college has more than one placement officer.

CREATE TABLE IF NOT EXISTS notifications (
  id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id         bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  recipient_role     text NOT NULL CHECK (recipient_role IN ('admin')),
  kind               text NOT NULL CHECK (kind IN ('question_escalated')),
  title              text NOT NULL,
  body               text,
  resource_type      text NOT NULL CHECK (resource_type IN ('question')),
  resource_id        bigint NOT NULL,
  created_by_user_id bigint REFERENCES users(id) ON DELETE SET NULL,
  created_at         timestamptz NOT NULL DEFAULT now(),
  read_at            timestamptz,
  UNIQUE (college_id, recipient_role, kind, resource_type, resource_id)
);
CREATE INDEX IF NOT EXISTS notifications_admin_inbox_idx
  ON notifications (college_id, recipient_role, read_at, created_at DESC);

ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS t_notifications ON notifications;
CREATE POLICY t_notifications ON notifications
  USING (
       app_role() = 'owner'
    OR (college_id = app_college() AND app_role() = 'admin'
        AND recipient_role = 'admin')
  )
  WITH CHECK (
       app_role() = 'owner'
    OR (college_id = app_college() AND app_role() = 'admin'
        AND recipient_role = 'admin')
    -- A branch CR can create only a placement-officer notification. No API
    -- exposes arbitrary notification creation; this is for the escalation
    -- transaction below, while RLS remains a useful backstop.
    OR (college_id = app_college() AND app_role() = 'sub_admin'
        AND recipient_role = 'admin' AND kind = 'question_escalated'
        AND resource_type = 'question')
  );
