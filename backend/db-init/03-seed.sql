-- FORCE ROW LEVEL SECURITY (schema.sql) applies even to this table's owner
-- unless the connecting role has BYPASSRLS — which a non-superuser admin
-- account (including an RDS master user) does not have by default. Setting
-- the 'owner' scope satisfies the "owner sees/writes everything" branch of
-- every policy, so this seed script can insert across all tenants.
SET app.role = 'owner';

-- Demo college so the POC dashboard shows real numbers immediately.
INSERT INTO colleges (name, slug, email_domain, status)
VALUES ('Demo Institute of Technology', 'demo', 'demo.ac.in', 'active');

INSERT INTO branches (college_id, code, name) VALUES
 (1,'CSE','Computer Science'), (1,'ISE','Information Science'),
 (1,'ECE','Electronics'),      (1,'MECH','Mechanical');

INSERT INTO companies (college_id, name, category, package, min_cgpa, max_backlogs, eligible_branches, status) VALUES
 (1,'Rubicon Systems','tier1', 2400000, 8.0, 0, '{CSE,ISE}', 1),
 (1,'Nova Analytics','tier2',  1200000, 7.0, 1, '{CSE,ISE,ECE}', 1),
 (1,'Kessel Motors','core',     900000, 6.5, 2, '{MECH,ECE}', 1),
 (1,'Beacon Labs','dream',     3600000, 8.5, 0, '{CSE}', 2);

-- 40 demo students spread across branches with a realistic funnel
INSERT INTO students (college_id, branch_id, roll_no, email, full_name, cgpa, backlogs, verified)
SELECT 1,
       ((g % 4) + 1),
       '01DIT23' || lpad(g::text, 3, '0'),
       'student' || g || '@demo.ac.in',
       'Student ' || g,
       round((6 + random()*3.5)::numeric, 2),
       (random()*2)::int,
       true
FROM generate_series(1,40) g;

-- applications: ~28 students apply to company 2 (Nova), 18 to company 1 (Rubicon)
INSERT INTO applications (college_id, branch_id, company_id, student_id, current_round, status)
SELECT s.college_id, s.branch_id, 2, s.id,
       (ARRAY['resume_screening','online_assessment','technical_1','technical_2','hr','final_placement'])[1 + (s.id % 6)],
       CASE WHEN s.id % 7 = 0 THEN 'placed' WHEN s.id % 11 = 0 THEN 'rejected' ELSE 'active' END
FROM students s WHERE s.id <= 28;

INSERT INTO applications (college_id, branch_id, company_id, student_id, current_round, status)
SELECT s.college_id, s.branch_id, 1, s.id,
       (ARRAY['resume_screening','online_assessment','technical_1','technical_2','technical_3','hr'])[1 + (s.id % 6)],
       CASE WHEN s.id % 9 = 0 THEN 'placed' ELSE 'active' END
FROM students s WHERE s.id <= 18 AND s.cgpa >= 8.0;

-- offers for the placed students
INSERT INTO offers (college_id, student_id, company_id, category, is_special)
SELECT college_id, student_id, company_id,
       CASE company_id WHEN 1 THEN 'tier1' ELSE 'tier2' END,
       (student_id % 13 = 0)
FROM applications WHERE status = 'placed';

-- a couple of interview experiences (the differentiator KB)
INSERT INTO feedback (college_id, student_id, company_id, role, ctc, rounds, difficulty, topics, tips) VALUES
 (1, 7, 2, 'SDE Intern', 1200000, 'OA + 2 tech + HR', 3, 'DP, graphs, SQL', 'Practice mediums on the topics list; be clear about time complexity.'),
 (1, 14,1, 'Software Engineer', 2400000, 'OA + 3 tech + HR', 4, 'System design basics, trees, OOP', 'They probe depth on your projects — know your own repo cold.');

-- ---- demo logins (CHANGE/DELETE before any real use) ----
-- admin:   admin@demo.ac.in / demo1234
-- student: student1@demo.ac.in / student123   (pre-claimed account)
INSERT INTO users (email, full_name, password_hash) VALUES
 ('admin@demo.ac.in',   'Demo Admin',  '$2b$12$lzt//IaVMi023jxlZDuJXup6YHwI34fkSxjY1TcC8NOcoEUSbC2lu'),
 ('student1@demo.ac.in','Student 1',   '$2b$12$yMU1f0FrhB9DCI8lgzuiuOFPks9cc1G7xjG/8ERPbuqz2BJw9TiNe');
INSERT INTO memberships (user_id, college_id, role) VALUES (1, 1, 'admin');
UPDATE students SET user_id = 2, verified = true, claimed_at = now()
 WHERE college_id = 1 AND roll_no = '01DIT23001';

-- activation codes for a few unclaimed students, to demo the claim flow
UPDATE students SET activation_code = 'DEMO' || lpad(id::text, 4, '0')
 WHERE college_id = 1 AND user_id IS NULL AND id <= 10;
