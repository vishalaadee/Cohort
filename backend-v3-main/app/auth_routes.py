from .admin_routes import get_current_admin
import email,io,xlsxwriter,ast,json
from io import BytesIO
from fastapi import File,UploadFile,Form,Body,Response,FastAPI, BackgroundTasks,APIRouter,status,Depends
from fastapi.responses import StreamingResponse
from starlette.requests import Request
from starlette.responses import JSONResponse
from .student_routes import get_current_student
from pydantic import EmailStr, BaseModel
from typing import List, Optional
from fastapi.exceptions import HTTPException
from .database import Session,engine
from .schemas import RegisterStudent, StudentModel,LoginModel,EmailSchema
from .models import User,Credentials
from werkzeug.security import generate_password_hash , check_password_hash
from fastapi_jwt_auth import AuthJWT
from fastapi.encoders import jsonable_encoder
from fastapi_mail import FastMail, MessageSchema,ConnectionConfig
from . import crud, models, schemas


auth_router = APIRouter(
    prefix='/auth',
    tags=['auth']
    )

session=Session(bind=engine)

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
        

session=Session(bind=engine)

# @auth_router.post('/auth/admin_login',status_code=200)
# async def admin_login(urn:str,password:str,Authorize:AuthJWT=Depends()):
#     urn=urn.upper()
#     urn=urn.strip()
#     password=password.upper()
#     password=password.strip()
#     if urn=="ALLISWELL123" and password=="PRADEEPSIR":
#         access_token=Authorize.create_access_token(subject=password)
#         refresh_token=Authorize.create_refresh_token(subject=password)

#         response={
#             "access":access_token,
#             "refresh":refresh_token
#         }

#         return jsonable_encoder(response)

#     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
#         detail="Password"
#     )

@auth_router.post('/auth/third_year_login',status_code=200)
def third_year_login(urn:str,password:str,Authorize:AuthJWT=Depends()):
    urn=urn.upper()
    urn=urn.strip()
    password=password.upper()
    #return password
    password=password.strip()
    # if (urn=="JSSATEN" and password=="PLACEMENT2024") or (urn[:7]=="01JST20" and password=="HARDWORK2024") or (urn=="JSSATE" and password=="PLACEMENT2024"):
    if (urn[:7]=="01JST20" and password=="HARDWORK2024"):
        access_token=Authorize.create_access_token(subject=password)
        refresh_token=Authorize.create_refresh_token(subject=password)

        response={
            "college_id":1,
            "access":access_token,
            "refresh":refresh_token
        }

        return jsonable_encoder(response)
    if (urn=="JSSATE" and password=="PLACEMENT2024"):
        access_token=Authorize.create_access_token(subject=password)
        refresh_token=Authorize.create_refresh_token(subject=password)

        response={
            "college_id":2,
            "access":access_token,
            "refresh":refresh_token
        }

        return jsonable_encoder(response)
    
    if (urn=="JSSATEN" and password=="PLACEMENT2024"):
        access_token=Authorize.create_access_token(subject=password)
        refresh_token=Authorize.create_refresh_token(subject=password)

        response={
            "college_id":3,
            "access":access_token,
            "refresh":refresh_token
        }

        return jsonable_encoder(response)

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
        detail="Password"
    )
    
@auth_router.post('/auth/head_pslogin',status_code=200)
def ps_login(urn:str,password:str,Authorize:AuthJWT=Depends()):
    urn=urn.upper()
    urn=urn.strip()
    password=password.upper()
    password=password.strip()
    if urn=="HEADPSOFNOIDA" and password=="NOIDASECRETKEY":
        access_token=Authorize.create_access_token(subject=password)
        refresh_token=Authorize.create_refresh_token(subject=password)

        response={
            "access":access_token,
            "refresh":refresh_token
        }

        return jsonable_encoder(response)

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
        detail="Error in Credentials"
    )
    
@auth_router.post('/auth/pslogin',status_code=200)
def ps_login(urn:str,password:str,Authorize:AuthJWT=Depends()):
    urn=urn.upper()
    urn=urn.strip()
    password=password.upper()
    password=password.strip()
    if urn=="PSLOGINOFNOIDA" and password=="PLACEMENTATNOIDA":
        access_token=Authorize.create_access_token(subject=password)
        refresh_token=Authorize.create_refresh_token(subject=password)

        response={
            "access":access_token,
            "refresh":refresh_token
        }

        return jsonable_encoder(response)

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
        detail="Wrong Credentials"
    )
     
    
@auth_router.post('/auth/management_login',status_code=200)
def managemnt_login(urn:str,password:str,Authorize:AuthJWT=Depends()):
    urn=urn.upper()
    urn=urn.strip()
    password=password.upper()
    password=password.strip()
    if urn=="EDUCATIONJSS" and password=="PLACEMENTFORJSS@123":
        access_token=Authorize.create_access_token(subject=password)
        refresh_token=Authorize.create_refresh_token(subject=password)

        response={
            "access":access_token,
            "refresh":refresh_token
        }

        return jsonable_encoder(response)

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
        detail="INVALID CREDENTIALS"
    )
@auth_router.get("/get_all_alumni_details")
def get_all_alumni_details(db: Session = Depends(get_db)):
    return crud.get_all_alumni_details(db=db)
@auth_router.get("/get_all_alumni_by_email/{email}")
def get_all_alumni_details_by_email(email:str,db: Session = Depends(get_db)):
    return crud.get_alumni_details(db=db,email=email)
        

@auth_router.post("/alumni/send_email_alumni/{email}",status_code=status.HTTP_201_CREATED)
async def alumni_mail(a_email:str,s_name:str,s_email:str,subject:str,body:str,db: session = Depends(get_db)) -> JSONResponse:
    conf = ConnectionConfig(
    MAIL_USERNAME = "placementsjssate@gmail.com",
    MAIL_PASSWORD = "ugpfesadhglobidd",
    MAIL_FROM = s_email,
    MAIL_PORT = 587,
    MAIL_SERVER = "smtp.gmail.com",
    MAIL_FROM_NAME=s_name,
    MAIL_TLS = True,
    MAIL_SSL = False,
    USE_CREDENTIALS = True,
    VALIDATE_CERTS = True
)
    
    message = MessageSchema(
        subject="Mail from "+ str(s_name),
        recipients=[a_email],  # List of recipients, as many as you can pass 
        body="Student's Email: "+str(s_email)+"\n"+"Subject: "+str(subject)+"\n"+"\n"+ str(body)+"\n"+"\n"+"Thanks and Regards"+"\n"+str(s_name)
        )
    fm = FastMail(conf)
    await fm.send_message(message)
    return JSONResponse(status_code=200, content={"message": "email has been sent"})
        
 
# @auth_router.post('/login',status_code=200)
# def login(urn:str,password:str,Authorize:AuthJWT=Depends()):
#     urn=urn.upper()
#     urn=urn.strip()
#     db_user=session.query(Credentials).filter(urn==Credentials.urn).first()
#     password=password.strip()
#     if db_user and check_password_hash(db_user.password,password):
#         access_token=Authorize.create_access_token(subject=db_user.urn)
#         refresh_token=Authorize.create_refresh_token(subject=db_user.urn)

#         response={
#             "access":access_token,
#             "refresh":refresh_token
#         }

#         return jsonable_encoder(response)

#     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
#         detail="Invalid Username Or Password"
#     )



#refreshing tokens





#THIS WEBSITE IS MADE BY:
#BACKEND+DB+Analytics+devops CREDIT->VISHAL MISHRA AND HARSH R SHAH
#FRONTEND CREDIT->SHOMIK GHOSH AND NAMAN OLI
#Placement Secretary->Yashas Uttangi 
#SPECIAL THANKS TO: MR.M PRADEEP SIR,SPARSH RAO,SANCHITH HEGDE,Narayan Bhat AND PRAJITH NAIR