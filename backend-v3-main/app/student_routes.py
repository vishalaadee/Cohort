from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from email import message
import asyncpg
from pydantic import EmailStr, BaseModel
from unicodedata import category
from pydantic import BaseModel
import jwt
from jose import JWTError, jwt
from fastapi.encoders import jsonable_encoder
from datetime import datetime, timedelta
from fastapi import UploadFile, File, APIRouter, Depends, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from werkzeug.security import generate_password_hash, check_password_hash
from fastapi_jwt_auth import AuthJWT
from fastapi.exceptions import HTTPException
import pytz
import boto3
from botocore.exceptions import ClientError
import ast
from datetime import datetime, timezone
from starlette.responses import JSONResponse
import json
from typing import List, Optional
import databases
from sqlalchemy.orm import Session
from .models import Blacklist, User, Feedback, Credentials, Company, Placed, Placed_category,Offer, College, Registrations
from . import crud, models
from .database import Session, engine
from .schemas import CompanyDetails, StudentDetails, StudentModel
from . import crud, models, schemas
from dotenv import load_dotenv
from fastapi_pagination import Page, paginate, Params
from sqlalchemy import func # for Aggerate function MAX in finding highet placed package
import os , logging
logger = logging.getLogger("my_logger")
load_dotenv()

def generate_password():
    import random
    # import array
    import string
    alphabet = string.ascii_letters + string.digits
    password = ''.join(random.choice(alphabet) for i in range(9))
    return password


conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_FROM=os.getenv("MAIL_FROM"),
    MAIL_PORT=587,
    MAIL_SERVER="smtp.gmail.com",
    MAIL_FROM_NAME="Placement-Information",
    MAIL_TLS=True,
    MAIL_SSL=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)


def get_session():
    session = Session()
    try:
        yield session
    finally:
        session.close()


def get_db():
    try:
        db = Session()
        yield db
    finally:
        db.close()


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="student/login", scheme_name="student")

ALGORITHM = "HS256"
JWT_SECRET = os.getenv("JWT_SECRET")
ACCESS_TOKEN_EXPIRE_MINUTES = 100


class Token(BaseModel):
    access_token: str
    token_type: str
    college_id: int


class TokenData(BaseModel):
    username: Optional[str] = None


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_student(request:Request, token: str = Depends(oauth2_scheme)):

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        role = payload.get("role")
        current_user = payload.get("urn")
        request_user = request.path_params['urn'].upper().strip()
        if role != 'student':
            raise credentials_exception
        if current_user != request_user:
            raise credentials_exception
        
    except JWTError:
        raise credentials_exception

    return True


session = Session(bind=engine)

itemrouter = APIRouter(
    prefix='/student',
    tags=['student']

)


# @itemrouter.post("/login", response_model=Token,include_in_schema=True)


@itemrouter.post("/login", include_in_schema=True)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)): # type: ignore # type: ignore # type: ignore
    urn = str(form_data.username)
    urn = urn.upper()
    urn=urn.strip()
    password = str(form_data.password)
    college_id = db.query(User.college_id).filter(User.urn == urn).first()
    if(college_id == None):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    college_id = college_id.college_id
    # return college_id
    
    urn = urn.strip()
    db_user = db.query(Credentials).filter(urn == Credentials.urn).first()

    if db_user and check_password_hash(db_user.password, password):

        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"urn": urn, "role":'student'}, expires_delta=access_token_expires
        )
    else:
        logger.error("Invalid")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"access_token": access_token, "token_type": "bearer", "college_id": college_id}
    
        


@itemrouter.get("/get_college")
def get_college_id(college_id: int, db: Session = Depends(get_db)): # type: ignore
    return db.query(models.College).filter(college_id == College.college_id).first()


@itemrouter.get("/get_all_student_in_college")
def get_all_students_from_this_college(college_id: int, db: Session = Depends(get_db)): # type: ignore
    return db.query(models.User).filter(college_id == User.college_id).all()


@itemrouter.post("/home/register", status_code=status.HTTP_201_CREATED)
async def register(urn: str, email: EmailStr, db: session = Depends(get_db)) -> JSONResponse: # type: ignore # type: ignore
    urn = urn.upper()
    urn = urn.strip()
    email = email.strip()
    email = email.lower()

    #  db_email=session.query(User).filter(User.email==email).first()
    db_urn = session.query(User).filter(User.urn == urn).first()
    if not db_urn:
        return JSONResponse(status_code=200, content={"message": "Invalid URN/USN"})
    db_cred = session.query(Credentials).filter(Credentials.urn == urn).first()
    db_email = db_urn.email
    db_email = db_email.lower()
    db_email = db_email.strip()
    if db_urn and (db_email == email) and db_cred == None:
        a = generate_password()
        message = MessageSchema(
            subject="JSS INSTITUTION Placement Portal Registration",
            recipients=[email],  # List of recipients, as many as you can pass
            body="your password is "+a,

        )
        a = generate_password_hash(a)
        credentials = Credentials(urn=urn, password=a, activated=True)
        db_urn.verified = 1
        session.add(credentials)
        session.commit()
        fm = FastMail(conf)
        await fm.send_message(message)
        return JSONResponse(status_code=200, content={"message": "email has been sent"})
    elif db_urn and (db_urn.email == email) and (db_cred.activated == True):
        return JSONResponse(status_code=200, content={"message": "Account Already Activated"})
    else:
        return JSONResponse(status_code=200, content={"message": "Check if your data exists in database (in correct format)"})


@itemrouter.post("/home/forgot_password", status_code=status.HTTP_201_CREATED)
async def forgot_pass(urn: str, email: EmailStr, db: session = Depends(get_db)) -> JSONResponse: # type: ignore
    urn = urn.upper()
    urn = urn.strip()
    email=email.strip()
    email = email.lower()
    #  db_email=session.query(User).filter(User.email==email).first()
    db_urn = db.query(User).filter(User.urn == urn).first()
    db_cred = db.query(Credentials).filter(Credentials.urn == urn).first()
    if db_urn and (db_urn.email.lower() == email) and db_cred != None:
        db_user = crud.get_item_by_credentials(db, urn)
        a = generate_password()
        message = MessageSchema(
            subject="New Password",
            recipients=[email],  # List of recipients, as many as you can pass
            body="your password is "+a,

        )
        a = generate_password_hash(a)
        db_user[0].password = a
        db.commit()
        fm = FastMail(conf)
        await fm.send_message(message)
        return JSONResponse(status_code=200, content={"message": "email has been sent"})
    elif db_urn and (db_urn.email == email) and (db_cred == None):
        return JSONResponse(status_code=200, content={"message": "Account yet not activated"})
    else:
        return JSONResponse(status_code=401, content={"message": "Invalid Credentials"})


@itemrouter.post("/home/changepassword/{urn}")
def change_password_student(urn: str, oldpass: str, newpass: str, db: Session = Depends(get_db), b: bool = Depends(get_current_student)): # type: ignore
    urn = urn.upper()
    urn = urn.strip()
    db_user = crud.get_item_by_credentials(db, urn)
    if db_user:
        if check_password_hash(db_user[0].password, oldpass):
            newpass = generate_password_hash(newpass)
            db_user[0].password = newpass
            db.commit()
            return {"message": "Password changed successfully"}
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Incorrect Old Password")
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Wrong Original Password")


@itemrouter.get("/home/all_companies", response_model=List[CompanyDetails], include_in_schema=True)
def show_records(db: Session = Depends(get_db), b: bool = Depends(get_current_student)): # type: ignore
    records = db.query(models.Company).all()
    return records


@itemrouter.get("/home/thirdyear/all_companies", response_model=List[CompanyDetails], include_in_schema=True)
def show_records_jnr(db: Session = Depends(get_db)): # type: ignore # type: ignore
    records = db.query(models.Company).filter_by(
        category="summer_internship").all()
    return records


@itemrouter.get("/home/total_company_count", include_in_schema=True)
def show_count(db: Session = Depends(get_db), b: bool = Depends(get_current_student)): # type: ignore
    records = db.query(models.Company.cid).all()
    records = str(records)
    data = json.dumps(ast.literal_eval(records))
    data = json.loads(data)
    return len(data)


@itemrouter.get("/home/total_company_count_incollege", include_in_schema=True)
def show_count_incollege(college_id: int, db: Session = Depends(get_db)): # type: ignore
    records = db.query(models.Company).filter(
        Company.eligible_college_ids.contains(str(college_id))).all()
    # return len(records)
    return (records)


@itemrouter.get("/home/upcoming_companies/{college_id}", include_in_schema=True)
def upcoming_companies(college_id:int,db: Session = Depends(get_db)): # type: ignore
    IST = pytz.timezone('Asia/Kolkata')
    datetime_ist = datetime.now(IST)
    cur_date_time = datetime_ist.strftime('%Y-%m-%d %H:%M:%S')
    cur_date_time = datetime.strptime(cur_date_time, '%Y-%m-%d %H:%M:%S')
    try:
        records = db.query(models.Company.cname, models.Company.date).filter(Company.date >= cur_date_time).filter(
            Company.status != 3).filter(Company.eligible_college_ids.contains(str(college_id))).order_by(Company.date.asc()).all()
        if (len(records)==0):
            return [{'cname':"message", "date":"No Upcoming Companies"}]
        return records
    except:
        db.rollback()


@itemrouter.put("/update_marks/", status_code=status.HTTP_201_CREATED)
def update_marks(user: schemas.UpdateMarks, session=Depends(get_db), b: bool = Depends(get_current_student)):

    dc = session.query(User).filter(User.urn == user.urn.upper()).first()
    if dc is None:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="Student doesn't exists"
                             )

    dc.urn = user.urn,
    dc.sem5 = user.sem5,
    dc.sem6 = user.sem6,
    dc.sem7 = user.sem7,
    dc.sem8 = user.sem8

    session.commit()

    return {"message": "Student Marks Updated"}

@itemrouter.get("/feedbacks/details/{college_id}", include_in_schema=True)
def feedbacks(college_id:int , branch: str | None = None, db: Session = Depends(get_db), stud: str | None = None, company: str | None = None, params: Params = Depends(), b: bool = Depends(get_current_student)):
    stud = '%' + stud + '%' if stud else None
    company = '%' + company + '%' if company else None
    branch = '%' + branch + '%' if branch else None
    
    query = db.query(Feedback).filter(Feedback.college_id == college_id)
    
    if stud is not None:
        query = query.filter(Feedback.sname.ilike(stud))
    if company is not None:
        query = query.filter(Feedback.cname.ilike(company))
    if branch is not None:
        query = query.filter(Feedback.branch.ilike(branch))
    
    return paginate(query.distinct(Feedback.urn).all(), params)


#New route for feedback by urn/usn
@itemrouter.get("/feedbacks/individual_details/{fid}", include_in_schema=True)
def feedbacks(fid:int ,db: Session = Depends(get_db), b: bool = Depends(get_current_student)): # type: ignore
    return db.query(Feedback).filter(Feedback.fid==fid).distinct(Feedback.fid).all()


# @itemrouter.post("/home/eligible/register/{urn}", include_in_schema=True)
# def record_placed(urn: str, db: Session = Depends(get_db), b: bool = Depends(get_current_student)):
    urn = urn.upper()
    records = crud.placed_item(db, urn=urn)

    # return records
    records = str(records)
    # return records
    data = json.dumps(ast.literal_eval(records))
    data = json.loads(data)
    # return data
    # data is in list of list
    categoryCount = len(data)
    categories = []
    for i in range(0, categoryCount):
        categories.append(data[i][0])
    # return categories

    records2 = db.query(models.Company.cid).all()
    records2 = str(records2)
    # return records2
    data2 = json.dumps(ast.literal_eval(records2))
    data2 = json.loads(data2)
    # return data2
    array_eligible_cid = {"company_details": [],
                          "eligible": [], "is_registered": []}
    # for i in data2:
    #     return i[0]

    student_variable = crud.get_item_by_urn(db, urn=urn)
    # return student_variable

    s_verified = student_variable.verified
    s_ssc = student_variable.ssc
    s_hsc = student_variable.hsc
    s_ug = student_variable.ug
    s_pg = student_variable.pg
    s_backlogs = student_variable.current_backlogs
    s_branch = student_variable.branch
    s_gender = student_variable.gender
    s_college_id = student_variable.college_id
    if s_gender == "male" or s_gender == "Male" or s_gender == "MALE":
        s_gender = "M"
    elif s_gender == "female" or s_gender == "Female" or s_gender == "FEMALE":
        s_gender = "F"

    company_variables = crud.item_of_company(db)

    for i in range(len(data2)):
        c_cid = company_variables[i].cid
        c_hsc = company_variables[i].hsc
        c_ssc = company_variables[i].ssc
        c_ug = company_variables[i].ug
        c_pg = company_variables[i].pg
        c_backlogs = company_variables[i].backlogs
        c_branch = company_variables[i].branch
        c_category = company_variables[i].category
        c_package = company_variables[i].package
        c_deadline = company_variables[i].deadline
        c_status = company_variables[i].status
        c_gender = company_variables[i].gender
        c_eligible_college_ids = company_variables[i].eligible_college_ids

        nonCircuitBranches = ['MECH', 'EE', 'EEE', 'CE']
        category_condition = ''
        # logic-> a student can take 2 offers from tier1,tier2,tier3,dream
        # tier 1-> upto 7 lpa , tier2->7-15 lpa, tier3->15-20 lpa, dream->20+ lpa
        # a student can take one offer from internship/core so total 3 offers
        IST = pytz.timezone('Asia/Kolkata')
        datetime_ist = datetime.now(IST)
        cur_date_time = datetime_ist.strftime('%Y-%m-%d %H:%M:%S')
        cur_date_time = datetime.strptime(cur_date_time, '%Y-%m-%d %H:%M:%S')

        eligible = True
        # return c_eligible_college_ids
        list_college_ids = []
        if c_eligible_college_ids:
            list_college_ids = c_eligible_college_ids.split(",")

        if str(s_college_id) not in list_college_ids:
            eligible = False

        if str(s_college_id) == "3":
            if c_status == 2:
                eligible = False
            else:
                if (c_deadline > cur_date_time):
                    eligible = True
                elif (((c_deadline < cur_date_time) == True) and (c_status == 1)):
                    eligible = False
                    company_variables[i].status = 2
                    db.commit()

                if c_status != 1 or (s_gender not in c_gender) or (s_branch not in c_branch) or (c_deadline < cur_date_time) or s_hsc < c_hsc or s_ssc < c_ssc or ((s_ug < c_ug and s_pg == -1) or (s_pg != -1 and s_pg < c_pg)) or (c_backlogs == 0 and s_backlogs != '0') or s_verified != 1 or (c_category in categories):
                    eligible = False

                elif categoryCount == 2:
                    if (("internship" or "core") in categories) or (not (c_category in ["internship", "core"])):
                        eligible = False
                elif categoryCount == 2:
                    # if internship is in s_category then he is eligible for a third offer
                    if (("internship") in categories or ("core") in categories):
                        if (c_category == "internship" or c_category == "core"):
                            eligible = False
                        elif ("tier1" in categories):
                            if (c_category == "tier1"):
                                eligible = False
                        elif ("tier2" in categories):
                            if ((c_category == "tier1") or (c_category == "tier2")):
                                eligible = False
                        elif ("tier3" in categories):
                            if ((c_category == "tier1") or (c_category == "tier2") or (c_category == "tier3")):
                                eligible = False
                        elif ("dream" in categories):
                            if ((c_category == "tier1") or (c_category == "tier2") or (c_category == "tier3") or (c_category == "dream")):
                                eligible = False
                    else:
                        if (c_category != "internship" or c_category != "core"):
                            eligible = False
                elif categoryCount == 3:
                    eligible = False
                elif categoryCount == 1:
                    if ("tier1" in categories):
                        if (c_category == "tier1"):
                            eligible = False
                    elif ("tier2" in categories):
                        if ((c_category == "tier1") or (c_category == "tier2")):
                            eligible = False
                    elif ("tier3" in categories):
                        if ((c_category == "tier1") or (c_category == "tier2") or (c_category == "tier3")):
                            eligible = False
                    elif ("dream" in categories):
                        if ((c_category == "tier1") or (c_category == "tier2") or (c_category == "tier3") or (c_category == "dream")):
                            eligible = False
                    elif ("core" in categories):
                        if ((c_category == "core") or (c_category == "internship")):
                            eligible = False
                    elif ("internship" in categories):
                        if ((c_category == "internship") or (c_category == "core")):
                            eligible = False
                else:
                    eligible = True

            exist = db.query(models.Registrations.urn).filter_by(
                cid=c_cid).all()

            records = str(exist)
            data = json.dumps(ast.literal_eval(records))
            exist = json.loads(data)

            is_registered = False
            for j in exist:
                if urn == j[0]:
                    eligible = False
                    is_registered = True
            company_variables = crud.item_of_company(db)
            array_eligible_cid["company_details"].append(company_variables[i])
            array_eligible_cid["eligible"].append(eligible)
            array_eligible_cid["is_registered"].append(is_registered)

        else:
            if c_status == 2:
                eligible = False
            else:
                if c_category == "other" and (c_deadline > cur_date_time):
                    eligible = True
                elif (((c_deadline < cur_date_time) == True) and (c_status == 1)):
                    eligible = False
                    company_variables[i].status = 2
                    db.commit()
                elif c_category == "summer_internship":
                    eligible = False
                elif c_status != 1 or (s_gender not in c_gender) or (s_branch not in c_branch) or (c_deadline < cur_date_time) or s_hsc < c_hsc or s_ssc < c_ssc or ((s_ug < c_ug and s_pg == -1) or (s_pg != -1 and s_pg < c_pg)) or (c_backlogs == 0 and s_backlogs != '0') or s_verified != 1 or (c_category in categories):
                    eligible = False
                elif ("dream" in categories):
                    eligible = False
                elif categoryCount >= 2 and (not (c_category in ["dream", "special"])):
                    eligible = False
                elif categoryCount == 1:
                    if ("tier1" in categories):
                        if (s_branch in nonCircuitBranches):
                            if (not (c_category in ["core", "tier2", "internship", "dream", "special"])):
                                eligible = False
                        else:
                            if (not (c_category in ["tier2", "internship", "dream", "special"])):
                                eligible = False
                    elif ("core" in categories):
                        if (not (c_category in ["tier2", "internship", "dream", "special"])):
                            eligible = False
                    elif ("tier2" in categories):
                        if (not (c_category in ["dream", "special"])):
                            eligible = False
                    elif ("internship" in categories):
                        if (s_branch in nonCircuitBranches) and c_category == 'core':
                            eligible = True
                        # assuming internship and summer internship sirf tier 2 me hota hai
                        elif (not (c_category in ["tier2", "dream", "special"])):
                            eligible = False
                else:
                    eligible = True

            exist = db.query(models.Registrations.urn).filter_by(
                cid=c_cid).all()
            records = str(exist)
            data = json.dumps(ast.literal_eval(records))
            exist = json.loads(data)
            is_registered = False
            for j in exist:
                if urn == j[0]:
                    eligible = False
                    is_registered = True
            company_variables = crud.item_of_company(db)
            array_eligible_cid["company_details"].append(company_variables[i])
            array_eligible_cid["eligible"].append(eligible)
            array_eligible_cid["is_registered"].append(is_registered)

    return array_eligible_cid


@itemrouter.post("/home/file/show_resume/{urn}", include_in_schema=True)
def show(urn: str, b: bool = Depends(get_current_student)):
    urn = urn.upper()
    urn = urn + ".pdf"
    try:
        client.head_object(Bucket='resumesnoida', Key=urn)
    except ClientError:
        return False

    url = client.generate_presigned_url(
        ClientMethod='get_object',
        Params={
            'Bucket': 'resumesnoida',
            'Key': urn,
        },
        ExpiresIn=600
    )

    return url
# @itemrouter.post("/home/eligible/debug_register/{urn}", include_in_schema=True)

@itemrouter.get("/home/registered/{urn}", include_in_schema=True)
async def registered(urn:str, db:Session = Depends(get_db), b: bool = Depends(get_current_student)):
    try:
        registerations = db.query(Registrations).filter(Registrations.urn == urn).all()

        registered_companies = []

        for registration in registerations:
            company = db.query(Company).filter(Company.cid == registration.cid).first()
            if company.status != 3:
                company_details = {
                    "cname": company.cname,
                    "package": company.package,
                    "eligible_college_ids": company.eligible_college_ids,
                    "deadline": company.deadline,
                    "ssc": company.ssc,
                    "ug": company.ug,
                    "branch": company.branch,
                    "status": company.status,
                    "category": company.category,
                    "cid": company.cid,
                    "internship_stipend": company.internship_stipend,
                    "date": company.date,
                    "hsc": company.hsc,
                    "pg": company.pg,
                    "backlogs": company.backlogs,
                    "gender": company.gender
                }    

                registered_companies.append(company_details)
        return registered_companies

    except Exception as e:
        return e

@itemrouter.post("/home/eligible/register/{urn}", include_in_schema=True)
async def debug_register(urn:str, db:Session = Depends(get_db), b: bool = Depends(get_current_student)):
    try:

        non_circuit_branches = [
            'MECH',
            'IP',
            "CV",
            "CTM",
            "PST",
            "BT",
            "ENV",
            "MSC_Math",
            "MSC_Phy",
            "MSC_Chem",
            "MSC_AnaChem",
            "MSC_Poly",
            "MSC_Bio","Polymer_Science",
            "Energy_Systems_Management",
            "Mechanical_Engineering_PG",
            "Automotive_Electronics",
            "Industrial_Structures",
            "Infrastructure_Engineering_Management",
            "Environmental_PG",
            "Health_Science_Water_Treatment",
            "Material_Science",
            "MBA_Financial_Management",
            "MBA_Retail_Management",
            "MBA_Digital_Marketing",
            "MBA_Finance",
            "MBA_Marketing",
            "MBA_HR",
            
        ]

        # 1.) Fetch student's record for checking their eligiblity
        urn=urn.upper()
        urn=urn.strip()
        blacklist_record = db.query(Blacklist).filter(Blacklist.urn ==urn).first()
        
        student = db.query(User).filter(User.urn==urn).first()
        stud_branch = student.branch
        
        # 2.) Fetch all the companies whose deadline has not reached yet
        companies = db.query(Company).filter(Company.deadline>=datetime.now(tz=pytz.timezone('Asia/Kolkata'))).filter(Company.status==1).all()

        if blacklist_record is not None:
            if blacklist_record.credits == 0:
                return  [{"msg": "You have been blacklisted"}]

        if (companies == []):
            return "No companies available"

        # Initialize an array of array of cids
        array_cids =[]
        i=-1

        is_placed = db.query(Placed).filter(Placed.urn == urn).all()
        placed_cids = []
        for placed_comp_detail in is_placed:
            placed_cids.append(placed_comp_detail.cid)
        
        max_placed_package = 0
        if is_placed :
            max_placed_package = db.query(func.max(Company.package)).filter(Company.cid.in_(placed_cids)).scalar()
        
        for company in companies:
            cid_details = {
                "company_details": {},
                "msg": "",
                "eligible": True,
                "is_registered": False
            }
            i+=1
                
            # Convert the company to json object
            company_details = {
                "cname": company.cname,
                "package": company.package,
                "eligible_college_ids": company.eligible_college_ids,
                "deadline": company.deadline,
                "ssc": company.ssc,
                "ug": company.ug,
                "branch": company.branch,
                "status": company.status,
                "category": company.category,
                "cid": company.cid,
                "internship_stipend": company.internship_stipend,
                "date": company.date,
                "hsc": company.hsc,
                "pg": company.pg,
                "backlogs": company.backlogs,
                "gender": company.gender
            }

            if company_details['category']=='core' and (stud_branch not in non_circuit_branches):
                print("Enterrrrr")
                cid_details["company_details"] = company_details
                cid_details["msg"] = ""
                cid_details["eligible"] = False
                cid_details["is_registered"] = False
                array_cids.append(cid_details)
                continue
            
            # 3.) Checking the blacklist record of the student
            blacklist_record = db.query(Blacklist).filter(Blacklist.urn == urn).first()
            if blacklist_record:
                if blacklist_record.credits == 0:
                    cid_details["company_details"] = company_details
                    cid_details["msg"] = "You are blacklisted"
                    cid_details["eligible"] = False
                    cid_details["is_registered"] = False
                    array_cids.append(cid_details)
                    continue

            # 4.) Checking for college id
            college_ids = company.eligible_college_ids.split(",")
            if str(student.college_id) not in college_ids:
                cid_details["company_details"] = company_details
                cid_details["msg"] = ""
                cid_details["eligible"] = False
                cid_details["is_registered"] = False
                array_cids.append(cid_details)
                print(student.college_id)
                continue
            
            # 5.) Checking for branch
            branch_list = company_details["branch"].split(",")
            if student.branch not in branch_list:
                cid_details["company_details"] = company_details
                cid_details["msg"] = ""
                cid_details["eligible"] = False
                cid_details["is_registered"] = False
                array_cids.append(cid_details)
                continue
            
            # 7.) Checking for gender
            gender = student.gender
            gender = gender.upper()
            print(gender)
            if gender=="FEMALE" or gender=="F":
                gender = "F"
            if gender=="MALE" or gender=="M":
                gender = "M"
            eligible_genders = company_details["gender"].split(",")
            if gender not in eligible_genders:
                cid_details["company_details"] = company_details
                cid_details["msg"] = ""
                cid_details["eligible"] = False
                cid_details["is_registered"] = False
                array_cids.append(cid_details)
                continue

            # 8.) Checking for eligible package

            if is_placed and company_details["category"]=='normal':
                #placed_company = db.query(Company).filter(Company.cid.in_(placed_cids)).first()
                #if placed_company:
                    # If student is already placed in the same company
                if company.cid in placed_cids:
                    cid_details["company_details"] = company_details
                    cid_details["msg"] = "You are already Placed in this company"
                    cid_details["eligible"] = False
                    cid_details["is_registered"] = True
                    array_cids.append(cid_details)
                    continue

                placed_package = max_placed_package
                eligible_package = placed_package+(placed_package*75)
                if company.package < eligible_package:
                    cid_details["company_details"] = company_details
                    cid_details["msg"] = "Only One Offer Allowed, Still seeking management approval 1.75 criteria"
                    cid_details["eligible"] = False
                    cid_details["is_registered"] = False
                    array_cids.append(cid_details)
                    continue

            if is_placed and company_details["category"]=='core':
                placed_company = db.query(Company).filter(Company.cid == is_placed.cid).first()

                # If student is already placed in the same company
                if placed_company.cid == company.cid:
                    cid_details["company_details"] = company_details
                    cid_details["msg"] = ""
                    cid_details["eligible"] = False
                    cid_details["is_registered"] = True
                    array_cids.append(cid_details)
                    continue


            # 9.) Checking for cutoffs
            if (student.ssc < company_details["ssc"] or student.ug < company_details["ug"] or student.hsc < company_details["hsc"] or (student.pg < company_details["pg"]) and student.pg!=-1):
                cid_details["company_details"] = company_details
                cid_details["msg"] = ""
                cid_details["eligible"] = False
                cid_details["is_registered"] = False
                array_cids.append(cid_details)
                continue

            # 10.) Checking for backlogs
            if student.backlogs>0 and company_details["backlogs"]==0:
                cid_details["company_details"] = company_details
                cid_details["msg"] = ""
                cid_details["eligible"] = False
                cid_details["is_registered"] = False
                array_cids.append(cid_details)
                continue
            
            # 11.) If all the cases are passed then send eligible as true
            else:
                # Check for registration
                registration = db.query(Registrations).filter(Registrations.urn == urn).filter(Registrations.cid == company.cid).first()
                cid_details["company_details"] = company_details
                cid_details["msg"] = ""
                cid_details["eligible"] = True
                is_registered = False
                if registration:
                    is_registered = True
                cid_details["is_registered"] = is_registered
                array_cids.append(cid_details)
                continue
        return array_cids  
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@itemrouter.post("/home/eligible/noida/register/{urn}", include_in_schema=True)
async def eligible_to_register(urn: str, db: Session = Depends(get_db), b: bool = Depends(get_current_student)): #b: bool = Depends(get_current_student) # type: ignore
    urn= urn.upper()
    urn=urn.strip()
    record= db.query(Placed).filter(Placed.urn== urn).all()
    blacklist_record = db.query(Blacklist).filter(Blacklist.urn == urn).first()
    # return blacklist_record
    credits = blacklist_record.credits
    categories= []
    placed_cids = []
    for item in record:
        categories.append(item.category_placed)
        placed_cids.append(item.cid)
    categoryCount=len(categories)
    # return cids
    array_eligible_cid = {"company_details": [],
                          "eligible": [], "is_registered": [], "error":[]}
    student_variable = db.query(User).filter(User.urn==urn).first()
    s_verified = student_variable.verified
    s_ssc = student_variable.ssc
    s_hsc = student_variable.hsc
    s_ug = student_variable.ug
    s_pg = student_variable.pg
    s_backlogs = student_variable.current_backlogs
    s_branch = student_variable.branch
    s_gender = student_variable.gender
    s_college_id = student_variable.college_id
    if s_gender == "male" or s_gender == "Male" or s_gender == "MALE" or s_gender=="m":
        s_gender = "M"
    elif s_gender == "female" or s_gender == "Female" or s_gender == "FEMALE" or s_gender=="f":
        s_gender = "F"
    company_variables= db.query(Company).filter(Company.eligible_college_ids.contains(str(s_college_id))).all()
    # return data
    blacklist_message=""
    if credits == 0 and s_college_id == 3:
        blacklist_message ="You have been Blacklisted" 
    cids=[]
    for item in company_variables:
        cids.append(item.cid)
    ###########################
    #logic for ppo rejected student
    ppo_rejected =False
    offers = db.query(Offer).filter(Offer.urn ==urn).all()
    

    for offer in offers:
        if (offer.category == "tier2" or offer.category =="dream") and len(record)==0:
            ppo_rejected =True   
           
        elif(offer.category =="internship") and len(record) == 0:
            
            student_ctc = db.query(Company).filter(Company.cid == offer.cid).first().package
            if student_ctc > 6:
                ppo_rejected =True
      
        
    
    ############################
    
    for i in range(len(cids)):
        error=''
        c_cid = company_variables[i].cid
        c_hsc = company_variables[i].hsc
        c_ssc = company_variables[i].ssc
        c_ug = company_variables[i].ug
        c_pg = company_variables[i].pg
        c_backlogs = company_variables[i].backlogs
        c_branch = company_variables[i].branch
        c_category = company_variables[i].category
        c_package = company_variables[i].package
        c_deadline = company_variables[i].deadline
        c_status = company_variables[i].status
        c_gender = company_variables[i].gender
        c_eligible_college_ids = company_variables[i].eligible_college_ids
        # c_ctc = company_variables[i].package

        # nonCircuitBranches = ['MECH', 'EE', 'EEE', 'CE']
        nonCircuitBranches=['MECH','CV','CTM','BT','PST','IP','EV','ECE','EEE','EI', 'CE']
        IST = pytz.timezone('Asia/Kolkata')
        datetime_ist = datetime.now(IST)
        cur_date_time = datetime_ist.strftime('%Y-%m-%d %H:%M:%S')
        cur_date_time = datetime.strptime(cur_date_time, '%Y-%m-%d %H:%M:%S')
        eligible = True
        # return c_eligible_college_ids
        list_college_ids = []
        if c_eligible_college_ids:
            list_college_ids = c_eligible_college_ids.split(",")

        if str(s_college_id) not in list_college_ids:
            eligible = False

        if str(s_college_id) == "3":
            if c_status == 2:
                eligible = False
            elif c_category == "summer_internship":
                    eligible = False
            else:
                if (((c_deadline < cur_date_time) == True) and (c_status == 1)):
                    eligible = False
                    company_variables[i].status = 2
                    db.commit()

                elif c_status != 1 or (s_gender not in c_gender) or (s_branch not in c_branch) or (c_deadline < cur_date_time) or s_hsc < c_hsc or s_ssc < c_ssc or ((s_ug < c_ug and s_pg == -1) or (s_pg != -1 and s_pg < c_pg)) or (c_backlogs == 0 and s_backlogs != '0') or s_verified != 1 or (c_category in categories):
                    eligible = False

                elif categoryCount == 2:
                    if (("internship" or "core") in categories) or (not (c_category in ["internship", "core"])):
                        eligible = False
                elif categoryCount == 2:
                    # if internship is in s_category then he is eligible for a third offer
                    if (("internship") in categories or ("core") in categories):
                        if (c_category == "internship" or c_category == "core"):
                            eligible = False
                        elif ("tier1" in categories):
                            if (c_category == "tier1"):
                                eligible = False
                        elif ("tier2" in categories):
                            if ((c_category == "tier1") or (c_category == "tier2")):
                                eligible = False
                        elif ("tier3" in categories):
                            if ((c_category == "tier1") or (c_category == "tier2") or (c_category == "tier3")):
                                eligible = False
                        elif ("dream" in categories):
                            if ((c_category == "tier1") or (c_category == "tier2") or (c_category == "tier3") or (c_category == "dream")):
                                eligible = False
                    else:
                        if (c_category != "internship" or c_category != "core"):
                            eligible = False
                elif categoryCount == 3:
                    eligible = False
                elif categoryCount == 1:
                    if ("tier1" in categories):
                        if (c_category == "tier1"):
                            eligible = False
                    elif ("tier2" in categories):
                        if ((c_category == "tier1") or (c_category == "tier2")):
                            eligible = False
                    elif ("tier3" in categories):
                        if ((c_category == "tier1") or (c_category == "tier2") or (c_category == "tier3")):
                            eligible = False
                    elif ("dream" in categories):
                        if ((c_category == "tier1") or (c_category == "tier2") or (c_category == "tier3") or (c_category == "dream")):
                            eligible = False
                    elif ("core" in categories):
                        if ((c_category == "core") or (c_category == "internship")):
                            eligible = False
                    elif ("internship" in categories):
                        if ((c_category == "internship") or (c_category == "core")):
                            eligible = False
                
            
            exist = db.query(models.Registrations).filter(models.Registrations.cid==c_cid).filter(models.Registrations.college_id==3).all()
            
            is_registered = False
            for item in exist:
                if urn == item.urn:
                    eligible = False
                    is_registered = True
            # company_variables = crud.item_of_company(db)
            array_eligible_cid["company_details"].append(company_variables[i])
            array_eligible_cid["eligible"].append(eligible)
            array_eligible_cid["is_registered"].append(is_registered)
            
        elif str(s_college_id) == "2":
            # company_count = db.query(Blacklist).filter(Blacklist.urn == urn).first().company_count
            # if company_count != 5:
                # eligible =False
            if c_status == 2:
                eligible = False
            elif c_status != 1 or (s_gender not in c_gender) or (s_branch not in c_branch) or (c_deadline < cur_date_time) or s_hsc < c_hsc or s_ssc < c_ssc or ((s_ug < c_ug and s_pg == -1) or (s_pg != -1 and s_pg < c_pg)) or (c_backlogs == 0 and s_backlogs != '0') or (c_category in categories):
                eligible = False
            
            elif (((c_deadline < cur_date_time) == True) and (c_status == 1)):
                    eligible = False
                    company_variables[i].status = 2
                    db.commit()
                    
            elif categoryCount >= 1:
                    for cid in cids:
                        student_ctc = db.query(Company).filter(Company.cid == cid).first().package
                        minimum_ctc = 2*student_ctc
                        
                        if ("internship" in categories) and minimum_ctc > c_package and c_category =="internship":
                             eligible =False
                             
                        elif("core" in categories) and minimum_ctc > c_package and c_category =="core":
                             eligible =False
                             
                        elif("tier1"in categories):  
                            if (not (c_category in ["core", "tier2", "internship", "dream", "special"])) and minimum_ctc > c_package:
                                eligible = False
                            
                        elif ("tier2" in categories):
                            if (not (c_category in ["dream", "special"])) and minimum_ctc > c_package:
                                eligible = False

            
            exist = db.query(models.Registrations).filter(models.Registrations.cid==c_cid).filter(models.Registrations.college_id==2).all()
            
            is_registered = False
            for item in exist:
                if urn == item.urn:
                    eligible = False
                    is_registered = True
            # company_variables = crud.item_of_company(db)
            array_eligible_cid["company_details"].append(company_variables[i])
            array_eligible_cid["eligible"].append(eligible)
            array_eligible_cid["is_registered"].append(is_registered)
            # array_eligible_cid["error"].append(error)
            
        # JSS MYSORE
        else:
            if credits == 0:
                eligible = False
            elif c_status == 2:
                eligible = False
            elif categoryCount == 2 and c_package < 25:
                eligible = False
            elif "core" in categories and c_package < 25:
                eligible =False
            else:
                if c_category == "other" and (c_deadline > cur_date_time):
                    eligible = True
                elif (((c_deadline < cur_date_time) == True) and (c_status == 1)):
                    eligible = False
                    company_variables[i].status = 2
                    db.commit()
                elif c_category == "summer_internship":
                    eligible = False
                elif c_status != 1 or (s_gender not in c_gender) or (s_branch not in c_branch) or (c_deadline < cur_date_time) or s_hsc < c_hsc or s_ssc < c_ssc or ((s_ug < c_ug and s_pg == -1) or (s_pg != -1 and s_pg < c_pg)) or (c_backlogs == 0 and s_backlogs != '0') or (c_category in categories):
                    eligible = False
                elif ("dream" in categories):
                    eligible = False
                elif categoryCount >= 2 and (not (c_category in ["dream", "special"])):
                    eligible = False
                elif ppo_rejected and (c_package > 6 and c_package < 25):
                    eligible =False
                elif categoryCount == 1:
                    for cid in placed_cids:
                        
                        student_ctc = db.query(Company).filter(Company.cid == cid).first().package
                        minimum_ctc = student_ctc + 0.75*student_ctc
                        if ("internship" in categories):
                       
                                #tier2 condition
                                
                            if student_ctc > 6 and c_package > 6 and c_category !="dream":
                                eligible=False
                                
                                # tier1 condition
                            elif c_package < minimum_ctc and student_ctc <= 6:
                                eligible=False
                                
                                
                                      
                        elif("tier1"in categories):
                            if (s_branch in nonCircuitBranches):
                                if c_category =="tier1":
                                    eligible = False
                                elif (c_package < minimum_ctc):
                                    eligible = False
                            else:
                                if c_package < minimum_ctc and student_ctc <= 6:
                                    eligible=False
                                elif c_category =="tier1":
                                    eligible = False
                                    
                                
                                
                        elif ("tier2" in categories):
                            if (not (c_category in ["dream", "special"])):
                                eligible = False
                            
                        
                        

            exist = db.query(models.Registrations).filter(models.Registrations.cid==c_cid).filter(models.Registrations.college_id==1).all()
            
            is_registered = False
            for item in exist:
                if urn == item.urn:
                    eligible = False
                    is_registered = True
            # company_variables = crud.item_of_company(db)
            array_eligible_cid["company_details"].append(company_variables[i])
            array_eligible_cid["eligible"].append(eligible)
            array_eligible_cid["is_registered"].append(is_registered)
            array_eligible_cid["blacklist_message"] = blacklist_message
            # array_eligible_cid["error"].append(error)

    return array_eligible_cid


# CRLF = "\r\n"
# import logging
@itemrouter.post("/home/eligible/cid/register_to_company/{urn}/{cid}/{college_id}", include_in_schema=True)
def register_into_company(urn: str, cid: int, college_id: int, db: Session = Depends(get_db), b: bool = Depends(get_current_student)): # type: ignore
    try:
        urn = urn.upper()
        urn= urn.strip()
        exist = db.query(models.Registrations).filter(
            models.Registrations.urn == urn).filter(models.Registrations.cid == cid).first()
        # return exist
        if exist is not None:
            return False
        
        # print("true")
        # user = db.query(User).filter(User.urn == urn).first()
        # return user
        # email = user.email
        # name = user.full_name
        # return email
        # cname = db.query(Company.cname).filter(Company.cid == cid).first().cname
        # return cname
        # message = MessageSchema(
        #     subject="JSS Institution Placement Portal Registration",
        #     recipients=[email],  # List of recipients, as many as you can pass
        #     body="Dear {name},\r\n".format(name= name) +CRLF+
        #         "We are pleased to inform you that your registration for {cname} has been successful ✌️.\r\n".format(cname=cname) +CRLF+CRLF+
        #         "If you have any questions or concerns, please don't hesitate to contact us.\r\n"+CRLF+
        #         "Please visit the JSS Placement Website to update the resume link with updated resume if necessary.\r\n"+CRLF+
        #         "Thank you for choosing {cname}!\r\n".format(cname=cname)+CRLF+
                
        #         "Best regards,\r\n\n" +CRLF+
        #         "JSS Institution Placement Team ")

        reg = models.Registrations(urn=urn, cid=cid, college_id=college_id)
        
        db.add(reg)
        db.commit()
        # sql_delete="DROP INDEX registration_index;"
        # sql_create="CREATE index registration_index on registrations(college_id, urn,cid);"
        # with engine.connect() as con:
        #         try:
        #             rs = con.execute(sql_create)
        #         except: 
        #             con.execute(sql_delete)
        #             con.execute(sql_create)
                    
        # fm = FastMail(conf)
        # await fm.send_message(message)

        db.refresh(reg)
        print(reg)

        q = f"""
            INSERT INTO progress(rid)
            VALUES (:rid)
            """
        db.execute(q,{"rid":reg.rid})
        db.commit()
        return True
    except:
        
        db.rollback()
        


@itemrouter.get("/home/eligible/details/{cid}", include_in_schema=True)
def get_company_details_students(cid: int, session=Depends(get_db), b: bool = Depends(get_current_student)):
    return crud.get_item_by_company(session, cid=cid)


@itemrouter.get("/home/status_category{urn}", include_in_schema=True)
def get_student_status(urn: str, session=Depends(get_db), b: bool = Depends(get_current_student)):
    urn = urn.upper()
    return crud.get_placedcategory_students(session, urn=urn)


@itemrouter.get("/home/status_stipend{urn}", include_in_schema=True)
def get_stipend_status(urn: str, session=Depends(get_db), b: bool = Depends(get_current_student)):
    urn = urn.upper()
    return crud.get_stipend_students(session, urn=urn)


@itemrouter.get("/home/status_cname{urn}", include_in_schema=True)
def get_student_cname_status(urn: str, session=Depends(get_db), b: bool = Depends(get_current_student)):
    urn = urn.upper()
    return crud.get_cname_students(session, urn=urn)

@itemrouter.get("/home/status{urn}", include_in_schema=True)
def get_student_status(urn: str, session=Depends(get_db), b: bool = Depends(get_current_student)):
    urn = urn.upper()
    return {'cname':crud.get_cname_students(session, urn=urn), 
            'category':crud.get_placedcategory_students(session, urn=urn),
            'branch':crud.get_branch_students(session, urn=urn),
    }



@itemrouter.get("/home/status_package{urn}", include_in_schema=True)
def get_student_package_status(urn: str, session=Depends(get_db), b: bool = Depends(get_current_student)):
    urn = urn.upper()
    return crud.get_package_students(session, urn=urn)


@itemrouter.get("/home/status_tier{urn}", include_in_schema=True)
def get_student_tier_status(urn: str, session=Depends(get_db), b: bool = Depends(get_current_student)):
    urn = urn.upper()
    return crud.placed_category(session, urn=urn)


@itemrouter.get("/home/status/placed/{urn}")
def get_status_after_placed(urn: str, db: Session = Depends(get_db), b: bool = Depends(get_current_student)): # type: ignore # type: ignore
    urn = urn.upper()
   # return db.query(Company.cname).filter(Company.cid == 1).first().cname
    placed_detail = db.query(Placed).filter(Placed.urn == urn).all()

    # Placed_category_detail= db.query(Placed_category).filter(Placed_category.urn==urn).all()
    placed_record = []
    for i in range(len(placed_detail)):
        category_placed = placed_detail[i].category_placed
        cid = placed_detail[i].cid
        company = db.query(Company).filter(Company.cid == cid).first()
        company_name = company.cname
        package = company.package
        stipend = company.internship_stipend
        category = company.category
        placed_record.append({"category": category, "category_placed": category_placed,
                             "cname": company_name, "package": package, "stipend": stipend})

    return placed_record


@itemrouter.get("/home/myprofile{urn}", include_in_schema=True)
def my_profile(urn: str, db: Session = Depends(get_db), b: bool = Depends(get_current_student)): # type: ignore
    # return b
    urn = urn.upper()
    item = db.query(User).filter(User.urn == urn).first()
   
    if(item.resume_link==None):
        item.resume_link=""
        
    if item is None:
        raise HTTPException(status_code=404, detail="user not found")
    return item


client = boto3.client(
    's3',
    aws_access_key_id=os.getenv("aws_access_key_id"),
    aws_secret_access_key=os.getenv("aws_secret_access_key"),
    region_name='ap-south-1'
)

# Creating the high level object oriented interface
resource = boto3.resource(
    's3',
    aws_access_key_id=os.getenv("aws_access_key_id"),
    aws_secret_access_key=os.getenv("aws_secret_access_key"),
    region_name='ap-south-1'
)


@itemrouter.post("/home/file/upload/{urn}", include_in_schema=True)
async def upload_resume(urn: str, file: UploadFile = File(...), b: bool = Depends(get_current_student)):
    if file.content_type != "application/pdf":
        raise HTTPException(400, detail="Invalid document type")
    contents = await file.read()
    urn = urn.upper()
    urn = urn + ".pdf"
    file.filename = urn
    import io
    temp_file = io.BytesIO()
    temp_file.write(contents)
    temp_file.seek(0)
    client.upload_fileobj(temp_file, 'resumesnoida', file.filename)
    temp_file.close()
    return {"message": "Resume uploaded successfully"}

@itemrouter.get("/home/feedback/{urn}/{college_id}", include_in_schema=True)
def check_feedback(urn: str, db: Session = Depends(get_db), b: bool = Depends(get_current_student)): # type: ignore
    exist = db.query(models.Feedback).filter_by(urn=urn).all()
    if exist != []:
        return 1
    else:
        return 0
    
    
@itemrouter.post("/home/feedback/{urn}/{college_id}", include_in_schema=True)
def write_feedback(feedback: schemas.Feedback, urn: str, college_id:int, cname: str, db: Session = Depends(get_db), b: bool = Depends(get_current_student)): # type: ignore # type: ignore
    try:
        urn = urn.upper()
        exist = db.query(models.Feedback).filter_by(urn=urn).all()
        if exist != []:
            return {"message": "Feedback already exist"}
        cn = crud.get_placed_students_cname(db, urn=urn)
        sn = db.query(models.User.full_name).filter_by(urn=urn).first()
        # return cn[0][0]
        cname = cname.upper()
        j = 0
        f = 1

        if f == 1:
            feedback_obj = models.Feedback(college_id=college_id,
                                            urn=urn,
                                            cname=cname,
                                            sname=sn[0],
                                            branch=feedback.branch,
                                            role=feedback.role,
                                            ctc=feedback.ctc,
                                            base=feedback.base,
                                            technical_round=feedback.technical_round,
                                            hr_round=feedback.hr_round,
                                            tips=feedback.tips,
                                            topics_covered=feedback.topics_covered,
                                            codinground_difficulty=feedback.codinground_difficulty,
                                            interview_difficulty=feedback.interview_difficulty,
                                            overall_experience=feedback.overall_experience,
                                            passing_year=feedback.passing_year,
                                            # need to check ful, time/summer intern issue from frontend
                                            full_time=True,
                                        #    summer_internship=False,
                                            stipend=feedback.stipend,
                                            location=feedback.location,
                                            mode=feedback.mode)
            db.add(feedback_obj)
            db.commit()
            return {"message": "Successfully submitted feedback"}
        return {"message": "Incorrect Details"}
    except:
        db.rollback()
        raise HTTPException(
            status_code=400, detail="Error in submitting feedback")
    finally:
        db.close()

@itemrouter.get("/home/registered_email/{cid}", include_in_schema=True)
def get_registered_email(cid: int, db: Session = Depends(get_db), b: bool = Depends(get_current_student)): # type: ignore
    urn = db.query(models.Registrations.urn).filter_by(cid=cid).all()
    a = []
    for i in urn:
        a.append(i[0])
    b = []
    for i in a:
        email = db.query(models.User.email).filter_by(urn=i).all()
        b.append(email[0][0])
    return b


@itemrouter.get("/home/feedback/eligible{urn}", include_in_schema=True)
def eligible_feedback(urn: str, db: Session = Depends(get_db), b: bool = Depends(get_current_student)): # type: ignore # type: ignore
    urn = urn.upper()
    item = db.query(models.Placed_category).filter_by(urn=urn).all()
    items = item.__len__()
    if items == 0:
        return False
    else:
        return True

@itemrouter.get("/get/user/")
def all_user_index(db: Session = Depends(get_db)): # type: ignore
    return db.query(User.resume_link).filter(User.urn=="01JST20IS028").first()


@itemrouter.put("/home/update_resume_link/{urn}",include_in_schema=True)
def update_resume_link(urn:str,user:schemas.UpdateResumeLink ,db: Session = Depends(get_db), b: bool = Depends(get_current_student)): # type: ignore
    urn=urn.upper()
    student = db.query(User).filter(User.urn==urn).first()
    student.resume_link= user.resume_link
    db.commit()
    return {"message":"Your Resume Link Updated Successfully"}
    # pass
# @itemrouter.post('/home/file/download_resume/{urn}')
# def download_resume(urn_list:str):
#     urnlist=urn_list.split(",")
#     a=[]
#     for i in urnlist:
#         j=i.upper()+".pdf"
#         a.append(j)
#     b=[]
#     #bucket = client.list_objects(Bucket='test-resumes14')
#     f=0
#     for i in a:
#         str=r"C:/Users/HP/Downloads/Placement-website-resume/resume"+"/"+i
#         client.download_file('test-resumes14',i,str)
#         f=f+1

#     return {"message":"Successfully downloaded %d resumes"%f}


# @itemrouter.get("/home/list_buckets")
# async def list_buckets():
#     clientResponse = client.list_buckets()
#     a=[]
# # Print the bucket names one by one
#     print('Printing bucket names...')
#     for bucket in clientResponse['Buckets']:
#         a=bucket['Name']
#     return a
