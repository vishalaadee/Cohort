SET app.role='owner';

-- ============ THREE COLLEGES, DELIBERATELY OVERLAPPING ============
-- Same branch codes, same batch year, one shared student email, and drives
-- running at the same time. If tenancy leaks anywhere, this shape finds it.
INSERT INTO colleges (id,name,slug,email_domain,status) OVERRIDING SYSTEM VALUE VALUES
 (1,'Green Valley Institute of Technology','gvit','gvit.ac.in','active'),
 (2,'Sunrise Engineering College','sec','sec.edu.in','active'),
 (3,'Nirmala Technical Campus','ntc','ntc.ac.in','active');

INSERT INTO branches (id,college_id,code,name) OVERRIDING SYSTEM VALUE VALUES
 (1,1,'CSE','Computer Science'),(2,1,'ECE','Electronics'),(3,1,'MECH','Mechanical'),
 (4,2,'CSE','Computer Science'),(5,2,'IT','Information Technology'),
 (6,3,'CSE','Computer Science');

-- staff
INSERT INTO users (id,email,full_name) OVERRIDING SYSTEM VALUE VALUES
 (1,'tpo@gvit.ac.in','GVIT Placement Officer'),
 (2,'cr.cse@gvit.ac.in','GVIT CSE Representative'),
 (3,'cr.ece@gvit.ac.in','GVIT ECE Representative'),
 (4,'tpo@sec.edu.in','SEC Placement Officer'),
 (5,'cr.cse@sec.edu.in','SEC CSE Representative'),
 (6,'tpo@ntc.ac.in','NTC Placement Officer');

INSERT INTO memberships (user_id,college_id,branch_id,role,status,permissions) VALUES
 (1,1,NULL,'admin','active',NULL),
 -- CSE CR: full grant INCLUDING the new collect_outcomes
 (2,1,1,'sub_admin','active','["view_branch_dashboard","view_branch_roster","manage_branch_pipeline","manage_branch_questions","collect_outcomes"]'),
 -- ECE CR: deliberately MINIMAL — dashboard + roster only. Used to prove the
 -- admin_extra capability fix: this CR must NOT be able to advance rounds.
 (3,1,2,'sub_admin','active','["view_branch_dashboard","view_branch_roster"]'),
 (4,2,NULL,'admin','active',NULL),
 (5,2,4,'sub_admin','active','["view_branch_dashboard","view_branch_roster","manage_branch_pipeline"]'),
 (6,3,NULL,'admin','active',NULL);

-- students: C1 60 (30 CSE / 20 ECE / 10 MECH), C2 40 (25 CSE / 15 IT), C3 20 CSE
INSERT INTO students (id,college_id,branch_id,user_id,roll_no,email,full_name,cgpa,backlogs,batch_year,program_years,verified)
OVERRIDING SYSTEM VALUE
SELECT g, 1,
       CASE WHEN g<=30 THEN 1 WHEN g<=50 THEN 2 ELSE 3 END,
       NULL, 'GV'||lpad(g::text,3,'0'), 'gv'||g||'@gvit.ac.in', 'GVIT Student '||g,
       round((5.5 + (g%45)/10.0)::numeric,2), CASE WHEN g%11=0 THEN 2 ELSE 0 END,
       2026, 4, true
FROM generate_series(1,60) g;

INSERT INTO students (id,college_id,branch_id,user_id,roll_no,email,full_name,cgpa,backlogs,batch_year,program_years,verified)
OVERRIDING SYSTEM VALUE
SELECT 100+g, 2, CASE WHEN g<=25 THEN 4 ELSE 5 END, NULL,
       'SE'||lpad(g::text,3,'0'), 'se'||g||'@sec.edu.in', 'SEC Student '||g,
       round((6.0 + (g%38)/10.0)::numeric,2), 0, 2026, 4, true
FROM generate_series(1,40) g;

INSERT INTO students (id,college_id,branch_id,user_id,roll_no,email,full_name,cgpa,backlogs,batch_year,program_years,verified)
OVERRIDING SYSTEM VALUE
SELECT 200+g, 3, 6, NULL, 'NT'||lpad(g::text,3,'0'), 'nt'||g||'@ntc.ac.in', 'NTC Student '||g,
       round((6.5 + (g%30)/10.0)::numeric,2), 0, 2026, 4, true
FROM generate_series(1,20) g;

-- a student with a login, for the student-scope test
INSERT INTO users (id,email,full_name) OVERRIDING SYSTEM VALUE VALUES (50,'gv7@gvit.ac.in','GVIT Student 7');
UPDATE students SET user_id=50 WHERE id=7;

-- drives, running SIMULTANEOUSLY across all three colleges
INSERT INTO companies (id,college_id,name,category,package,min_cgpa,max_backlogs,eligible_branches,deadline,status,role_title)
OVERRIDING SYSTEM VALUE VALUES
 (1,1,'TCS',        'tier2', 350000,  6.0,0,'{CSE,ECE,MECH}', now()+interval '10 days',1,'Systems Engineer'),
 (2,1,'Google',     'dream',2500000,  8.0,0,'{CSE}',          now()+interval '20 days',1,'SWE'),
 (3,1,'LocalCore',  'core',  250000,  5.0,3,'{MECH}',         now()+interval '15 days',0,'GET'),      -- DRAFT
 (4,1,'ExpiredCo',  'tier2', 300000,  6.0,0,'{CSE}',          now()-interval '2 days', 1,'Analyst'),  -- deadline passed
 (5,2,'Infosys',    'tier2', 400000,  6.5,0,'{CSE,IT}',       now()+interval '12 days',1,'Engineer'),
 (6,2,'StartupX',   'tier1',1200000,  7.5,0,'{CSE}',          now()+interval '18 days',0,'Founding Eng'), -- DRAFT
 (7,3,'Wipro',      'tier2', 380000,  6.0,0,'{CSE}',          now()+interval '14 days',1,'Engineer');
SET app.role='owner';
-- GVIT (60): 28 placed, 8 higher studies, 2 ventures, 18 not placed, 4 unavailable
INSERT INTO student_outcomes (college_id,branch_id,student_id,batch_year,kind,is_primary,annual_ctc,source,verified)
SELECT 1,s.branch_id,s.id,2026,'placed_campus',true, 300000 + (s.id%12)*75000,'officer',true
  FROM students s WHERE s.college_id=1 AND s.id<=28;
INSERT INTO student_outcomes (college_id,branch_id,student_id,batch_year,kind,is_primary,institution_name,program_name,source,verified)
SELECT 1,s.branch_id,s.id,2026,'higher_studies',true,'IIT Bombay','M.Tech','officer',true
  FROM students s WHERE s.college_id=1 AND s.id BETWEEN 29 AND 36;
INSERT INTO student_outcomes (college_id,branch_id,student_id,batch_year,kind,is_primary,venture_name,source,verified)
SELECT 1,s.branch_id,s.id,2026,'entrepreneurship',true,'Venture '||s.id,'officer',true
  FROM students s WHERE s.college_id=1 AND s.id BETWEEN 37 AND 38;
INSERT INTO student_outcomes (college_id,branch_id,student_id,batch_year,kind,is_primary,source,verified)
SELECT 1,s.branch_id,s.id,2026,'not_placed',true,'officer',true
  FROM students s WHERE s.college_id=1 AND s.id BETWEEN 39 AND 56;
INSERT INTO student_outcomes (college_id,branch_id,student_id,batch_year,kind,is_primary,source,verified)
SELECT 1,s.branch_id,s.id,2026,'unavailable',true,'officer',true
  FROM students s WHERE s.college_id=1 AND s.id BETWEEN 57 AND 60;
-- 6 GVIT students cleared GATE; 4 of them are also placed (non-primary)
INSERT INTO student_outcomes (college_id,branch_id,student_id,batch_year,kind,is_primary,exam_name,source,verified)
SELECT 1,s.branch_id,s.id,2026,'competitive_exam',false,'GATE','officer',true
  FROM students s WHERE s.college_id=1 AND s.id IN (1,2,3,4,39,40);

-- SEC (40): 22 placed, 5 higher, 1 venture, 10 not placed, 2 unavailable
INSERT INTO student_outcomes (college_id,branch_id,student_id,batch_year,kind,is_primary,annual_ctc,source,verified)
SELECT 2,s.branch_id,s.id,2026,'placed_campus',true, 350000 + (s.id%9)*60000,'officer',true
  FROM students s WHERE s.college_id=2 AND s.id<=122;
INSERT INTO student_outcomes (college_id,branch_id,student_id,batch_year,kind,is_primary,institution_name,source,verified)
SELECT 2,s.branch_id,s.id,2026,'higher_studies',true,'NIT Trichy','officer',true
  FROM students s WHERE s.college_id=2 AND s.id BETWEEN 123 AND 127;
INSERT INTO student_outcomes (college_id,branch_id,student_id,batch_year,kind,is_primary,venture_name,source,verified)
SELECT 2,s.branch_id,s.id,2026,'entrepreneurship',true,'SEC Venture','officer',true
  FROM students s WHERE s.college_id=2 AND s.id = 128;
INSERT INTO student_outcomes (college_id,branch_id,student_id,batch_year,kind,is_primary,source,verified)
SELECT 2,s.branch_id,s.id,2026,'not_placed',true,'officer',true
  FROM students s WHERE s.college_id=2 AND s.id BETWEEN 129 AND 138;
INSERT INTO student_outcomes (college_id,branch_id,student_id,batch_year,kind,is_primary,source,verified)
SELECT 2,s.branch_id,s.id,2026,'unavailable',true,'officer',true
  FROM students s WHERE s.college_id=2 AND s.id BETWEEN 139 AND 140;

-- NTC (20): 6 placed, 3 higher, 9 not placed, 2 unavailable
INSERT INTO student_outcomes (college_id,branch_id,student_id,batch_year,kind,is_primary,annual_ctc,source,verified)
SELECT 3,s.branch_id,s.id,2026,'placed_campus',true, 320000,'officer',true
  FROM students s WHERE s.college_id=3 AND s.id<=206;
INSERT INTO student_outcomes (college_id,branch_id,student_id,batch_year,kind,is_primary,institution_name,source,verified)
SELECT 3,s.branch_id,s.id,2026,'higher_studies',true,'IISc','officer',true
  FROM students s WHERE s.college_id=3 AND s.id BETWEEN 207 AND 209;
INSERT INTO student_outcomes (college_id,branch_id,student_id,batch_year,kind,is_primary,source,verified)
SELECT 3,s.branch_id,s.id,2026,'not_placed',true,'officer',true
  FROM students s WHERE s.college_id=3 AND s.id BETWEEN 210 AND 218;
INSERT INTO student_outcomes (college_id,branch_id,student_id,batch_year,kind,is_primary,source,verified)
SELECT 3,s.branch_id,s.id,2026,'unavailable',true,'officer',true
  FROM students s WHERE s.college_id=3 AND s.id BETWEEN 219 AND 220;
