from pydantic import BaseModel, EmailStr
from sqlalchemy.sql.elements import Null
from sqlalchemy.sql.sqltypes import Date, DateTime, Float,Integer
from .database import Base
from sqlalchemy import Column,Integer,Boolean,Text,String,ForeignKey
from sqlalchemy import Index
class College(Base):
    __tablename__="college"
    college_id=Column(Integer,primary_key=True,unique=True)
    college_name=Column(String(100),unique=True)
    
class User(Base):
    __tablename__='students'
    urn=Column(String(100),primary_key=True,unique=True)
    college_id=Column(Integer,ForeignKey('college.college_id'))
    full_name=Column(String(100),unique=False)
    email=Column(String(80),unique=False)
    first_name=Column(String(125),unique=False)
    middle_name=Column(String(125),unique=False)
    last_name=Column(String(125),unique=False)
    branch=Column(String(25),unique=False)
    backlogs=Column(Integer,unique=False)
    ssc=Column(Float,unique=False)
    hsc=Column(Float,unique=False)
    ug=Column(Float,unique=False)
    pg=Column(Float,unique=False)
    ug_percentage=Column(Float,unique=False)
    sem1=Column(Float,unique=False)
    sem2=Column(Float,unique=False)
    sem3=Column(Float,unique=False)
    sem4=Column(Float,unique=False)
    sem5=Column(Float,unique=False)
    sem6=Column(Float,unique=False)
    sem7=Column(Float,unique=False)
    sem8=Column(Float,unique=False)
    current_backlogs=Column(String(30),unique=False)
    history_backlogs=Column(String(30),unique=False)
    no_of_x_grades=Column(Integer,unique=False)
    other_grades=Column(String(30),unique=False)
    ug_start_year=Column(Integer,unique=False)
    ug_end_year=Column(Integer,unique=False)
    ssc_board=Column(String(50),unique=False)
    hsc_board=Column(String(50),unique=False)
    hsc_start_year=Column(Integer,unique=False)
    hsc_end_year=Column(Integer,unique=False)
    ssc_start_year=Column(Integer,unique=False)
    ssc_end_year=Column(Integer,unique=False)
    entry_to_college=Column(String(40),unique=False)
    rank=Column(Integer,unique=False)
    gap_in_studies=Column(String(255),unique=False)
    dob=Column(DateTime,unique=False)
    gender=Column(String(1),unique=False)
    category=Column(String(10),unique=False)
    native=Column(String(10),unique=False)
    parents_name=Column(String(50),unique=False)
    present_addr=Column(Text,unique=False)
    permanent_addr=Column(Text,unique=False)
    phone=Column(String(14),unique=False)
    secondary_phone=Column(String(14),unique=False,default=Null)
    verified=Column(Integer,default=0)
    resume_link= Column(String(500),unique=False, default=Null)
    __table_args__ = (Index('urn_index', 'urn'), )
    def __repr__(self):
        return f"<User {self.name}"
    
class Resume(Base):
    __tablename__='resume'
    resume_id=Integer()
    urn=Column(String(100),ForeignKey('students.urn'),primary_key=True,unique=True)
class Credentials(Base):
    __tablename__ = 'credentials'
    urn=Column(String(100),ForeignKey('students.urn'),primary_key=True,unique=True)
    # college_id=Column(Integer,ForeignKey('college.college_id'))
    password=Column(String(50),unique=False)
    activated=Column(Boolean,default=False)
    __table_args__ = (Index('urn_index', 'urn'), )
    
class Registrations(Base):
    __tablename__='registrations'
    rid=Column(Integer,primary_key=True,autoincrement=True)
    college_id=Column(Integer,ForeignKey('college.college_id'))
    urn=Column(String(100),ForeignKey('students.urn'))
    cid=Column(Integer,ForeignKey('company.cid'))
    __table_args__ = (Index('urn_cid_index', 'urn','cid'), )

    def __repr__(self):
        return f"<Registrations{self.urn}"
class alumni(Base):
    __tablename__='alumni'
    aid=Column(Integer,primary_key=True,autoincrement=True)
    a_name=Column(String(100))
    a_cname=Column(String(100))
    usn=Column(String(100))
    a_email=Column(String(100))
    passout=Column(Integer)
    branch=Column(String(100))
    def __repr__(self):
        return f"<alumni {self.a_email}"
    
class Placed(Base):
    __tablename__='placed'
    pid=Column(Integer,primary_key=True,autoincrement=True)
    college_id=Column(Integer,ForeignKey('college.college_id'))
    urn=Column(String(100))
    cid=Column(Integer,ForeignKey('company.cid'))
    category_placed=Column(String(10),unique=False)
    feedback=Column(Boolean,default=False)
    __table_args__ = (Index('urn_category_index', 'urn', 'category_placed'), )
    def __repr__(self):
        return f"<Registrations{self.urn}"
class Placed_category(Base):

    __tablename__='placed_category'
    pid=Column(Integer,primary_key=True,autoincrement=True)
    college_id=Column(Integer,ForeignKey('college.college_id'))
    name=Column(String(30),nullable=False)
    urn=Column(String(100))
    branch=Column(String(10),nullable=False)
    gender=Column(String(10),nullable=False)
    email=Column(String(80),nullable=False)
    phone=Column(String(50),nullable=False)
    tier1=Column(Boolean,nullable=False,default=False)
    tier2=Column(Boolean,nullable=False,default=False)
    core=Column(Boolean,nullable=False,default=False)
    internship=Column(Boolean,nullable=False,default=False)
    summer_internship=Column(Boolean,nullable=False,default=False)
    dream=Column(Boolean,nullable=False,default=False)
    cid=Column(Integer,ForeignKey('company.cid'))
    __table_args__ = (Index('urn_index','urn'), )
    def repr(self):
        return f"<Placed_category {self.urn}"
    
class Company(Base):
    
    
    __tablename__='company'
    cid=Column(Integer,primary_key=True)
    # college_id=Column(Integer,ForeignKey('college.college_id'))
    eligible_college_ids=Column(String(100),unique=False)
    cname=Column(String(25),unique=False)
    category=Column(String(25),nullable=False)
    package=Column(Float,nullable=False)
    internship_stipend=Column(Float,nullable=True,default=0)
    deadline=Column(DateTime,nullable=False)
    date=Column(Date,nullable=False)
    ssc=Column(Float,nullable=False)
    hsc=Column(Float,nullable=False)
    ug=Column(Float,nullable=False)
    pg=Column(Float,nullable=False)
    branch=Column(String(100),nullable=False)
    backlogs=Column(Integer,nullable=False,default=0)
    status=Column(Integer,nullable=False,default=0)
    gender=Column(String(15),nullable=False,default="M,F")
    __table_args__ = (Index('cid_index','cid'), )

    def __repr__(self):
        return f"<Company {self.cname}"

class Feedback(Base):
    
    __tablename__='feedback'
    fid=Column(Integer,primary_key=True,autoincrement=True)
    college_id=Column(Integer,ForeignKey('college.college_id'))
    urn=Column(String(100),ForeignKey('students.urn'))
    sname=Column(String(25))
    branch=Column(String(25))
    cname=Column(String(25))
    role=Column(String(40))
    ctc=Column(Float)
    base=Column(Float)
    technical_round=Column(String(5000))
    hr_round=Column(String(5000))
    tips=Column(String(4000))
    topics_covered=Column(String(600))
    codinground_difficulty=Column(Integer)
    interview_difficulty=Column(Integer)
    overall_experience=Column(Integer)
    passing_year=Column(Integer)
    full_time=Column(Boolean)
    stipend=Column(Float)
    location=Column(String(25))
    mode=Column(String(25))
        
    def __repr__(self):
        return f"<Feedback {self.urn}"
    
class Offer(Base):
    __tablename__ ="offer"
    ofid = Column(Integer,primary_key=True,autoincrement=True)
    urn=Column(String(100),ForeignKey('students.urn'))
    is_internship = Column(Integer, default =0)    
    cid=Column(Integer,ForeignKey('company.cid'))
    category = Column(String(20), unique =False)
    
    
class Blacklist(Base):
    __tablename__ ="blacklist"
    bid = Column(Integer,primary_key=True,autoincrement=True)
    urn=Column(String(100),ForeignKey('students.urn'))
    credits = Column(Integer)
    company_count = Column(Integer)