from pathlib import Path
from email import message
from unicodedata import category
# from pyrsistent import optional
from . import crud, models, schemas
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from typing import List
from pydantic import BaseModel
from sqlalchemy import insert
from fastapi.exceptions import HTTPException
from fastapi import APIRouter, status, Depends, File, UploadFile, Form, Body, Response, FastAPI, BackgroundTasks, APIRouter, status
from .database import Session, engine
from .schemas import LoginModel, AddCompanyModel, CompanyStatusDetails, CompanyDetails, StudentDetails, StudentModel, EmailSchema, BranchDetails, Placed, PlacedCategory
from .models import Blacklist, Company, Placed, Placed_category, Registrations, User , Offer
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from typing import Optional
from datetime import datetime, timedelta
import os
import pytz
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi_pagination import Page, paginate, Params
import secrets
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status , BackgroundTasks
load_dotenv()

security = HTTPBasic()
import logging
logger = logging.getLogger("my_logger")
session = Session(bind=engine)

oauth3_scheme = OAuth2PasswordBearer(
    tokenUrl="admin/login", scheme_name='admin')
# super user
admin_username = os.getenv('admin_username')
admin_password = os.getenv('admin_password')

# admin_username_mysore=os.getenv('admin_mysore')
# admin_password_mysore=os.getenv('admin_mysore_pass')

admin_username_bangalore = os.getenv('admin_bangalore')
admin_password_bangalore = os.getenv('admin_bangalore_pass')

admin_username_noida = os.getenv('admin_noida')
admin_password_noida = os.getenv('admin_noida_pass')
ALGORITHM = "HS256"
JWT_SECRET = os.getenv("JWT_SECRET")
ACCESS_TOKEN_EXPIRE_MINUTES = 1000


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


class Token(BaseModel):
    access_token: str
    token_type: str


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


def get_current_admin(token: str = Depends(oauth3_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        role = payload.get("role")
        if role != 'admin':
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    return True


admin_router = APIRouter(
    prefix='/admin',
    tags=['admin'],

)


@admin_router.post("/login", include_in_schema=True)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    urn = str(form_data.username)
    urn = urn.upper()
    password = str(form_data.password)
    college_id = 0
    if ((urn == admin_username) and (password == admin_password)):
        college_id = 1
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": urn, "role": 'admin'}, expires_delta=access_token_expires
        )
    elif ((urn == "TPO@JSSATEB") and (password == "jssbangalore@admin")):
        college_id = 2
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": urn, "role":'admin'}, expires_delta=access_token_expires
        )
    elif ((urn == admin_username_noida) and (password == admin_password_noida)):
        college_id = 3
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": urn, "role":'admin'}, expires_delta=access_token_expires
        )
    else:
        logger.info("401 Unauthorized")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"access_token": access_token, "token_type": "bearer", "college_id": college_id}


@admin_router.post("/add_alumni_details")
def post_alumni_details(alumni: schemas.Alumni, db: Session = Depends(get_db), current_user: bool = Depends(get_current_admin)):
    db_alumni = models.alumni(a_name=alumni.a_name, a_email=alumni.a_email, branch=alumni.branch,
                              passout=alumni.passout, usn=alumni.usn, a_cname=alumni.a_cname)
    db.add(db_alumni)
    db.commit()
    db.refresh(db_alumni)
    return db_alumni


@admin_router.put("/update_alumni_details/{a_email}")
def update_alumni_details(a_email: str, alumnid: schemas.Alumni, db: Session = Depends(get_db), current_user: bool = Depends(get_current_admin)):
    db_alumni = db.query(models.alumni).filter(
        models.alumni.a_email == a_email).first()
    db_alumni.a_name = alumnid.a_name
    db_alumni.a_email = alumnid.a_email
    db_alumni.branch = alumnid.branch
    db_alumni.passout = alumnid.passout
    db_alumni.usn = alumnid.usn
    db_alumni.a_cname = alumnid.a_cname
    db.commit()
    db.refresh(db_alumni)
    return db_alumni


@admin_router.get("/get_all_alumni_details")
def get_all_alumni_details(db: Session = Depends(get_db)):
    return crud.get_all_alumni_details(db=db)


@admin_router.post("/admin/edit_student/{urn}/{college_id}", status_code=status.HTTP_201_CREATED)
def updatestudent(user: StudentModel, college_id: int, urn: str, session=Depends(get_db), a: bool = Depends(get_current_admin)):
    urn = urn.upper()
    dc = session.query(User).filter(User.urn == urn).filter(
        User.college_id == college_id).first()
    if dc is None:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="Student doesn't exists"
                             )
    dc.urn = user.urn,
    dc.full_name = user.full_name,
    dc.email = user.email,
    dc.branch = user.branch,
    dc.first_name = user.first_name,
    dc.last_name = user.last_name,
    dc.middle_name = user.middle_name,
    dc.ssc = user.ssc
    dc.hsc = user.hsc
    dc.ug = user.ug,
    dc.pg = user.pg,
    dc.ug_percentage = user.ug_percentage
    dc.backlogs = user.backlogs,
    dc.sem1 = user.sem1
    dc.sem2 = user.sem2
    dc.sem3 = user.sem3
    dc.sem4 = user.sem4
    dc.sem5 = user.sem5
    dc.sem6 = user.sem6
    dc.sem7 = user.sem7
    dc.sem8 = user.sem8
    dc.current_backlogs = user.current_backlogs
    dc.history_backlogs = user.history_backlogs
    dc.no_of_x_grades = user.no_of_x_grades
    dc.other_grades = user.other_grades
    dc.ug_start_year = user.ug_start_year
    dc.ug_end_year = user.ug_end_year
    dc.ssc_board = user.ssc_board
    dc.hsc_board = user.hsc_board
    dc.hsc_start_year = user.hsc_start_year
    dc.hsc_end_year = user.hsc_end_year
    dc.ssc_start_year = user.ssc_start_year
    dc.ssc_end_year = user.ssc_end_year
    dc.entry_to_college = user.entry_to_college
    dc.rank = user.rank
    dc.gap_in_studies = user.gap_in_studies
    dc.dob = user.dob
    dc.gender = user.gender
    dc.category = user.category
    dc.native = user.native
    dc.parents_name = user.parents_name
    dc.present_addr = user.present_addr
    dc.permanent_addr = user.permanent_addr
    dc.phone = user.phone
    dc.secondary_phone = user.secondary_phone
    dc.verified = user.verified
    dc.college_id = user.college_id
    dc.resume_link= user.resume_link
    session.commit()
    return JSONResponse(status_code = 200, content = {"message":"Student Details Updated"})

conf1 = ConnectionConfig(
    MAIL_USERNAME = "placementsjce2022@gmail.com",
    MAIL_PASSWORD = "gurdstluylqaglrk",
    MAIL_FROM = "placementsjce2022@gmail.com",
    MAIL_PORT = 587,
    MAIL_SERVER = "smtp.gmail.com",
    MAIL_FROM_NAME="Placement-Information",
    MAIL_TLS = True,
    MAIL_SSL = False,
    USE_CREDENTIALS = True,
    VALIDATE_CERTS = True
)



@admin_router.post("/home/send_feedback_reminder/{cid}/{college_id}", include_in_schema=True)
async def remind_feedback(college_id:int,remind: List[schemas.FeedbackRemindModel], db: Session = Depends(get_db), a: bool = Depends(get_current_admin)):
    company = db.query(Company).filter(Company.cid==remind[0].cid).filter(Company.eligible_college_ids.contains(str(college_id))).first()
    company_name =company.cname
    urns =  db.query(models.Placed.urn).filter(Placed.cid==remind[0].cid).filter(Placed.college_id==college_id).all()
    urn_list=[]
    for item in urns:
        urn_list.append(item.urn)
        
    attendees=[]
    for urn in urn_list:
        student= db.query(User).filter(User.urn ==urn ).filter(User.college_id==college_id).first()
        attendees.append(student.email)
    message = MessageSchema(
        subject="Congratulations on getting selected in "+company_name+"!!",
        recipients=attendees,
        body="Congratulations to all of you who got selected in "+company_name+".\r\n"+"All of you are hereby requested to fill the feedback form on the placement portal by today without any failure.\nContact placement office or the website team for any queries.\n\n" +
        # "Regards,\nDr. M Pradeep\nTraining & Placement Officer -SJCE Mysore."
        "Regards,\nJSS INSTITUTION \nTraining & Placement Team\n"
    )
    fm = FastMail(conf1)
    await fm.send_message(message)

    return JSONResponse(status_code=200, content={"message": "Reminder details has been sent"})


@admin_router.post("/update_send_file", status_code=status.HTTP_201_CREATED)
async def update_send_file(
    file: Optional[UploadFile] = File(None),
    file1: Optional[UploadFile] = File(None),
    file2: Optional[UploadFile] = File(None),
    email: Optional[str] = Body(None),
    email2: Optional[str] = Body(None),
    subject: Optional[str] = Body(None),
    body: Optional[str] = Body(None),
    a: bool = Depends(get_current_admin)
) -> JSONResponse:

    list1 = []
    emails = []

    if email2 == None:
        email2 = "prab7hat@gmail.com"

    if email is not None:
        emails.append(email)
    if email2 is not None:
        emails.append(email2)

    if (file == None and file1 == None and file2 == None):
        message = MessageSchema(
            recipients=emails,
            body=body,
            subject=subject
        )
    else:
        if file is not None:
            list1.append(file)
        if file1 is not None:
            list1.append(file1)
        if file2 is not None:
            list1.append(file2)

        message = MessageSchema(
            recipients=emails,
            attachments=list1,
            body=body,
            subject=subject
        )

    fm = FastMail(conf1)
    await fm.send_message(message)

    return JSONResponse(status_code=200, content={"message": "Updated Company details has been sent "})


@admin_router.delete("/delete_company/{cid}/{college_id}", status_code=status.HTTP_201_CREATED)
def delete_company(cid: int, college_id: int, db: Session = Depends(get_db), a: bool = Depends(get_current_admin)):
    dc = db.query(Company).filter(Company.cid == cid).filter(Company.eligible_college_ids.contains(str(college_id))).first()
    if dc is None:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="Company doesn't exists or you are not allowed to delete the Company"
                             )
    list_of_college_ids= dc.eligible_college_ids.split(',')
    list_of_college_ids.remove(str(college_id))
    updated_eligible_college_ids=''
    if(len(list_of_college_ids)==0):
        db.delete(dc)
        db.commit()
    else:
        for i in range (len(list_of_college_ids)):
            if(i!=len(list_of_college_ids)-1):
                updated_eligible_college_ids+= list_of_college_ids[i]+','
            else:
                updated_eligible_college_ids+=list_of_college_ids[i]
            dc.eligible_college_ids=updated_eligible_college_ids
            db.commit()
    return {"message": "Company Deleted"}


@admin_router.post("/send_file", status_code=status.HTTP_201_CREATED)
async def send_file(
    file: Optional[UploadFile] = File(None),
    file1: Optional[UploadFile] = File(None),
    file2: Optional[UploadFile] = File(None),
    email: Optional[str] = Body(None),
    subject: Optional[str] = Body(None),
    body: Optional[str] = Body(None),
    email2: Optional[str] = Body(None), a: bool = Depends(get_current_admin)
) -> JSONResponse:

    list1 = []
    emails = []
    if email2 == None:
        email2 = "aadeevishal@gmail.com"

    if email is not None:
        emails.append(email)
    if email2 is not None:
        emails.append(email2)

    if (file == None and file1 == None and file2 == None):
        message = MessageSchema(
            recipients=emails,
            body=body,
            subject=subject
        )
    else:
        if file is not None:
            list1.append(file)
        if file1 is not None:
            list1.append(file1)
        if file2 is not None:
            list1.append(file2)

        message = MessageSchema(
            recipients=emails,
            attachments=list1,
            subject=subject,
            body=body
        )

    fm = FastMail(conf1)
    await fm.send_message(message)

    return JSONResponse(status_code=200, content={"message": "Company details has been sent"})

conf_noida = ConnectionConfig(
    MAIL_USERNAME = "placementsjssate@gmail.com",
    MAIL_PASSWORD = "ugpfesadhglobidd",
    MAIL_FROM = "placementsjssate@gmail.com",
    MAIL_PORT = 587,
    MAIL_SERVER = "smtp.gmail.com",
    MAIL_FROM_NAME="Placement-Information",
    MAIL_TLS = True,
    MAIL_SSL = False,
    USE_CREDENTIALS = True,
    VALIDATE_CERTS = True
)
@admin_router.post("/company/add_company", status_code=status.HTTP_201_CREATED)
async def add_company(
    cname: str = Form(...),
    category: str = Form(...),
    package: float = Form(...),
    internship_stipend: float = Form(...),
    deadline: datetime = Form(...),
    date: datetime = Form(...),
    ssc: float = Form(...),
    hsc: float = Form(...),
    ug: float = Form(...),
    pg: float = Form(...),
    branch: str = Form(...),
    backlogs: int = Form(...),
    gender: str = Form(...),
    email_mysore: Optional[str] = Form(None),
    email_noida: Optional[str] = Form(None),
    email_bangalore: Optional[str] = Form(None),
    email2: Optional[str] = Form(None),
    body: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    file1: Optional[UploadFile] = File(None),
    file2: Optional[UploadFile] = File(None),
    eligible_college_ids: str = Form(...),
        db: Session = Depends(get_db),a: bool = Depends(get_current_admin)):

    list_email = eligible_college_ids.split(",")
    new_company = Company(
        cname=cname,
        category=category,
        package=package,
        internship_stipend=internship_stipend,
        deadline=deadline,
        date=date,
        ssc=ssc,
        hsc=hsc,
        ug=ug,
        pg=pg,
        branch=branch,
        backlogs=backlogs,
        gender=gender,
        status=1,

        eligible_college_ids=eligible_college_ids
    )
                
        
        
    db.commit()
    if backlogs == 0:
        b = "NO"
    else:
        b = "YES"
    try:
        if body == None:
            body = " "
        list1 = []
        emails = []

        if email_mysore is not None and "1" in list_email:
            emails.append(email_mysore)
        if email_bangalore is not None and "2" in list_email:
            emails.append(email_bangalore)
        if email_noida is not None and "3" in list_email:
            emails.append(email_noida)
        emails.append("placement@sjce.ac.in")
        
        template = template = f"""
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Company Registration</title>
    <style>
      body {{
        font-family: sans-serif;
      }}
      h1,
      h2,
      h3,
      p,
      h4 {{
        margin: 0;
      }}
      .body {{
        max-width: 24rem;
        margin-left: auto;
        margin-right: auto;
        color: #000000;
      }}

      .header {{
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
        height: min-content;
        text-align: center;
      }}

      .header > h3 {{
        font-weight: 600;
      }}

      .container {{
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
        background-color: #f4f4f5;
      }}

      .container > h2 {{
        font-size: 1.125rem;
        line-height: 2rem;
        font-weight: 600;
        text-align: center;
      }}

      .content {{
        padding-left: 1rem;
        padding-right: 1rem;
      }}

      .content > h3 {{
        margin-top: 0.5rem;
        font-size: 1rem;
        line-height: 1.75rem;
        font-weight: 600;
      }}

      .content > div > div {{
        display: flex;
        padding-top: 0.25rem;
        justify-content: flex-end;
        align-content: center;
        flex-direction: column;
      }}

      .left {{
        text-align: right;
        white-space: nowrap;
        width: 15rem;
        font-weight: 500;
      }}

      .center {{
        padding-left: 0.5rem;
        padding-right: 0.5rem;
        font-weight: 600;
      }}

      .right {{
        width: 100%;
        font-weight: 500;
      }}

      .btnouter {{
        margin-bottom: 0.5rem;
        margin-top: 2rem;
        text-align: center;
      }}

      .btnregister {{
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
        padding-left: 3rem;
        padding-right: 3rem;
        border-radius: 9999px;
        font-size: 1.125rem;
        line-height: 1.75rem;
        font-weight: 500;
        text-transform: uppercase;
        background-color: #34d399;
        text-decoration: none;
        color: black;
      }}
      .footer {{
        padding-top: 1rem;
        padding-bottom: 1rem;
        font-size: 0.75rem;
        line-height: 1rem;
        text-align: center;
        color: #71717a;
      }}

      .footer > p {{
        width: 83.333333%;
        margin: 0 auto;
      }}

      .divider {{
        margin-top: 0.75rem;
        margin-bottom: 0.75rem;
        border-radius: 9999px;
        border-width: 1px;
        width: 75%;
      }}
    </style>
  </head>

  <body class="body">
    <header class="header">
      <h3>JSS</h3>
      <p>Training and Placement Cell</p>
    </header>
    <div class="container">
      <h2>{cname}</h2>

      <div class="content">
        <h3>Company Details</h3>
        <div>
          <div>
            <p class="left">Company Name</p>
            <p class="center">:</p>
            <p class="right">{cname}</p>
          </div>
          <div>
            <p class="left">Fulltime CTC</p>
            <p class="center">:</p>
            <p class="right">{package} approx.</p>
          </div>
          <div>
            <p class="left">Internship Stipend</p>
            <p class="center">:</p>
            <p class="right">{internship_stipend} approx.</p>
          </div>
          <div>
            <p class="left">Category</p>
            <p class="center">:</p>
            <p class="right">{category}</p>
          </div>
        </div>
        <h3>Cutoff Details</h3>
        <div>
          <div>
            <p class="left">SSC Cutoff</p>
            <p class="center">:</p>
            <p class="right">{ssc}</p>
          </div>
          <div>
            <p class="left">HSC Cutoff</p>
            <p class="center">:</p>
            <p class="right">{hsc}</p>
          </div>
          <div>
            <p class="left">UG Cutoff</p>
            <p class="center">:</p>
            <p class="right">{ug}</p>
          </div>
          <div>
            <p class="left">PG Cutoff</p>
            <p class="center">:</p>
            <p class="right">{pg}</p>
          </div>
          <div>
            <p class="left">Backlogs allowed</p>
            <p class="center">:</p>
            <p class="right">{b}</p>
          </div>
        </div>

        <h3>Registrations Details</h3>
        <div>
          <div>
            <p class="left">Date</p>
            <p class="center">:</p>
            <p class="right">{date}</p>
          </div>
          <div>
            <p class="left">Deadline</p>
            <p class="center">:</p>
            <p class="right">{deadline}</p>
          </div>
          <div>
            <p class="left">Branches allowed</p>
            <p class="center">:</p>
            <p class="right">
              {branch}
            </p>
          </div>
        </div>
      </div>
      <div class="btnouter">
        <a href="http://central.sjceplacements.org" class="btnregister">Register</a>
      </div>
    </div>
    <footer class="footer">
      <p class="w-5/6 mx-auto">
        You have received this mail because your e-mail ID is registered with
        JSSSTU Placement And Training Cell. This is a system-generated e-mail,
        please don't reply to this message.
      </p>
      <div class="divider"></div>
      <p>JSS Science And Technology University</p>
      <p>Mysuru Karnataka - 570006</p>
    </footer>
  </body>
</html>

        """

        if (file == None and file1 == None and file2 == None):
            message = MessageSchema(
                subject=str(cname)+" Registration Started",
                recipients=emails,
                html=template,
                subtype='html'
            )
        else:
            if file is not None:
                list1.append(file)
            if file1 is not None:
                list1.append(file1)
            if file2 is not None:
                list1.append(file2)

            message = MessageSchema(
                recipients=emails,
                attachments=list1,
                subject=str(cname)+" Registration Started",
                html=template,
                subtype='html'
            )
        sql_delete = "DROP INDEX company_index;"
        sql_create = "CREATE index company_index on company(cid);"
        with engine.connect() as con:
            try:
                rs = con.execute(sql_create)
            except:
                con.execute(sql_delete)
                con.execute(sql_create)

        session.add(new_company)
        session.commit()
        try:
            if email_mysore in emails:
                fm = FastMail(conf1)
                logger.info("Mysore email block")
                await fm.send_message(message)
            elif email_bangalore in emails:
                fm = FastMail(conf1)
                logger.info("Bangalore email block")
                await fm.send_message(message)
            elif email_noida in emails:
                fm = FastMail(conf_noida)
                logger.info("Noida email block")
                await fm.send_message(message)
            else:
                fm = FastMail(conf1)
                logger.info("Global email block")
                await fm.send_message(message)
        except Exception as e:
            logger.error(f"An error occurred: {str(e)}")
        
        
        return JSONResponse(status_code = 200, content = {"message":"Company has been added"})

    except:
        session.rollback()
        raise
    finally:
        session.close()
        
# START COMPANY DETAILS

@admin_router.get("/student/placement/{urn}", status_code=status.HTTP_200_OK)
def get_student_placement_details(urn: str, a: bool = Depends(get_current_admin)):
    # First check if student exists
    student = session.query(User).filter(User.urn == urn).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Student not found"
        )
    
    # Get placement details if they exist
    placement_details = session.query(User, Company, Placed).join(
        Placed, Placed.urn == User.urn
    ).join(
        Company, Company.cid == Placed.cid
    ).filter(
        User.urn == urn
    ).first()

    # Initialize response
    response = {
        "urn": student.urn,
        "full_name": student.full_name,
        "email": student.email,
        "is_placed": False,
        "placement_details": None
    }

    # If student is placed, add placement details
    if placement_details:
        student, company, placed = placement_details
        response["is_placed"] = True
        response["placement_details"] = {
            "company_name": company.cname,
            "category": placed.category_placed,
            "package": company.package,  # CTC from company table
            "feedback_submitted": placed.feedback
        }
        
        return JSONResponse(status_code=200, content=response)

# END COMPANY DETAILS


@admin_router.post("/student/add_student", response_model=StudentModel, status_code=status.HTTP_201_CREATED)
def add_student(user: StudentModel, a: bool = Depends(get_current_admin)):

    db_cname = session.query(User).filter(User.urn == user.urn).first()

    if db_cname is not None:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="Student already exists"
                             )

    new_student = User(
        urn=user.urn,
        # college_id=user.college_id,
        full_name=user.full_name,
        email=user.email,
        branch=user.branch,
        first_name=user.first_name,
        last_name=user.last_name,
        middle_name=user.middle_name,
        ssc=user.ssc,
        hsc=user.hsc,
        ug=user.ug,
        pg=user.pg,
        ug_percentage=user.ug_percentage,
        backlogs=user.backlogs,
        sem1=user.sem1,
        sem2=user.sem2,
        sem3=user.sem3,
        sem4=user.sem4,
        sem5=user.sem5,
        sem6=user.sem6,
        sem7=user.sem7,
        sem8=user.sem8,
        current_backlogs=user.current_backlogs,
        history_backlogs=user.history_backlogs,
        no_of_x_grades=user.no_of_x_grades,
        other_grades=user.other_grades,
        ug_start_year=user.ug_start_year,
        ug_end_year=user.ug_end_year,
        ssc_board=user.ssc_board,
        hsc_board=user.hsc_board,
        hsc_start_year=user.hsc_start_year,
        hsc_end_year=user.hsc_end_year,
        ssc_start_year=user.ssc_start_year,
        ssc_end_year=user.ssc_end_year,
        entry_to_college=user.entry_to_college,
        rank=user.rank,
        gap_in_studies=user.gap_in_studies,
        dob=user.dob,
        gender=user.gender,
        category=user.category,
        native=user.native,
        parents_name=user.parents_name,
        present_addr=user.present_addr,
        permanent_addr=user.permanent_addr,
        phone=user.phone,
        secondary_phone=user.secondary_phone,
        verified=user.verified,

    )

    session.add(new_student)

    session.commit()

    return message("Student added successfully")


@admin_router.get("/company/company_branch/{cid}", status_code=status.HTTP_201_CREATED)
def company_branch(cid: int, a: bool = Depends(get_current_admin)):
    dc = session.query(Company.branch).filter(Company.cid == cid).first()
    if dc is None:
        return HTTPException(status_code = status.HTTP_400_BAD_REQUEST,
            detail = "Company doesn't exists"
        )
    list_branches = [
        "CSE",
        "CSE_BS",
        "CSE_IS",
        "IT",
        "ECE",
        "ECE_Inst",
        "EEE",
        "Mech_IPE",
        "IP",
        "CV",
        "Civil_CTM",
        "PST",
        "BT",
        "ENV",
        "MCA",
        "BCA",
        "MSC_Cyber_Security",
        "MSC_Analytical_Chemistry",
        "MSC_General_Chemistry",
        "MSC_Mathematics",
        "MSC_Physics",
        "MSC_Data_Science",
        "MSC_AIML",
        "MSC_CS",
        "MTECH_Automotive_Electronics",
        "MTECH_Biotechnology",
        "MTECH_Computer_Engineering",
        "MTECH_Data_Science",
        "MTECH_Environmental_PG",
        "MTECH_Industrial_Electronics",
        "MTECH_Industrial_Structures",
        "MTECH_Infrastructure_Engineering_Management",
        "MTECH_Maintenance_Engineering",
        "MTECH_Material_Science",
        "MTECH_Networking_Internet_Engineering",
        "MTECH_Software_Engineering",
        "MTECH_Energy_Systems_Management",
        "MTECH_Biomedical_Signal_Processing",
        "MBA_Financial_Management",
        "MBA_Retail_Management",
        "MBA_Digital_Marketing",
        "MBA_Finance",
        "MBA_Marketing",
        "MBA_HR",
        "CSDS",
        "CSE_AIML",
        "EE",
        "MBA",
              ]
    cid_branches = dc[0].split(',')
    final_dict = {'branches':[],'is_true':[]}
    for i in list_branches:
        if i in cid_branches:
            final_dict["branches"].append(i)
            final_dict["is_true"].append(True)
        else:
            final_dict["branches"].append(i)
            final_dict["is_true"].append(False)
    return final_dict


@admin_router.put("/company/edit_company/{cid}", status_code=status.HTTP_201_CREATED)
async def update_company(
        cid: int,
        cname: str = Form(...),
        category: str = Form(...),
        package: float = Form(...),
        internship_stipend: float = Form(...),
        deadline: datetime = Form(...),
        date: datetime = Form(...),
        ssc: float = Form(...),
        hsc: float = Form(...),
        ug: float = Form(...),
        pg: float = Form(...),
        branch: str = Form(...),
        backlogs: int = Form(...),
        gender: str = Form(...),
        email_mysore: Optional[str] = Form(None),           #mysore google group
        email_banglore: Optional[str] = Form(None),           #banglore google group
        email_noida: Optional[str] = Form(None),           #noida google group
        body: Optional[str] = Form(None),
        file: Optional[UploadFile] = File(None),
        file1: Optional[UploadFile] = File(None),
        file2: Optional[UploadFile] = File(None),
        eligible_college_ids: str = Form(...),
        a: bool = Depends(get_current_admin)):

    dc = session.query(Company).filter(Company.cid == cid).first()
    if dc is None:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                             detail="Company doesn't exists"
                            )
        
    dc.cname = cname,
    dc.category = category,
    dc.package = package,
    dc.internship_stipend = internship_stipend,
    dc.deadline = deadline,
    dc.date = date,
    dc.ssc = ssc,
    dc.hsc = hsc,
    dc.ug = ug,
    dc.pg = pg,
    dc.branch = branch,
    dc.backlogs = backlogs,
    dc.gender = gender,
    dc.status = 1
    dc.eligible_college_ids = eligible_college_ids
    list_email = eligible_college_ids.split(",")

    if backlogs == 0:
        b = "NO"
    else:
        b = "YES"
    try:
        if body == None:
            body = " "
        list1 = []
        emails = []
        if email_noida == None or email_banglore == None or email_mysore == None:
            emails.append("placement@sjce.ac.in")
        if email_mysore is not None and "1" in list_email:
            emails.append(email_mysore)
        if email_banglore is not None and "2" in list_email:
            emails.append(email_banglore)
        if email_noida is not None and "3" in list_email:
            emails.append(email_noida)
        
        template = f"""
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Company Registration</title>
    <style>
      body {{
        font-family: sans-serif;
      }}
      h1,
      h2,
      h3,
      p,
      h4 {{
        margin: 0;
      }}
      .body {{
        max-width: 24rem;
        margin-left: auto;
        margin-right: auto;
        color: #000000;
      }}

      .header {{
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
        height: min-content;
        text-align: center;
      }}

      .header > h3 {{
        font-weight: 600;
      }}

      .container {{
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
        background-color: #f4f4f5;
      }}

      .container > h2 {{
        font-size: 1.125rem;
        line-height: 2rem;
        font-weight: 600;
        text-align: center;
      }}

      .content {{
        padding-left: 1rem;
        padding-right: 1rem;
      }}

      .content > h3 {{
        margin-top: 0.5rem;
        font-size: 1rem;
        line-height: 1.75rem;
        font-weight: 600;
      }}

      .content > div > div {{
        display: flex;
        padding-top: 0.25rem;
        justify-content: flex-end;
        align-content: center;
        flex-direction: column;
      }}

      .left {{
        text-align: right;
        white-space: nowrap;
        width: 15rem;
        font-weight: 500;
      }}

      .center {{
        padding-left: 0.5rem;
        padding-right: 0.5rem;
        font-weight: 600;
      }}

      .right {{
        width: 100%;
        font-weight: 500;
      }}

      .btnouter {{
        margin-bottom: 0.5rem;
        margin-top: 2rem;
        text-align: center;
      }}

      .btnregister {{
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
        padding-left: 3rem;
        padding-right: 3rem;
        border-radius: 9999px;
        font-size: 1.125rem;
        line-height: 1.75rem;
        font-weight: 500;
        text-transform: uppercase;
        background-color: #34d399;
        text-decoration: none;
        color: black;
      }}
      .footer {{
        padding-top: 1rem;
        padding-bottom: 1rem;
        font-size: 0.75rem;
        line-height: 1rem;
        text-align: center;
        color: #71717a;
      }}

      .footer > p {{
        width: 83.333333%;
        margin: 0 auto;
      }}

      .divider {{
        margin-top: 0.75rem;
        margin-bottom: 0.75rem;
        border-radius: 9999px;
        border-width: 1px;
        width: 75%;
      }}
    </style>
  </head>

  <body class="body">
    <header class="header">
      <h3>JSS</h3>
      <p>Training and Placement Cell</p>
    </header>
    <div class="container">
      <h2>{cname}</h2>

      <div class="content">
        <h3>Company Details</h3>
        <div>
          <div>
            <p class="left">Company Name</p>
            <p class="center">:</p>
            <p class="right">{cname}</p>
          </div>
          <div>
            <p class="left">Fulltime CTC</p>
            <p class="center">:</p>
            <p class="right">{package} approx.</p>
          </div>
          <div>
            <p class="left">Internship Stipend</p>
            <p class="center">:</p>
            <p class="right">{internship_stipend} approx.</p>
          </div>
          <div>
            <p class="left">Category</p>
            <p class="center">:</p>
            <p class="right">{category}</p>
          </div>
        </div>
        <h3>Cutoff Details</h3>
        <div>
          <div>
            <p class="left">SSC Cutoff</p>
            <p class="center">:</p>
            <p class="right">{ssc}</p>
          </div>
          <div>
            <p class="left">HSC Cutoff</p>
            <p class="center">:</p>
            <p class="right">{hsc}</p>
          </div>
          <div>
            <p class="left">UG Cutoff</p>
            <p class="center">:</p>
            <p class="right">{ug}</p>
          </div>
          <div>
            <p class="left">PG Cutoff</p>
            <p class="center">:</p>
            <p class="right">{pg}</p>
          </div>
          <div>
            <p class="left">Backlogs allowed</p>
            <p class="center">:</p>
            <p class="right">{b}</p>
          </div>
        </div>

        <h3>Registrations Details</h3>
        <div>
          <div>
            <p class="left">Date</p>
            <p class="center">:</p>
            <p class="right">{date}</p>
          </div>
          <div>
            <p class="left">Deadline</p>
            <p class="center">:</p>
            <p class="right">{deadline}</p>
          </div>
          <div>
            <p class="left">Branches allowed</p>
            <p class="center">:</p>
            <p class="right">
              {branch}
            </p>
          </div>
        </div>
      </div>
      <div class="btnouter">
        <a href="http://central.sjceplacements.org" class="btnregister">Register</a>
      </div>
    </div>
    <footer class="footer">
      <p class="w-5/6 mx-auto">
        You have received this mail because your e-mail ID is registered with
        JSSSTU Placement And Training Cell. This is a system-generated e-mail,
        please don't reply to this message.
      </p>
      <div class="divider"></div>
      <p>JSS Science And Technology University</p>
      <p>Mysuru Karnataka - 570006</p>
    </footer>
  </body>
</html>

        """
        if (file == None and file1 == None and file2 == None):
            message = MessageSchema(
                subject=str(cname)+" information updated",
                recipients=emails,
                html=template,
                subtype='html'
            )
        else:
            if file is not None:
                list1.append(file)
            if file1 is not None:
                list1.append(file1)
            if file2 is not None:
                list1.append(file2)

            message = MessageSchema(
                recipients=emails,
                attachments=list1,
                subject=str(cname)+"'s Information Updated",
                html=template,
                subtype='html'
            )

        session.commit()
        fm = FastMail(conf1)
        await fm.send_message(message)

        session.commit()

        return JSONResponse(status_code = 200, content = {"message":"Details has been updated"})

    except:
        session.rollback()
        raise
    finally:
        session.close()


@admin_router.post("/company/extend_deadline/{cid}", status_code=status.HTTP_201_CREATED)
def extend_deadline(user: schemas.ExtendDeadlineModel, cid: int, a: bool = Depends(get_current_admin)):
    dc = session.query(Company).filter(Company.cid == cid).first()
    if dc is None:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="Company doesn't exists"
                             )
    dc.deadline = user.deadline,
    dc.date = user.date,

    session.commit()

    return {"message": "Company Deadline Updated"}


@admin_router.put("/company/registrations/StartRegistrations{cid}")
def start_registration(cid: int, a: bool = Depends(get_current_admin)):
    db_company = session.query(Company).filter(Company.cid == cid).first()

    if db_company is None:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="Company does not exists"
                            )

    db_company.status = 1
    session.commit()

    # return db_company.cname+" started registrations"
    return JSONResponse(status_code = 200, content = {"message":"Registration started successfully"})


@admin_router.put("/company/registrations/EndRegistrations{cid}")
def end_registration(cid: int, a: bool = Depends(get_current_admin)):
    db_company = session.query(Company).filter(Company.cid == cid).first()

    if db_company is None:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="Company does not exists"
                            )

    db_company.status = 2
    session.commit()

    # return db_company.cname + " ended registrations"
    return JSONResponse(status_code = 200, content = {"message":"Registration ended successfully"})


@admin_router.put("/company/registrations/EndProcess{cid}")
def end_process(cid: int, a: bool = Depends(get_current_admin)):
    db_company = session.query(Company).filter(Company.cid == cid).first()

    if db_company is None:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="Company does not exists"
                             )
    db_company.status = 3
    session.commit()

    # return db_company.cname + " process ended"
    return JSONResponse(status_code = 200, content = {"message":"Process ended successfully"})


@admin_router.get("/status/{college_id}")
def company_records(college_id: int, db: Session = Depends(get_db), a: bool = Depends(get_current_admin), params: Params = Depends(), company: str|None = None):
    IST = pytz.timezone('Asia/Kolkata')
    datetime_ist = datetime.now(IST)
    cur_date_time = datetime_ist.strftime('%Y-%m-%d %H:%M:%S')
    cur_date_time = datetime.strptime(cur_date_time, '%Y-%m-%d %H:%M:%S')     

    ended_records = db.query(models.Company).filter(Company.deadline < cur_date_time).all()
    
    for rec in ended_records:
        if rec.status != 3:
            rec.status = 2
            db.add(rec)

    db.commit()

    if college_id == 1:
        records = db.query(models.Company).filter(
            Company.category != "summer_internship").order_by(Company.date.desc()).all()
        if(company is not None):
            records = db.query(models.Company).filter(
                (models.Company.category != "summer_internship") &(   
                    (models.Company.cname.ilike(f"%{company}%"))|(models.Company.cname.contains(company))
                )).order_by(models.Company.date.desc()).all()
    else:
        records = db.query(models.Company).filter(Company.category != "summer_internship").filter(
            Company.eligible_college_ids.contains(str(college_id))).order_by(Company.date.desc()).all()
        if(company is not None):
            records = db.query(models.Company).filter(
                (Company.category != "summer_internship") & (
                    (models.Company.cname.ilike(f"%{company}%"))|(models.Company.cname.contains(company))
                )).filter(Company.eligible_college_ids.contains(str(college_id))).order_by(Company.date.desc()).all()




    return paginate(records, params)


@admin_router.get("/summer_status/{college_id}")
def company_records_summer(college_id: int, db: Session = Depends(get_db), a: bool = Depends(get_current_admin)):
    if college_id == 1:
        records = db.query(Company).filter(
            Company.category == "summer_internship").all()
    else:
        records = db.query(Company).filter(Company.category == "summer_internship").filter(
            Company.eligible_college_ids.contains(str(college_id))).all()
    return records
from fastapi import Depends, Query
from sqlalchemy import func
from .models import Company, Registrations ,Placed

@admin_router.get("/status_compny_count/{college_id}")
def company_placed_count_records(college_id: int = Query(...), db: Session = Depends(get_db), a: bool = Depends(get_current_admin)):
    try:
        record = []
        if college_id == 1:
            query = db.query(Company.cid, func.count(Placed.cid).label("count_cid")) \
                .outerjoin(Placed, Company.cid == Placed.cid) \
                .group_by(Company.cid) \
                .order_by(Company.cid)
        else:
            query = db.query(Company.cid, func.count(Placed.cid).label("count_cid")) \
                .outerjoin(Placed, Company.cid == Placed.cid) \
                .filter(Company.eligible_college_ids.like(f'%{college_id}%')) \
                .group_by(Company.cid) \
                .order_by(Company.cid)
        result_data = query.all()

        for row in result_data:
            cid, count_cid = row
            record.append({"cid": cid, "count": count_cid if count_cid is not None else 0})

        return record
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
    
    # if college_id == 1:
    #     records = db.query(models.Placed).all()
    #     records2 = db.query(models.Company).all()
    # else:
    #     records = db.query(models.Placed).filter(
    #         Placed.college_id == college_id).all()
    #     records2 = db.query(models.Company).filter(
    #         Company.eligible_college_ids.contains(str(college_id))).all()
    # l2 = len(records2)
    # l = len(records)
    # a = []
    # c = 0
    # row = 1
    # col = 0
    # f = []
    # for i in range(l):
    #     cid = records[i].cid
    #     if cid not in f:

    #         f.append(cid)

    #         c = 0
    #         with engine.connect() as con:
    #             if college_id == 1:
    #                 sql = """select * from students s inner join placed a on s.urn = a.urn where a.cid ={};""".format(
    #                     cid)
    #             else:
    #                 sql = """select * from students s inner join placed a on s.urn = a.urn where a.college_id={} and a.cid ={};""".format(
    #                     college_id, cid)

    #             rs = con.execute(sql)

    #             for i in rs:
    #                 c += 1
    #         a.append({"cid": cid, "count": c})

    # for i in range(l2):
    #     if records2[i].cid not in f:
    #         a.append({"cid": records2[i].cid, "count": 0})

    # return a


 # Import your models

@admin_router.get("/status_compny_reg_count/{college_id}")
def company_reg_count_records(college_id: int = Query(...), db: Session = Depends(get_db), a: bool = Depends(get_current_admin)):
    try:
        record = []
        if college_id == 1:
            query = db.query(Company.cid, func.count(Registrations.cid).label("count_cid")) \
                .outerjoin(Registrations, Company.cid == Registrations.cid) \
                .group_by(Company.cid) \
                .order_by(Company.cid)
        else:
            query = db.query(Company.cid, func.count(Registrations.cid).label("count_cid")) \
                .outerjoin(Registrations, Company.cid == Registrations.cid) \
                .filter(Company.eligible_college_ids.like(f'%{college_id}%')) \
                .group_by(Company.cid) \
                .order_by(Company.cid)
        result_data = query.all()

        for row in result_data:
            cid, count_cid = row
            record.append({"cid": cid, "count": count_cid if count_cid is not None else 0})

        return record
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")

    # return result
    # if college_id == 1:
    #     records = db.query(models.Registrations).all()
    #     records2 = db.query(models.Company).all()
    # else:
    #     records = db.query(models.Registrations).filter(
    #         models.Registrations.college_id == college_id).all()
    #     records2 = db.query(models.Company).filter(
    #         Company.eligible_college_ids.contains(str(college_id))).all()
    # # return records
    # # return records2
    # l2 = len(records2)

    # l = len(records)
    # a = []
    # c = 0
    # f = []

    # for i in range(l):
    #     cid = records[i].cid
    #     if cid not in f:
    #         f.append(cid)

    #         c = 0
    #         with engine.connect() as con:
    #             if college_id == 1:
    #                 sql = """select * from registrations where cid ={};""".format(
    #                     cid)
    #             else:
    #                 sql = """select * from registrations where college_id= {} and cid ={};""".format(
    #                     college_id, cid)

    #             rs = con.execute(sql)

    #             for i in rs:
    #                 c += 1

    #         a.append({"cid": cid, "count": c})
    # for i in range(l2):
    #     if records2[i].cid not in f:
    #         a.append({"cid": records2[i].cid, "count": 0})
    # return a

@admin_router.get("/student/resume/{urn}", status_code=status.HTTP_200_OK)
def get_resume(urn: str, session=Depends(get_db), a: bool = Depends(get_current_admin)):
    urn = urn.upper()
    dc = session.query(User).filter(User.urn == urn).first()
    if dc is None:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="Student doesn't exists"
                             )
    return dc.resume_link

@admin_router.get("/student/blacklistcount/{college_id}", status_code=status.HTTP_200_OK)
def get_blacklistcount(college_id: int, session=Depends(get_db), a: bool = Depends(get_current_admin)):
    count = session.query(Blacklist).join(User, Blacklist.urn == User.urn).filter(
        Blacklist.credits == 0,
        User.college_id == college_id
    ).count()

    return {"blacklist_count": count}

@admin_router.put("/student/edit_student/{urn}", status_code=status.HTTP_201_CREATED)
def update_student(user: StudentModel, urn: str, session=Depends(get_db), a: bool = Depends(get_current_admin)):
    urn = urn.upper()
    dc = session.query(User).filter(User.urn == urn).first()
    if dc is None:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="Student doesn't exists"
                             )
    dc.urn = user.urn,
    dc.full_name = user.full_name,
    dc.email = user.email,
    dc.branch = user.branch,
    dc.first_name = user.first_name,
    dc.last_name = user.last_name,
    dc.middle_name = user.middle_name,
    dc.ssc = user.ssc
    dc.hsc = user.hsc
    dc.ug = user.ug,
    dc.pg = user.pg,
    dc.ug_percentage = user.ug_percentage
    dc.backlogs = user.backlogs,
    dc.sem1 = user.sem1
    dc.sem2 = user.sem2
    dc.sem3 = user.sem3
    dc.sem4 = user.sem4
    dc.sem5 = user.sem5
    dc.sem6 = user.sem6
    dc.sem7 = user.sem7
    dc.sem8 = user.sem8
    dc.current_backlogs = user.current_backlogs
    dc.history_backlogs = user.history_backlogs
    dc.no_of_x_grades = user.no_of_x_grades
    dc.other_grades = user.other_grades
    dc.ug_start_year = user.ug_start_year
    dc.ug_end_year = user.ug_end_year
    dc.ssc_board = user.ssc_board
    dc.hsc_board = user.hsc_board
    dc.hsc_start_year = user.hsc_start_year
    dc.hsc_end_year = user.hsc_end_year
    dc.ssc_start_year = user.ssc_start_year
    dc.ssc_end_year = user.ssc_end_year
    dc.entry_to_college = user.entry_to_college
    dc.rank = user.rank
    dc.gap_in_studies = user.gap_in_studies
    dc.dob = user.dob
    dc.gender = user.gender
    dc.category = user.category
    dc.native = user.native
    dc.parents_name = user.parents_name
    dc.present_addr = user.present_addr
    dc.permanent_addr = user.permanent_addr
    dc.phone = user.phone
    dc.secondary_phone = user.secondary_phone
    dc.verified = user.verified

    session.commit()
    return JSONResponse(status_code = 200, content = {"message":"Student Details Updated"})


@admin_router.post("/company/registrations/place_students/{cid}/{college_id}", status_code=status.HTTP_201_CREATED)
async def place_students(cid: int, college_id: int, student_list: str, category_placed: str, db:session=Depends(get_db), a: bool = Depends(get_current_admin)):
    
    already_placed = db.query(Placed).filter(Placed.urn == student_list).filter(Placed.cid == cid).first()
    if already_placed:
        return False
    
    urn= student_list
    student= db.query(User).filter(User.urn==urn).first()
    name= student.full_name
    urn = student.urn
    branch = student.branch
    gender =student.gender
    if gender == "male" or gender == "Male" or gender=="m" or gender=="MALE":
        gender = "M"
    elif gender == "female" or gender == "Female" or gender=="MALE" or gender=="f":
        gender = "F"

    email = student.email
    phone = student.phone
        
    if category_placed == "tier1":
        tier1 = True
    else:
        tier1 = False

    if category_placed == "tier2":
        tier2 = True
    else:
        tier2 = False

    if category_placed == "dream":
        dream = True
    else:
        dream = False
            
    if category_placed == "core":
        core = True
    else:
        core = False

    if category_placed == "internship":
        internship = True
    else:
        internship = False

    if category_placed == "summer_internship":
        summer_internship = True
    else:
        summer_internship = False

    placed = Placed_category(name=name, urn=urn, branch=branch, gender=gender, email=email, phone=phone, tier2=tier2,
                                 tier1=tier1, dream=dream, internship=internship, summer_internship=summer_internship, cid=cid,core=core, college_id=college_id)
    feedback = True

    placed2 = Placed(urn=urn, cid=cid, category_placed=category_placed,
                         feedback=feedback, college_id=college_id)
    db.add(placed)
    db.add(placed2)
    db.commit()

    return {"message": "Students Placed"}

@admin_router.post("/company/registrations/place_summer_interns/{cid}", status_code=status.HTTP_201_CREATED)
def place_students(cid: int, name: str, urn: str, branch: str, gender: str, email: str, phone: str, session=Depends(get_db), a: bool = Depends(get_current_admin)):
    urn = urn.upper()
    gender = gender.upper()
    branch = branch
    category_placed = "summer_internship"
    summer_internship = True
    placed = Placed_category(name=name, urn=urn, branch=branch, gender=gender, email=email, phone=phone,
                             tier2=False, tier1=False, dream=False, internship=False, summer_internship=summer_internship, cid=cid)
    feedback = True
    placed2 = Placed(urn=urn, cid=cid,
                     category_placed=category_placed, feedback=feedback)
    session.add(placed)
    session.add(placed2)

    session.commit()
    return {"message": "Summer Intern Students Placed"}


@admin_router.delete("/company/registrations/unplace{urn}/{cid}", status_code=status.HTTP_201_CREATED)
def unplace_students(urn: str, cid: int, session=Depends(get_db), a: bool = Depends(get_current_admin)):
    urn = urn.upper()
    session.query(Placed).filter_by(urn=urn).filter_by(cid=cid).delete()
    session.query(Placed_category).filter_by(
        urn=urn).filter_by(cid=cid).delete()

    session.commit()
    return {"message": "Student Unplaced"}


@admin_router.delete("/company/registrations/unregister{urn}/{cid}", status_code=status.HTTP_201_CREATED)
def un_register_students(urn: str, cid: int, session=Depends(get_db), a: bool = Depends(get_current_admin)):
    urn = urn.upper()
    session.query(Registrations).filter_by(urn=urn).filter_by(cid=cid).delete()
    session.commit()
    return {"message": "Student un-registered"}


@admin_router.get("/company/registrations/convert/{cid}", status_code=status.HTTP_201_CREATED)
def convert_summerinterns(urn: str, cid: int, session=Depends(get_db), a: bool = Depends(get_current_admin)):
    urn = urn.upper()

    db_student = session.query(Placed).filter(
        Placed.urn == urn).filter(Placed.cid == cid)
    # at last we will look upto to placed table to check the final status of the student
    db_student.update({"category_placed": "tier2"})
    db_student1 = session.query(Placed_category).filter(
        Placed_category.urn == urn).filter(Placed_category.cid == cid)
    # at last we will look upto to placed table to check the final status of the student
    db_student1.update({"tier2": True})

    session.commit()
    return {"message": "TIER UPDATED"}


@admin_router.get("/company/registrations/details{cid}", status_code=status.HTTP_201_CREATED)
def get_company_details(cid: int, session=Depends(get_db), a: bool = Depends(get_current_admin)):
    db_company = session.query(Company).filter(Company.cid == cid).first()
    return db_company


@admin_router.get("/company/place_summer_interns/details{cid}", status_code=status.HTTP_201_CREATED)
def get_summerintern_details(cid: int, session=Depends(get_db), a: bool = Depends(get_current_admin)):
    db_company = session.query(Placed.urn).filter_by(cid=cid).all()
    l = []
    for i in db_company:
        db_user = session.query(User).filter(User.urn == i[0]).first()
        l.append(db_user)
    return l


@admin_router.get("/company/registrations/place_students/Select_students{cid}/{college_id}", status_code=status.HTTP_201_CREATED)
async def select_registered_students(cid: int, college_id: int, db: Session = Depends(get_db), a: bool = Depends(get_current_admin)):
        if college_id == 1:
            urn = db.query(Registrations.urn).filter(Registrations.cid == cid).order_by(Registrations.college_id.asc()).all()
        else:
            urn = db.query(Registrations.urn).filter(Registrations.cid == cid).filter(Registrations.college_id == college_id).all()
        urn_list = []
        # return urn
        for i in urn:  # i is object
            urn_list.append(i.urn)
        # return urn_list # ["01JST20IS033 , "01JST20IS030"]
        record_list = []
        college_names = ["", "JSS Mysore", "JSS Bangalore", "JSS Noida"]
        for urn in urn_list:
            if len(db.query(Placed).filter(Placed.urn == urn).filter(Placed.cid == cid).all()) == 0:
                record_urn = urn
                record = db.query(User).filter(User.urn == urn).all()
                record_name = record[0].full_name
                record_branch = record[0].branch
                record_college_id = record[0].college_id
                record_list.append({"urn": record_urn, "name": record_name,
                                "branch": record_branch, "college": college_names[record_college_id]})
        return record_list
    
@admin_router.get("/company/registrations/place_students/placed_students_info/{cid}/{college_id}", status_code=status.HTTP_201_CREATED)
def select_placed_students(cid: int, college_id: int, db: Session = Depends(get_db), a: bool = Depends(get_current_admin)):
    
        # return db.query(Placed_category).filter(Placed_category.cid == cid).order_by(Placed_category.college_id.asc()).all()
        if college_id == 1:
            records = db.query(Placed_category).filter(Placed_category.cid == cid).order_by(Placed_category.college_id.asc()).all()
        else:
            records = db.query(Placed_category).filter(Placed_category.cid == cid).filter(Placed_category.college_id == college_id).all()
        # urn_list = []
        placed_record = []
        college_names = ["", "JSS Mysore", "JSS Bangalore", "JSS Noida"]
        # for i in urn:
        #     urn_list.append(i.urn)
            
        # return records
        for record in records:
            category = "NULL"
            records_urn = record.urn
            records_name = record.name
            records_branch = record.branch
            records_tier1 = record.tier1
            records_tier2 = record.tier2
            records_internship = record.internship
            records_summer_internship = record.summer_internship
            records_dream = record.dream
            records_core = record.core
            records_cid = record.cid
            record_college_id = record.college_id
            if records_tier1:
                category = "Tier-1"
            elif records_tier2:
                category = "Tier-2"
            elif records_internship:
                category = "Internship"
            elif records_summer_internship:
                category = "Summer Internship"
            elif records_core:
                category = "Core"
            elif records_dream:
                category = "Dream"
            placed_record.append({"urn": records_urn, "name": records_name, "branch": records_branch,
                                "cid": records_cid, "category": category, "college": college_names[record_college_id]})

        return placed_record


@admin_router.get("/studentprofile/{urn}", include_in_schema=True)
def my_profile(urn: str, db: Session = Depends(get_db), b: bool = Depends(get_current_admin)):
    # return b
    urn = urn.upper()
    item = db.query(User).filter(User.urn == urn).first()
   
    if item is None:
        raise HTTPException(status_code=404, detail="User not found")

    if(item.resume_link==None):
        item.resume_link=""
        
    return item


@admin_router.delete("/company/rejectppo/{urn}/{cid}", status_code=status.HTTP_201_CREATED)
def reject_ppo(urn:str, cid:int, db: Session = Depends(get_db), b:bool= Depends(get_current_admin)):
    try:
        urn = urn.upper()
        college_id = db.query(User).filter(User.urn == urn ).first().college_id
        if college_id != 1:
            # return {"message":"Not Valid for this User","success":False}
            return JSONResponse(status_code = 403, content = {"message":"Not Valid for this User"})
        company = db.query(Company).filter(Company.cid == cid).first()
        placed = db.query(Placed).filter(Placed.cid == cid).filter(Placed.urn == urn).first()
        category_placed = placed.category_placed
        offer_detail= Offer(urn=urn,is_internship=1,cid=cid,category=category_placed)
        db.add(offer_detail)
        db.query(Placed).filter_by(urn=urn).filter_by(cid=cid).delete()
        db.query(Placed_category).filter_by(urn=urn).filter_by(cid=cid).delete()
        db.commit()
        
        return JSONResponse(status_code = 200, content = {"message": f"PPO rejected by {company.cname} in {category_placed} category"})
    except:
        db.rollback()
        
        
        
from .constants import get_blacklist_email_message
@admin_router.post("/company/blacklist/{urn}/{reason}", include_in_schema=True)
async def blacklist_student(urn:str,reason:str,background_tasks:BackgroundTasks,db: Session=Depends(get_db),a: bool = Depends(get_current_admin)):
    urn = urn.strip().upper()
    blacklist_record = db.query(Blacklist).filter(Blacklist.urn ==urn).first()
    # return blacklist_record
    user_data = db.query(User).filter(User.urn == urn).first()
    college_id = user_data.college_id
    credits = blacklist_record.credits
    # company_count = blacklist_record.company_count
    if credits == 0:
            return JSONResponse(status_code= 200 , content = {"message": "Already Blacklisted"})
    if college_id == 1:
            email_template=''; 
            # print(f"reason: {reason}")
            if reason is not None:
                email_template = get_blacklist_email_message(
                student_name=user_data.full_name,
                student_urn=user_data.urn,
                blacklist_reason=reason
            )
            else:
                email_template = get_blacklist_email_message(
                student_name=user_data.full_name,
                student_urn=user_data.urn
            )

            # print(f"email_template: {email_template}")
            message = MessageSchema(
                subject="Important: Blacklisted from SJCE Placements",
                recipients=[user_data.email],
                html=email_template,
            )

            fm = FastMail(conf1)
            background_tasks.add_task(fm.send_message, message)
            # await fm.send_message(message)
            blacklist_record.credits = 0
            db.commit()
    # else:
    #     # return company_count

    #     if credits > 0:
    #         credits = credits - 4
    #     else:
    #         credits =0
    #         company_count = 0
    # db.commit()
    
    return JSONResponse(status_code= 200 , content = {"message": "Email Sent and Blacklisted Successfully"})
    
@admin_router.post("/company/unblacklist/{urn}",include_in_schema=True)
def unblacklist_student(urn:str,db: Session=Depends(get_db),a: bool = Depends(get_current_admin)):
    blacklist_record = db.query(Blacklist).filter(Blacklist.urn ==urn).first()
    # return blacklist_record
    user_date = db.query(User).filter(User.urn == urn).first()
    college_id = user_date.college_id
    credits = blacklist_record.credits
    # company_count = blacklist_record.company_count
    if college_id == 1:
        if credits == 12:
            return JSONResponse(status_code= 200 , content = {"message": "Already UnBlacklisted"})
        blacklist_record.credits = 12
        db.commit()
    return JSONResponse(status_code= 200 , content = {"message": "UnBlacklisted Successfully"})

from sqlalchemy.sql import text

@admin_router.get("/company/progress/{cid}",include_in_schema=True)
def get_all_students_progress_of_company(cid:int,db: Session=Depends(get_db),a:bool= Depends(get_current_admin)):

    sql_q = """
    SELECT p.rid,r.urn,s.full_name,s.branch,c.cname,p.test,p.tech_interview,p.gd,p.hr_interview
FROM progress p
JOIN registrations r ON p.rid = r.rid
JOIN students s ON s.urn = r.urn
JOIN company c ON c.cid = r.cid
WHERE r.cid = %s;
"""
    progress = []
    with engine.connect() as con:
        result = con.execute(sql_q,(cid))

        column_names = result.keys()
        # print(column_names)
        for row in result:
            row_data = {col:row[col] for col in column_names}
            print(row_data)
            progress.append(row_data)
        
    status_info = {0:"N/A",1:"Cleared",-1:"Didn't Clear"}
    return JSONResponse(status_code=200,content={"status_info":status_info,"progress_data":progress})

def get_student_progess_of_company(rid:int,db: Session=Depends(get_db),a:bool= Depends(get_current_admin)):

    sql_q = """
    SELECT p.rid,r.urn,s.full_name,s.branch,c.cname,p.test,p.tech_interview,p.gd,p.hr_interview
FROM progress p
JOIN registrations r ON p.rid = r.rid
JOIN students s ON s.urn = r.urn
JOIN company c ON c.cid = r.cid
WHERE r.rid = %s;
"""
    progress = []
    with engine.connect() as con:
        result = con.execute(sql_q,(rid))

        column_names = result.keys()
        # print(column_names)
        for row in result:
            row_data = {col:row[col] for col in column_names}
            print(row_data)
            progress.append(row_data)
        
    status_info = {0:"N/A",1:"Cleared",-1:"Didn't Clear"}
    return JSONResponse(status_code=200,content={"status_info":status_info,"progress_data":progress})


@admin_router.put("/company/progress",include_in_schema=True)
def update_student_progess_of_a_company(progress_update : schemas.ProgressUpdate,db: Session=Depends(get_db),a:bool= Depends(get_current_admin)):

    round_columns = crud.get_column_names("progress")
    round_columns.remove('rid')
    print(round_columns)

    filtered_update = []

    for round_info in progress_update.progressData:
        if (round_info.round_name in round_columns) and (round_info.status in [-1,0,1]):
            filtered_update.append([round_info.round_name,round_info.status])
        else:
            print(f"Skipped : {round_info}")
            
    print(filtered_update)
    rid = progress_update.rid
    if(filtered_update):
        for column,status in filtered_update:
            print(column,status)
            q = f"""
                UPDATE progress
                SET {column} = :status
                WHERE rid = :rid
                """
            
            db.execute(text(q),{"status":status,"rid":rid})
            
        db.commit()

    # write the sql query to update , [{'test': 1}]
    return get_student_progess_of_company(rid)

