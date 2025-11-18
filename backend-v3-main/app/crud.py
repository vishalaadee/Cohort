import json
import ast
from pyexpat import model
from typing import List
from .database import engine,inspect
from sqlalchemy.orm import Session  # type: ignore
from .models import User,Company,Registrations,Placed,Placed_category,Credentials,College
from . import models, schemas


def get_college_id(db: Session,college_id:int):
    return db.query(models.College).filter(college_id==models.College.college_id).first()


def get_user(db: Session, cid: int):
    return db.query(models.Company).filter(models.Company.cid == cid).first()

def get_alumni_details(db: Session, email: str):
    return db.query(models.alumni).filter_by(a_email=email).first()
def get_all_alumni_details(db: Session):
    return db.query(models.alumni).order_by(models.alumni.a_cname.asc()).all()
def get_item_by_urn(db: Session, urn: str):
    urn=urn.upper()
    return db.query(User).filter_by(urn=urn).first()

def get_item_by_company(db: Session, cid: int):
    return db.query(Company).filter_by(cid=cid).first()

def item_of_company(db: Session):
    return db.query(Company).all()

def get_registered_students(db: Session, cid: int):
    return db.query(Registrations.urn).filter_by(cid=cid).all()

def get_placed_students(db: Session, cid: int):
    return db.query(Placed.urn).filter_by(cid=cid).all()

def get_placed_students_cname(db: Session, urn: str):
    urn=urn.upper()
    companyid= db.query(Placed.cid).filter_by(urn=urn).all()
    records = str(companyid) 
    data = json.dumps(ast.literal_eval(records)) 
    exist=json.loads(data)
    cate=[]
    j=0
    for i in exist:
        cate.append(exist[j][0])
        j+=1
    #return cate
    c_details=[]
    for i in cate:
        c_d=db.query(Company.cname).filter_by(cid=i).all()   
        records = str(c_d) 
        data = json.dumps(ast.literal_eval(records)) 
        exist=json.loads(data)
        c_details.append(exist)  
    return [e for sl in c_details for e in sl]

def get_placedcategory_students(db: Session, urn: str):
    urn=urn.upper()
    companyid= db.query(Placed.cid).filter_by(urn=urn).all()
    records = str(companyid) 
    data = json.dumps(ast.literal_eval(records)) 
    exist=json.loads(data)
    cate=[]
    j=0
    for i in exist:
        cate.append(exist[j][0])
        j+=1
    #return cate
    c_details=[]
    for i in cate:
        c_d=db.query(Company.category).filter_by(cid=i).all()   
        records = str(c_d) 
        data = json.dumps(ast.literal_eval(records)) 
        exist=json.loads(data)
        c_details.append(exist)  
    return [e for sl in c_details for e in sl]      
    

def get_stipend_students(db: Session, urn: str):
    urn=urn.upper()
    companyid= db.query(Placed.cid).filter_by(urn=urn).all()
    records = str(companyid) 
    data = json.dumps(ast.literal_eval(records)) 
    exist=json.loads(data)
    cate=[]
    j=0
    for i in exist:
        cate.append(exist[j][0])
        j+=1
    #return cate
    c_details=[]
    for i in cate:
        c_d=db.query(Company.internship_stipend).filter_by(cid=i).all()   
        records = str(c_d) 
        data = json.dumps(ast.literal_eval(records)) 
        exist=json.loads(data)
        c_details.append(exist)  
    return [e for sl in c_details for e in sl]

def get_cname_students(db: Session, urn: str):
    urn=urn.upper()
    companyid= db.query(Placed.cid).filter_by(urn=urn).all()
    records = str(companyid) 
    data = json.dumps(ast.literal_eval(records)) 
    exist=json.loads(data)
    cate=[]
    j=0
    for i in exist:
        cate.append(exist[j][0])
        j+=1
    #return cate
    c_details=[]
    for i in cate:
        c_d=db.query(Company.cname).filter_by(cid=i).all()   
        records = str(c_d) 
        data = json.dumps(ast.literal_eval(records)) 
        exist=json.loads(data)
        c_details.append(exist)  
    return [e for sl in c_details for e in sl]

def get_package_students(db: Session, urn: str):
    urn=urn.upper()
    companyid= db.query(Placed.cid).filter_by(urn=urn).all()
    records = str(companyid) 
    data = json.dumps(ast.literal_eval(records)) 
    exist=json.loads(data)
    cate=[]
    j=0
    for i in exist:
        cate.append(exist[j][0])
        j+=1
    #return cate
    c_details=[]
    for i in cate:
        c_d=db.query(Company.package).filter_by(cid=i).all()   
        records = str(c_d) 
        data = json.dumps(ast.literal_eval(records)) 
        exist=json.loads(data)
        c_details.append(exist)  
    return [e for sl in c_details for e in sl]

def placed_category(db: Session, urn: str):
    urn=urn.upper()
    return db.query(Placed.category_placed).filter_by(urn=urn).all()

def get_item_by_companies(db: Session, cid: int):
    return db.query(Company.cname).filter_by(cid=cid).first()

def get_item_by_branch(db: Session, cid: int):
    return db.query(Company.branch).filter_by(cid=cid).first()

def get_item_by_credentials(db: Session, urn:str):
    urn=urn.upper()
    return db.query(Credentials).filter_by(urn=urn)

def get_items(session: Session, skip: int = 0, limit: int = 100) -> List[Company]:
    return session.query(Company).offset(skip).limit(limit).all()

def register_student(db:Session,urn: str, cid:int):
    urn=urn.upper()
    student=Registrations(urn=urn,cid=cid)
    db.add(student)
    db.commit()    
    return {"message":"Registration Successful"}

def placed_item(db: Session, urn: str):
    urn=urn.upper()
    category=db.query(Placed.category_placed).filter_by(urn=urn).all()
    return category

def get_branch_students(db: Session, urn: str):
    urn=urn.upper()
    branch = db.query(User.branch).filter_by(urn=urn).first()
    return branch

def get_column_names(table_name: str):
    # Use SQLAlchemy's inspector to get table columns
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    return [column['name'] for column in columns]
