-- ============================================================
-- Dummy data: a second college whose students use personal Gmail
-- Run this in DBeaver (or psql) as the RDS master user.
-- Then import roster-gnc.csv through the app's Import screen.
-- ============================================================

-- RLS applies even to the admin account; claim the owner scope first.
SET app.role = 'owner';

-- The college. slug 'gnc' is what students type in the Claim form.
-- email_domain is NULL on purpose: students use personal Gmail, so there is
-- no domain to auto-map. Google sign-in still works for them because roster
-- matching is by EXACT EMAIL — a Gmail on the roster can "Continue with
-- Google" and land verified.
INSERT INTO colleges (name, slug, email_domain, status)
VALUES ('Greenfield National College', 'gnc', NULL, 'active');

-- The placement officer's login for this college.
-- Email: placements.gnc@gmail.com   Password: gncadmin1
-- (bcrypt hash below is for 'gncadmin1' — CHANGE after first login flow exists)
INSERT INTO users (email, full_name, password_hash)
VALUES ('placements.gnc@gmail.com', 'GNC Placement Officer',
        '$2b$12$REPLACE_ME_RUN_GENERATOR_BELOW');
-- Generate the real hash on your laptop and paste it above before running:
--   python3 -c "import bcrypt;print(bcrypt.hashpw(b'gncadmin1',bcrypt.gensalt()).decode())"

INSERT INTO memberships (user_id, college_id, role)
VALUES (currval('users_id_seq'), currval('colleges_id_seq'), 'admin');

-- Four drives with varied eligibility so the dashboard looks real
INSERT INTO companies (college_id, name, category, package, min_cgpa, max_backlogs, eligible_branches, deadline, status) VALUES
 (currval('colleges_id_seq'), 'Zentrix Software',  'tier1', 1800000, 8.0, 0, '{CSE,ISE,AIML}',      now() + interval '10 days', 1),
 (currval('colleges_id_seq'), 'BharatPay Fintech', 'tier2', 1100000, 7.0, 1, '{CSE,ISE,ECE,AIML}',  now() + interval '7 days',  1),
 (currval('colleges_id_seq'), 'Ashoka Motors',     'core',   750000, 6.5, 2, '{MECH,CIVIL,ECE}',    now() + interval '14 days', 1),
 (currval('colleges_id_seq'), 'CloudNine Labs',    'dream',  3200000, 8.5, 0, '{CSE,AIML}',          now() + interval '5 days',  0);
