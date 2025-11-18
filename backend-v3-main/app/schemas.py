from typing import List
from pydantic import BaseModel, EmailStr,validator
from typing import Optional
from sqlalchemy.sql.sqltypes import Date, DateTime,Integer
from datetime import datetime
from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey


class College(BaseModel):
    college_id:int
    college_name:int
    
class StudentModel(BaseModel):
    urn     : str
    college_id: int
    full_name : str
    email   : EmailStr
    branch:str
    first_name:str
    last_name:str
    middle_name:Optional[str] = None
    ssc:float
    hsc:float
    ug:float
    pg:float
    ug_percentage:float
    backlogs:int
    sem1:float
    sem2:float
    sem3:float
    sem4:float
    sem5:Optional[float] = None
    sem6:Optional[float] = None
    sem7:Optional[float] = None
    sem8:Optional[float] = None
    current_backlogs:str
    history_backlogs:str
    no_of_x_grades:int
    other_grades:str
    ug_start_year:int
    ug_end_year:int
    ssc_board:str
    hsc_board:str
    hsc_start_year:int
    hsc_end_year:int
    ssc_start_year:int
    ssc_end_year:int
    entry_to_college:str
    rank:int
    gap_in_studies:str
    dob:datetime
    gender:str
    category:str
    native:str
    parents_name:str
    present_addr:str
    permanent_addr:str
    phone:str
    secondary_phone:Optional[str] | None
    verified:int
    resume_link : Optional[str] | None 
    class Config:
        orm_mode=True
    
class CompanyDetails(BaseModel):
    cname: str
    eligible_college_ids: str
    category:str
    package:float
    deadline:datetime
    internship_stipend:float
    date:datetime
    ssc:float
    hsc:float
    ug:float
    pg:float
    branch:str
    backlogs:int
    gender:str
    class Config:
        orm_mode=True
        
class CompanyStatusDetails(BaseModel):
    cid:int
    college_id: int
    cname: str
    status:int
    category:str
    package:float
    deadline:datetime
    internship_stipend:float
    date:datetime
    ssc:float
    hsc:float
    ug:float
    pg:float
    branch:str
    backlogs:int
    gender:str
    class Config:
        orm_mode=True

class RegisterStudent(BaseModel):
    urn:str
    email:EmailStr
    college_id: int
    
    
class Alumni(BaseModel):
    a_name:str
    a_cname:str
    usn:str
    a_email:str
    passout:int
    branch:str
    class Config:
        orm_mode:True
        
        
class BranchDetails(BaseModel):
    branch: str
    class Config:
        orm_mode=True

class StudentDetails(BaseModel):
    urn: str
    class Config:
        orm_mode=True

class EmailSchema(BaseModel):
   email: List[EmailStr]
   class config:
        orm_mode=True
        arbitrary_types_allowed = True
        

    
class Feedback(BaseModel):
    branch: str
    role: str
    ctc: float
    base: float
    technical_round: str
    hr_round: str
    tips: str
    topics_covered: str
    codinground_difficulty: int
    interview_difficulty: int
    overall_experience: int
    passing_year: int
    full_time:Optional[bool]
    stipend:float
    location:str
    mode:str
    class Config:
        orm_mode=True

class AddCompanyModel(BaseModel):
    cname    : str
    college_id: int
    category  :str
    package   : float
    internship_stipend : float
    deadline : datetime
    date : datetime
    ssc : float
    hsc : float
    ug : float
    pg : float
    branch : str
    backlogs : int
    gender:str
    status=int
    class Config:
        orm_mode=True
        arbitrary_types_allowed = True
        Schema_extra={
            'example':{
            'cname':'Fidelity',
            'category':'TIER-2',
            'package':'1200000.00',
            'internship_stipend':'35000',
            'deadline':'2020-02-01',
            'date':'2020-01-01',
            'ssc':'60.00',
            'hsc':'60.00',
            'ug':'7.00',
            'pg':'7.00',
            'branch':'CSE,CSBS,ISE',
            'backlogs':'0',
            'gender':'M,F'
                    }
        }

    
class ExtendDeadlineModel(BaseModel):
    deadline : datetime
    date : datetime
    class Config:
        orm_mode=True
    

class RemindModel(BaseModel):
    datesir:datetime
    cid:int
    class Config:
        orm_mode=True

class RemindModel2(BaseModel):
    cid:int
    link:str
    class Config:
        orm_mode=True

class FeedbackRemindModel(BaseModel):
    cid:int
    class Config:
        orm_mode=True
        
class UpdateMarks(BaseModel):
    urn:str
    sem5:float
    sem6:float
    class Config:
        orm_mode=True
                
class Placed(BaseModel):
    pid: int
    urn: str
    cid: int
    category_placed:str
    college_id: int
    feedback:Optional[bool] = False
    
class PlacedCategory(BaseModel):
    pid: int
    college_id: int
    name:str
    urn:str
    branch:str
    email:str
    gender:str
    phone:str
    tier1:Optional[bool] = False
    tier2:Optional[bool] = False
    internship:Optional[bool] = False
    summer_internship:Optional[bool] = False
    dream:Optional[bool] = False
    cid:int
    class config:
        orm_mode=True
        arbitrary_types_allowed = True 
          
class Settings(BaseModel):
    authjwt_secret_key:str='a37493dfbbf304be139adb2f2bcb4dc4ab306084126287b4914b463727b32260'


class LoginModel(BaseModel):
    urn:str
    password:str
    
class UpdateResumeLink(BaseModel):
    resume_link:str
    class Config:
        orm_mode=True

class RoundInfoUpdate(BaseModel):
    round_name:str
    status : int

    # @validator("status")
    # def validate_stats(cls,status,values):
    #     # print(values.get("round_name"))
    #     if status not in (0,1,-1):
    #         raise ValueError("Status must be -1,0,1")
    #     return status
    
class ProgressUpdate(BaseModel):
    rid:int
    progressData:  List[RoundInfoUpdate]