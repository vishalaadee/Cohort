from .admin_routes import get_current_admin
import databases
import io,xlsxwriter,json
from sqlalchemy import distinct
from io import BytesIO
from math import ceil, floor 
import email
from unicodedata import category
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastapi import FastAPI, BackgroundTasks
from pydantic import EmailStr, BaseModel
from typing import List, Optional
from fastapi import APIRouter,status,Depends
from fastapi.exceptions import HTTPException
from .database import Session,engine
from fastapi.exceptions import HTTPException
from werkzeug.security import generate_password_hash , check_password_hash
from fastapi_jwt_auth import AuthJWT
from fastapi.encoders import jsonable_encoder
from fastapi import BackgroundTasks
from fastapi import FastAPI
from fastapi_mail import FastMail, MessageSchema,ConnectionConfig
from starlette.requests import Request
from starlette.responses import JSONResponse
from pydantic import EmailStr, BaseModel
from fastapi.responses import StreamingResponse
from typing import List
from .models import User
from .schemas import StudentDetails,RemindModel,RemindModel2
from . import crud, models, schemas
import inspect
import databases
import io,xlsxwriter,json
from io import BytesIO, StringIO
import email
from unicodedata import category
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastapi import FastAPI, BackgroundTasks
from pydantic import EmailStr, BaseModel
from typing import List, Optional
from fastapi import APIRouter,status,Depends,File,UploadFile
from .database import Session,engine
from fastapi.exceptions import HTTPException
from fastapi import BackgroundTasks
from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse
from pydantic import EmailStr, BaseModel
from fastapi.responses import StreamingResponse
from typing import List
from . import crud, models, schemas
from tempfile import NamedTemporaryFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTasks
import smtplib,time
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.utils import formatdate
from email import encoders
import os,datetime
import pytz
import smtplib,time
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.utils import formatdate
from email import encoders
import os,datetime

noida_stats_router = APIRouter(
    prefix='/stats/noida',
    tags=['stats_noida']
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
        


session=Session(bind=engine)


@noida_stats_router.post("/home/test_reminder/{cid}/",include_in_schema=True)
def test_remind(remind:List[RemindModel2],db:Session=Depends(get_db),a:bool=Depends(get_current_admin)):
    a=db.query(models.Company.cname).filter(models.Company.cid == remind[0].cid).first()
    b=a.cname
    link=remind[0].link
   
    CRLF = "\r\n"
    login = "placementsjssate@gmail.com"
    password = "ugpfesadhglobidd"
    urn=db.query(models.Registrations.urn).filter_by(cid=remind[0].cid).all()
    aa=[]
    for i in urn:
        aa.append(i[0])
    ba=[]
    for i in aa:
        email=db.query(models.User.email).filter_by(urn=i).all()
        ba.append(email[0][0])
    attendees = ba #['aadeevishal@gmail.com'] 
    # change the placement email to depending on the college placement email
    fro = "Placement Information JSSATE <placementsjssate@gmail.com>"
    organizer = "ORGANIZER;CN=Placement Cell:mailto:placementsjssate"+CRLF+" @gmail.com"
    
   
   
    description = "Test Link "+ str(link) +CRLF
    attendee = ""
    for att in attendees:
        attendee += "ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-    PARTICIPANT;PARTSTAT=ACCEPTED;RSVP=TRUE"+CRLF+" ;CN="+att+";X-NUM-GUESTS=0:"+CRLF+" mailto:"+att+CRLF
   
    eml_body = "Link for test " + str(link)
    
    msg = MIMEMultipart('mixed')
    msg['Reply-To']=fro
    msg['Date'] = formatdate(localtime=False)
    msg['Subject'] = "Test Link for  "+b
    msg['From'] = fro
    msg['To'] = ",".join(attendees)

    part_email = MIMEText(eml_body,"html")
   
    msgAlternative = MIMEMultipart('alternative')
    msg.attach(msgAlternative)
    ical_atch = MIMEBase('application/ics',' ;name="%s"'%("invite.ics"))
    ical_atch.add_header('Content-Disposition', 'attachment; filename="%s"'%("invite.ics"))

    eml_atch = MIMEText('', 'plain')
    encoders.encode_base64(eml_atch)
    eml_atch.add_header('Content-Transfer-Encoding', "")


    msgAlternative.attach(part_email)
   
    mailServer = smtplib.SMTP('smtp.gmail.com', 587)
    mailServer.ehlo()
    mailServer.starttls()
    mailServer.ehlo()
    mailServer.login(login, password)
    mailServer.sendmail(fro, attendees, msg.as_string())
    mailServer.close()
    return True



@noida_stats_router.post("/home/send_reminder/{cid}",include_in_schema=True)
def remind(remind:List[RemindModel],db:Session=Depends(get_db),a:bool=Depends(get_current_admin)):
    a=db.query(models.Company.cname).filter(models.Company.cid == remind[0].cid).first()
    b=a.cname
    UTC = pytz.utc
    IST = pytz.timezone('Asia/Kolkata')
    CRLF = "\r\n"
    login = "placementsjssate@gmail.com"
    password = "ugpfesadhglobidd"
    urn=db.query(models.Registrations.urn).filter_by(cid=remind[0].cid).all()
    aa=[]
    for i in urn:
        aa.append(i[0])
    ba=[]
    for i in aa:
        email=db.query(models.User.email).filter_by(urn=i).all()
        ba.append(email[0][0])
    attendees = ba #['aadeevishal@gmail.com'] 
    fro = "Placement Information <placementsjssate@gmail.com>"
    organizer = "ORGANIZER;CN=Placement Cell:mailto:placementsjssate"+CRLF+" @gmail.com"
    
    ddtstart = remind[0].datesir
    dtoff = datetime.timedelta(days = 1)
    dur = datetime.timedelta(hours = 1)
   
    dtend = ddtstart + dur
    dtstamp = datetime.datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dtstart = ddtstart.strftime("%Y%m%dT%H%M%SZ")
    dtend = dtend.strftime("%Y%m%dT%H%M%SZ")

    description = "Test Reminder"+CRLF
    attendee = ""
    for att in attendees:
        attendee += "ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-    PARTICIPANT;PARTSTAT=ACCEPTED;RSVP=TRUE"+CRLF+" ;CN="+att+";X-NUM-GUESTS=0:"+CRLF+" mailto:"+att+CRLF
    ical = "BEGIN:VCALENDAR"+CRLF+"PRODID:Reminder"+CRLF+"VERSION:2.0"+CRLF+"CALSCALE:GREGORIAN"+CRLF
    ical+="METHOD:REQUEST"+CRLF+"BEGIN:VEVENT"+CRLF+"DTSTART:"+dtstart+CRLF+"DTEND:"+dtend+CRLF+"DTSTAMP:"+dtstamp+CRLF+organizer+CRLF
    ical+= "UID:FIXMEUID"+dtstamp+CRLF
    ical+= attendee+"CREATED:"+dtstamp+CRLF+description+"LAST-MODIFIED:"+dtstamp+CRLF+"LOCATION:"+CRLF+"SEQUENCE:0"+CRLF+"STATUS:CONFIRMED"+CRLF
    ical+= "SUMMARY:Reminder for Test "+CRLF+"TRANSP:OPAQUE"+CRLF+"END:VEVENT"+CRLF+"END:VCALENDAR"+CRLF

    eml_body = "Reminder for test"
    
    msg = MIMEMultipart('mixed')
    msg['Reply-To']=fro
    msg['Date'] = formatdate(localtime=False)
    msg['Subject'] = "Test Reminder for  "+b
    msg['From'] = fro
    msg['To'] = ",".join(attendees)

    part_email = MIMEText(eml_body,"html")
    part_cal = MIMEText(ical,'calendar;method=REQUEST')

    msgAlternative = MIMEMultipart('alternative')
    msg.attach(msgAlternative)
    ical_atch = MIMEBase('application/ics',' ;name="%s"'%("invite.ics"))
    ical_atch.set_payload(ical)
    encoders.encode_base64(ical_atch)
    ical_atch.add_header('Content-Disposition', 'attachment; filename="%s"'%("invite.ics"))

    eml_atch = MIMEText('', 'plain')
    encoders.encode_base64(eml_atch)
    eml_atch.add_header('Content-Transfer-Encoding', "")


    msgAlternative.attach(part_email)
    msgAlternative.attach(part_cal)

    mailServer = smtplib.SMTP('smtp.gmail.com', 587)
    mailServer.ehlo()
    mailServer.starttls()
    mailServer.ehlo()
    mailServer.login(login, password)
    mailServer.sendmail(fro, attendees, msg.as_string())
    mailServer.close()
    return True

@noida_stats_router.get("/download/downloadregisteredbutnotplaced/", response_description='xlsx')
async def rnotplaced(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
   
    hrow=0
    hcol=0
    row=1
    col=0
    
    sql1="SELECT branch,s.urn, full_name,email,ssc,hsc,ug,ug_percentage,pg,backlogs,sem1,sem2,sem3,sem4,sem5,sem6,sem7,sem8,current_backlogs,history_backlogs,no_of_x_grades,other_grades,ug_start_year,ug_end_year,ssc_board,ssc_start_year,ssc_end_year,hsc_board,hsc_start_year,hsc_end_year,entry_to_college,rank,gap_in_studies,dob,gender,category,native,parents_name,present_addr,permanent_addr,phone,secondary_phone,count(*) FROM students s join registrations r on s.urn=r.urn where s.urn not in (SELECT DISTINCT urn from placed) and r.cid in (SELECT cid from company where category!='other') and s.college_id = 3 group by s.urn"
    with engine.connect() as con:
        rs = con.execute(sql1)
        output = 'notplaced.xlsx'
        workbook = xlsxwriter.Workbook(output)
        format2 = workbook.add_format({'num_format': 'd-m-yyyy'})
       
        worksheet = workbook.add_worksheet()
        worksheet.set_column('AH:AH', None, format2)
        worksheet.set_column('A:AQ', 15)
        for i in rs:
            for j in i.keys():
                worksheet.write(hrow, hcol, j)
                hcol+=1
            break
                
        for i in rs:
            
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1     
            col = 0
            row += 1
    
    workbook.close()
    bg_tasks.add_task(os.remove, output)
    return FileResponse(path=output,filename=output, background=bg_tasks)


@noida_stats_router.get("/download/downloadstudenttable", response_description='xlsx')
async def student_table(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
   
    hrow=0
    hcol=0
    row=1
    col=0
    
    sql1="SELECT branch,s.urn, full_name,email,ssc,hsc,ug,ug_percentage,pg,backlogs,sem1,sem2,sem3,sem4,sem5,sem6,sem7,sem8,current_backlogs,history_backlogs,no_of_x_grades,other_grades,ug_start_year,ug_end_year,ssc_board,ssc_start_year,ssc_end_year,hsc_board,hsc_start_year,hsc_end_year,entry_to_college,rank,gap_in_studies,dob,gender,category,native,parents_name,present_addr,permanent_addr,phone,secondary_phone FROM students s where s.college_id=3"
    
   
    with engine.connect() as con:
        rs = con.execute(sql1)
        output = 'notplaced.xlsx'
        workbook = xlsxwriter.Workbook(output)
        format2 = workbook.add_format({'num_format': 'd-m-yyyy'})
       
        worksheet = workbook.add_worksheet()
        worksheet.set_column('AH:AH', None, format2)
        worksheet.set_column('A:AP', 15)
        for i in rs:
            for j in i.keys():
                worksheet.write(hrow, hcol, j)
                hcol+=1
            break
                
        for i in rs:
            
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1     
            col = 0
            row += 1
    
    workbook.close()
    bg_tasks.add_task(os.remove, output)
    return FileResponse(path=output,filename=output, background=bg_tasks)

@noida_stats_router.get("/download/placed_list/", response_description='xlsx')
async def placed_list(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    rows=1
    col=0
    branches=[]
    urns=[]
    
    output = 'placed_list.xlsx'
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet()
    
    with engine.connect() as con:
           worksheet.write(rows,col,"PLACED LIST")
           rows+=1
           sql2= """SELECT students.urn, students.full_name, students.branch FROM placed INNER JOIN students ON placed.urn = students.urn where students.college_id=3"""
           rp=con.execute((sql2))
           for row in rp:
               urns.append(str(row['urn']))
               sql3="""SELECT company.cname FROM placed INNER JOIN company ON company.cid = placed.cid WHERE placed.college_id= 3 and placed.urn ='{}'""".format(row['urn'])
               rr=con.execute((sql3))
               for j in row.values():
                   worksheet.write(rows, col, j)
                   col+=1
                
               for k in rr:
                   worksheet.write(rows, col, k['cname'])
                   col+=1
                           
               col = 0
               rows += 1
    workbook.close()
    bg_tasks.add_task(os.remove, output)

    
    return FileResponse(path=output,filename=output, background=bg_tasks)
    
@noida_stats_router.get("/download/placedBranchWise/", response_description='xlsx')
async def placedbranch(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    rows=1
    col=0
    branches=[]
    urns=[]
    
    output = 'placedbranchwise.xlsx'
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet()
    
    with engine.connect() as con:

        sql1 = 'select DISTINCT students.branch from placed INNER JOIN students on placed.urn=students.urn where students.college_id= 3 '

        rs = con.execute(sql1)
        for row in rs:
            branches.append(str(row['branch']))
        
        
        for i in branches:
           worksheet.write(rows,col,i)
           rows+=1
           sql2= """SELECT students.urn, students.full_name, students.branch FROM placed INNER JOIN students ON placed.urn = students.urn WHERE students.college_id= 3 and students.branch = '{}'""".format(i)
           rp=con.execute((sql2))
           for row in rp:
               urns.append(str(row['urn']))
               sql3="""SELECT company.cname FROM placed INNER JOIN company ON company.cid = placed.cid WHERE placed.college_id= 3 and placed.urn ='{}'""".format(row['urn'])
               rr=con.execute((sql3))
               for j in row.values():
                   worksheet.write(rows, col, j)
                   col+=1
                
               for k in rr:
                   worksheet.write(rows, col, k['cname'])
                   col+=1
                           
               col = 0
               rows += 1
    workbook.close()
    bg_tasks.add_task(os.remove, output)

    
    return FileResponse(path=output,filename=output, background=bg_tasks)
                      
                      

@noida_stats_router.get("/download/placedGenderwise/", response_description='xlsx')
async def placedgender(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    rows=1
    col=0
    branches=['male','female']
    urns=[]
    
    output = 'placedgenderwise.xlsx'
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet()
    
    with engine.connect() as con:    
        
        for i in branches:
           worksheet.write(rows,col,i)
           rows+=1
           sql2= """SELECT students.urn, students.full_name, students.branch FROM placed INNER JOIN students ON placed.urn = students.urn WHERE students.college_id= 3  and students.gender = '{}'""".format(i)
           rp=con.execute((sql2))
           for row in rp:
               urns.append(str(row['urn']))
               sql3="""SELECT company.cname FROM placed INNER JOIN company ON company.cid = placed.cid WHERE placed.college_id= 3 and placed.urn ='{}'""".format(row['urn'])
               rr=con.execute((sql3))
               for j in row.values():
                   worksheet.write(rows, col, j)
                   col+=1
                
               for k in rr:
                   worksheet.write(rows, col, k['cname'])
                   col+=1
                           
               col = 0
               rows += 1
    workbook.close()
    bg_tasks.add_task(os.remove, output)

    
    return FileResponse(path=output,filename=output, background=bg_tasks)
                      
@noida_stats_router.get("/download/placedCategoryWise/", response_description='xlsx')
async def category(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    rows=1
    col=0
    branches=[]
    urns=[]
    
    output = 'placedcategorywise.xlsx'
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet()
    
    with engine.connect() as con:

        sql1 = 'select DISTINCT students.category from placed INNER JOIN students on placed.urn=students.urn where students.college_id= 3'

        rs = con.execute(sql1)
        for row in rs:
            branches.append(str(row['category']))
        
        
        for i in branches:
           worksheet.write(rows,col,i)
           rows+=1
           sql2= """SELECT students.urn, students.full_name, students.branch FROM placed INNER JOIN students ON placed.urn = students.urn WHERE students.college_id= 3 and students.category = '{}'""".format(i)
           rp=con.execute((sql2))
           for row in rp:
               urns.append(str(row['urn']))
               sql3="""SELECT company.cname FROM placed INNER JOIN company ON company.cid = placed.cid WHERE placed.college_id = 3 and placed.urn ='{}'""".format(row['urn'])
               rr=con.execute((sql3))
               for j in row.values():
                   worksheet.write(rows, col, j)
                   col+=1
                
               for k in rr:
                   worksheet.write(rows, col, k['cname'])
                   col+=1
                           
               col = 0
               rows += 1
    workbook.close()
    bg_tasks.add_task(os.remove, output)

    
    return FileResponse(path=output,filename=output, background=bg_tasks)
                      
@noida_stats_router.get("/download/companyregperstudent/", response_description='xlsx')
async def companyregperstudent(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    hrow=0
    hcol=0
    rows=1
    col=0
    headers=["urn", "Name", "Branch", "E-mail", "SSC", "HSC", "Sem-1", "Sem-2", "Sem-3", "Sem-4", "Sem-5", "Sem-6", "Sem-7", "Sem-8", "UG", "UG Percentage", "PG", "Backlogs", "Current Backlogs", "Backlog History", "Number of X grades", "Other Grades", "UG Start Year", "UG End Year", "SSC Board", "SSC Start Year", "SSC End Year", "HSC Board", "HSC Start Year", "HSC End Year", "Method of entry to College", "Rank in entrance test", "Gap in Studies", "DOB", "Gender", "Category", "Native", "Parent's Name", "Present Address", "Permanent Address", "Phone", "Secondary Phone", "Companies registered to"]
    urns=[]
    output = 'companyregperstudent.xlsx'
    workbook = xlsxwriter.Workbook(output)
    format2 = workbook.add_format({'num_format': 'd-m-yyyy'})   
    worksheet = workbook.add_worksheet()
    worksheet.set_column('AH:AH', None, format2)
    fmt = workbook.add_format({'bold': True})
    worksheet.set_row(0, None, fmt)
    for i in headers:
        worksheet.write(hrow,hcol,i)
        hcol+=1
    
    
    with engine.connect() as con:

        sql1 = 'SELECT DISTINCT registrations.urn FROM registrations where college_id= 3'

        rs = con.execute(sql1)
        for row in rs:
            urns.append(str(row['urn']))
            
        for i in urns:
            sql2= """SELECT DISTINCT students.urn, students.full_name, students.branch, students.email, students.ssc,students.hsc,students.sem1,students.sem2, students.sem3,students.sem4,students.sem5,students.sem6,students.sem7,students.sem8,students.ug,students.ug_percentage,students.pg,students.backlogs,students.current_backlogs,students.history_backlogs,students.no_of_x_grades,students.other_grades,students.ug_start_year ,students.ug_end_year, students.ssc_board,students.ssc_start_year,students.ssc_end_year,students.hsc_board,students.hsc_start_year,students.hsc_end_year,students.entry_to_college,students.rank,students.gap_in_studies,students.dob,students.gender,students.category,students.native,students.parents_name,students.present_addr,students.permanent_addr,students.phone,students.secondary_phone FROM students WHERE students.college_id= 3 and students.urn = '{}'""".format(i)
            sql3="""SELECT company.cname FROM registrations INNER JOIN company ON company.cid = registrations.cid WHERE registrations.college_id= 3 and registrations.urn = '{}'""".format(i)
            rp=con.execute(sql2)
            rt =con.execute(sql3)    
            
            for x in rp:
                for y in x.values():
                    worksheet.write(rows, col, y)
                    col+=1
                    
                    
                for k in rt:
                    worksheet.write(rows, col, k['cname'])
                    col+=1
                
                
                col=0
                rows+=1
            
           
        
        workbook.close()
    bg_tasks.add_task(os.remove, output)

    
    return FileResponse(path=output,filename=output, background=bg_tasks)
                   
        
@noida_stats_router.get("/download/downloadentireplacedlist", response_description='xlsx')
async def entireplaced(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
   
    hrow=0
    hcol=0
    row=1
    col=0
    
    sql1='''SELECT s.urn, s.full_name, s.email, c.cname, p.category_placed, s.branch, s.first_name, s.middle_name, s.last_name, s.current_backlogs, s.history_backlogs, s.other_grades, s.ssc_board,
    s.hsc_board , s.entry_to_college, s.gap_in_studies, s.gender,s.category, s.native, s.parents_name, s.phone, s.secondary_phone, s.hsc, s.ug, s.ug_percentage, s.pg, s.backlogs,s.sem1, s.sem2, s.sem3, s.sem4, s.sem5, s.sem6,
    s.sem7, s.sem8 ,s.ssc, s.present_addr, s.permanent_addr, s.no_of_x_grades, s.ug_start_year, s.ug_end_year, s.ssc_start_year, s.ssc_end_year, s.hsc_start_year, s.hsc_end_year, s.rank, s.dob, s.resume_link 
    FROM students s, placed p , company c where s.urn = p.urn and c.cid = p.cid and s.college_id = 3'''   
    
    
    headers=["URN/USN", "Full Name", "Email", "Company", "Category Placed","Branch", "First Name", "Middle Name", "Last Name","Current Backlogs","History Backlogs","Other Grades","SSC Board","HSC Board","Entry To College", 
            "Gap In Studies", "Gender", "Category", "Native", "Parents Name", "Phone ", "Secondary Phone", "HSC", "UG",
            "UG Percentage", "PG", "Backlogs", "SEM 1", "SEM 2", "SEM 3", "SEM 4" , "SEM 5" , "SEM 6" ,"SEM 7", "SEM 8", "SSC","Present Address", "Permanent Address", "Number Of X Grades", "UG Start Year", "UG End Year",
            "SSC Start Year", "SSC End Year", "HSC Start Year", "HSC End Year", "Rank","DOB", "Resume Link"]
    
   
    with engine.connect() as con:
        rs = con.execute(sql1)
        output = 'entireplaced.xlsx'
        workbook = xlsxwriter.Workbook(output)
        
       
        worksheet = workbook.add_worksheet()
        
        worksheet.set_column('A:AQ', 15)
        for i in headers:
            
            worksheet.write(hrow, hcol, i)
            hcol+=1
            
            
        
                
        for i in rs:
            
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1     
            col = 0
            row += 1
    
    workbook.close()
    bg_tasks.add_task(os.remove, output)
    return FileResponse(path=output,filename=output, background=bg_tasks)         
    
    
    
    
@noida_stats_router.get("/download/downloadnotregisteredyet", response_description='xlsx')
async def notregistered(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
   
    hrow=0
    hcol=0
    row=1
    col=0
    
    sql1="""SELECT * FROM students where urn not in (SELECT DISTINCT urn from registrations r join company c on r.cid=c.cid where c.category!='other' and r.college_id= 3 ) and verified=1 and college_id = 3""" 
    headers=["Name", "urn", "Branch", "Gender", "Email", "Phone","Tier1","Tier2","Internship","Dream"]
    
   
    with engine.connect() as con:
        rs = con.execute(sql1)
        output = 'entireplaced.xlsx'
        workbook = xlsxwriter.Workbook(output)
        
       
        worksheet = workbook.add_worksheet()
        
        worksheet.set_column('A:AQ', 15)
        for i in rs:
            for j in i.keys():
                worksheet.write(hrow, hcol, j)
                hcol+=1
            break
            
            
        
                
        for i in rs:
            
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1     
            col = 0
            row += 1
    
    workbook.close()
    bg_tasks.add_task(os.remove, output)
    return FileResponse(path=output,filename=output, background=bg_tasks)

    
@noida_stats_router.get("/download/regcid_list_short/{cid}", response_description='xlsx')
async def regcid_list_short(bg_tasks: BackgroundTasks,cid:int,reg:Request,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    row=1
    col=0
    
    with engine.connect() as con:
        sql = """select s.urn,email,branch,full_name,ssc,hsc,ug,ug_percentage,backlogs,current_backlogs,pg,dob,gender,phone
        from students s 
inner join registrations a on s.urn = a.urn
where s.college_id = 3 and a.cid ={};""".format(cid)

        rs = con.execute(sql)
        output = 'registredstudentsshort.xlsx'
        
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        bold = workbook.add_format({'bold': True,'bg_color':'#00C7CE'})
        format2=workbook.add_format({'num_format': 'dd/mm/yy','border': 2})
        format3 = workbook.add_format({'border': 2})
        format4= workbook.add_format({'border': 2})
        worksheet = workbook.add_worksheet()
        worksheet.set_row(0, 20, bold)
        
        worksheet.write(0,0,"University Roll Number")
        worksheet.write(0,1,"email")
        worksheet.write(0,2,"branch")
        worksheet.write(0,3,"full_name")
        worksheet.write(0,4,"10th_percent")
        worksheet.write(0,5,"12th_percent")
        worksheet.write(0,6,"ug_cgpa")
        worksheet.write(0,7,"ug_percentage")
        worksheet.write(0,8,"backlogs")
        worksheet.write(0,9,"current_backlogs")
        worksheet.write(0,10,"pg")
        worksheet.write(0,11,"date_of_birth")
        worksheet.write(0,12,"gender")
        worksheet.write(0,13,"phone_number")
        
        
                
        for i in rs:
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1     
            col = 0
            row += 1
        worksheet.set_column('A:K', 25, format3)
        worksheet.set_column('L:L', 25, format2)
        worksheet.set_column('M:N', 25, format3)
    workbook.close()
    bg_tasks.add_task(os.remove, output)
    return FileResponse(path=output,filename=output, background=bg_tasks)

        
    
    
@noida_stats_router.get("/download/regcid_list_detailed/{cid}", response_description='xlsx')
async def regcid_list_detailed(bg_tasks: BackgroundTasks,cid:int,reg:Request,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    row=1
    col=0
    
    with engine.connect() as con:
        sql = """select s.urn,email,branch,full_name,first_name,middle_name,last_name,ssc,hsc,ug,ug_percentage,pg,backlogs,sem1,sem2,sem3,sem4,sem5,sem6,sem7,sem8,current_backlogs,history_backlogs,no_of_x_grades,other_grades,ug_start_year,ug_end_year,ssc_board,ssc_start_year,ssc_end_year,hsc_board,hsc_start_year,hsc_end_year,entry_to_college,rank,gap_in_studies,dob,gender,category,native,parents_name,present_addr,permanent_addr,phone,secondary_phone,resume_link
        from students s 
inner join registrations a on s.urn = a.urn
where where s.college_id = 3 and  a.cid ={};""".format(cid)

        rs = con.execute(sql)
        output = 'registeredstudentsdetailed.xlsx'
        workbook = xlsxwriter.Workbook(output)
        bold = workbook.add_format({'bold': True,'bg_color':'#00C7CE'})
        format2=workbook.add_format({'num_format': 'dd/mm/yy','border': 2})
        format3 = workbook.add_format({'border': 2})
        format4= workbook.add_format({'border': 2})
        worksheet = workbook.add_worksheet()
        worksheet.set_row(0, 20, bold)
        
        worksheet.write(0,0,"University Roll Number")
        worksheet.write(0,1,"email")
        worksheet.write(0,2,"branch")
        worksheet.write(0,3,"full_name")
        worksheet.write(0,4,"first_name")
        worksheet.write(0,5,"middle_name")
        worksheet.write(0,6,"last_name")
        worksheet.write(0,7,"10th_percent")
        worksheet.write(0,8,"12th_percent")
        worksheet.write(0,9,"ug_cgpa")
        worksheet.write(0,10,"ug_percentage")
        worksheet.write(0,11,"pg")
        worksheet.write(0,12,"backlogs")
        worksheet.write(0,13,"sem1_cgpa")
        worksheet.write(0,14,"sem2_cgpa")
        worksheet.write(0,15,"sem3_cgpa")
        worksheet.write(0,16,"sem4_cgpa")
        worksheet.write(0,17,"sem5_cgpa")
        worksheet.write(0,18,"sem6_cgpa")
        worksheet.write(0,19,"sem7_cgpa")
        worksheet.write(0,20,"sem8_cgpa")
        worksheet.write(0,21,"current_backlogs")
        worksheet.write(0,22,"history_backlogs")
        worksheet.write(0,23,"no_of_x_grades")
        worksheet.write(0,24,"other_grades")
        worksheet.write(0,25,"ug_start_year")
        worksheet.write(0,26,"ug_end_year")
        worksheet.write(0,27,"10th_board")
        worksheet.write(0,28,"10th_board_start_year")
        worksheet.write(0,29,"10th_board_end_year")
        worksheet.write(0,30,"12th_board")
        worksheet.write(0,31,"12th_board_start_year")
        worksheet.write(0,32,"12th_board_end_year")
        worksheet.write(0,33,"entry_to_college")
        worksheet.write(0,34,"rank")
        worksheet.write(0,35,"gap_in_studies")
        worksheet.write(0,36,"date_of_birth")
        worksheet.write(0,37,"gender")
        worksheet.write(0,38,"category")
        worksheet.write(0,39,"native")
        worksheet.write(0,40,"parent's name")
        worksheet.write(0,41,"present_address")
        worksheet.write(0,42,"permanent_address")
        worksheet.write(0,43,"phone_number")
        worksheet.write(0,44,"secondary_phone_number")
        worksheet.write(0,45,"resume_link")
        
        
                
        for i in rs:
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1     
            col = 0
            row += 1
        worksheet.set_column('A:AJ', 25, format3)
        worksheet.set_column('AK:AK', 25, format2)
        worksheet.set_column('AL:AT', 25, format3)
    workbook.close()
    bg_tasks.add_task(os.remove, output)
    return FileResponse(path=output,filename=output, background=bg_tasks)

    
@noida_stats_router.get("/download/regcid_list_detailed_palo/", response_description='xlsx')
async def regcid_list_detailed_palo(bg_tasks: BackgroundTasks,reg:Request,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    row=1
    col=0
    
    with engine.connect() as con:
        sql = """select urn,email,branch,full_name,ug,dob,gender,phone
        from students 
where (branch='IT' or branch='ECE' or branch='CSE') and (ug>=7.50) and (current_backlogs='0') and college_id = 3;"""

        rs = con.execute(sql)
        output = 'registeredstudentsdetailed.xlsx'
        workbook = xlsxwriter.Workbook(output)
        bold = workbook.add_format({'bold': True,'bg_color':'#00C7CE'})
        format2=workbook.add_format({'num_format': 'dd/mm/yy','border': 2})
        format3 = workbook.add_format({'border': 2})
        format4= workbook.add_format({'border': 2})
        worksheet = workbook.add_worksheet()
        worksheet.set_row(0, 20, bold)
        
        worksheet.write(0,0,"University Roll Number")
        worksheet.write(0,1,"email")
        worksheet.write(0,2,"branch")
        worksheet.write(0,3,"full_name")
        worksheet.write(0,4,"ug_cgpa")
        worksheet.write(0,5,"date_of_birth")
        worksheet.write(0,6,"gender")
        worksheet.write(0,7,"phone_number")
        
        
                
        for i in rs:
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1     
            col = 0
            row += 1
        worksheet.set_column('A:AJ', 25, format3)
        worksheet.set_column('AK:AK', 25, format2)
        worksheet.set_column('AL:AS', 25, format3)
    workbook.close()
    bg_tasks.add_task(os.remove, output)
    return FileResponse(path=output,filename=output, background=bg_tasks)

# @noida_stats_router.post('/analytics/test_csv',status_code=200)
# async def register(company:str):

#     s = """SELECT * from students where email='{}'""".format(company)
   
#     SQL_for_file_output = "COPY ({0}) TO STDOUT WITH CSV HEADER".format(s)
#     path=company+'.csv'

#     t_path_n_file = r"C:\Users\HP\Downloads\Analytics-2023\Registration\{}".format(path)
    
#     with open(t_path_n_file, 'w') as f_output:
#         db_cursor.copy_expert(SQL_for_file_output, f_output)
# import itertools

# @noida_stats_router.get("/download/xlsxtest4", response_description='xlsx')
# async def data4(reg:Request,dba: Session = Depends(get_db)):
#     a=[]
#     b=[]
#     c=[]
#     hrow=0
#     hcol=0
#     row=1
#     col=0
    
#     query = dba.query(models.Company).all()
#     for user in query:
#         return {c.key: getattr(user, c.key())}
#    # return a
#     with engine.connect() as con:
#         rs = con.execute('SELECT * FROM company')
#         output = BytesIO()
#         workbook = xlsxwriter.Workbook(output)
#         worksheet = workbook.add_worksheet()
#         for i in rs:
#             for j in i.keys():
#                 worksheet.write(hrow, hcol, j)
#                 hcol+=1
#             break
                
#         for i in rs:
            
#             for j in i.values():
#                worksheet.write(row, col, j)
#                col+=1     
#             col = 0
#             row += 1
         
#     workbook.close()
#     output.seek(0)

#     headers = {
#         'Content-Disposition': 'attachment; filename="filename.xlsx"'
#     }
#     return StreamingResponse(output, headers=headers)

#]verified,]total,branchwise selects,]total companies,]companies so far,]offers,]student placed,female placed,male placed.

@noida_stats_router.get("/download/student/verified")
async def verified_count(reg:Request,db: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    output=db.query(User.branch).filter_by(verified=1).all()
    return len(output)

@noida_stats_router.get("/download/student/total")
async def student_count(reg:Request,db: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    output=db.query(User.branch).all()
    return len(output)

@noida_stats_router.get("/download/admin/total_company")
async def company_count(reg:Request,db: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    output=db.query(models.Company.cid).all()
    return len(output)

@noida_stats_router.get("/download/admin/companies_so_far")
async def companysofar_count(reg:Request,db: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    output=db.query(models.Company.cid).filter_by(status=3).all()
    return len(output)

@noida_stats_router.get("/download/admin/offers")
async def offers_count(reg:Request,db: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    output=db.query(models.Placed.pid).all()
    return len(output)
    
@noida_stats_router.get("/download/admin/placed_count")
async def placed_count(reg:Request,db: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    output=db.query(models.Placed.urn).distinct().all()
    return len(output)

import tempfile
import os  
# import psycopg2
import pandas as pd

# @noida_stats_router.get("/download/regcid_list1/{cid}",response_description='xlsx')
# async def regcid_list1(cid:int,reg:Request,dba: Session = Depends(get_db)):
#     db_conn = psycopg2.connect(host=t_host, port=t_port, dbname=t_dbname, user=t_user, password=t_pw)
#     cursor = db_conn.cursor()
#     sql = """select s.urn,email,branch,full_name,first_name,middle_name,last_name,ssc,hsc,ug,ug_percentage,pg,backlogs,sem1,sem2,sem3,sem4,sem5,sem6,sem7,sem8,current_backlogs,history_backlogs,no_of_x_grades,other_grades,ug_start_year,ug_end_year,ssc_board,ssc_start_year,ssc_end_year,hsc_board,hsc_start_year,hsc_end_year,entry_to_college,rank,gap_in_studies,dob,gender,category,native,parents_name,present_addr,permanent_addr,phone,secondary_phone
#         from students s 
# inner join registrations a on s.urn = a.urn
# where a.cid ={};""".format(cid)
    
#     try:
#         cursor.execute(sql)
#     except (Exception, psycopg2.DatabaseError) as error:
#         print("Error: %s" % error)
#         cursor.close()
#         return 1
    
#     # Naturally we get a list of tupples
#     tupples = cursor.fetchall()
#     cursor.close()
    
#     # We just need to turn it into a pandas dataframe
#     df = pd.DataFrame(tupples)
    
    
    
#     output = io.BytesIO()
#     writer = pd.ExcelWriter(output, engine='xlsxwriter')
#     df.to_excel(writer, sheet_name='Sheet1')
#     writer.save()
#     output.seek(0)
    
#     response= StreamingResponse(output)
#     response.headers["Content-Disposition"] = "attachment; filename=export.xlsx"
#     return response
    # try:
    #     cursor.execute(sql)
    # except (Exception, psycopg2.DatabaseError) as error:
    #     print("Error: %s" % error)
    #     cursor.close()
    #     return 1
    
    # # Naturally we get a list of tupples
    # tupples = cursor.fetchall()
    # cursor.close()
    
    # # We just need to turn it into a pandas dataframe
    # df = pd.DataFrame(tupples)
    # df.columns=['email','urn','name','branch','full_name',	'first_name'	,'middle_name'	,'last_name',	'ssc',	'hsc',	'ug',	'ug_percentage',	'pg',	'backlogs',	'sem1',    'sem2',	'sem3',	'sem4',    'sem5',	'sem6',	'sem7',    'sem8',	'current_backlogs',	'history_backlogs',	'no_of_x_grades',	'other_grades',	'ug_start_year',	'ug_end_year',	'ssc_board',	'ssc_start_year',	'ssc_end_year',	'hsc_board',	'hsc_start_year',	'hsc_end_year',	'entry_to_college',	'rank',	'gap_in_studies',	'dob',	'gender',	'category',	'native',	'parents_name',	'present_addr',	'permanent_addr',	'phone'	,'secondary_phone',	'verified']
    # stream = io.StringIO()
    
    # df.to_csv(stream, index = False)
    
    # response = StreamingResponse(iter([stream.getvalue()]),
    #                         media_type="text/csv"
    #    )
    
    # response.headers["Content-Disposition"] = "attachment; filename=export.csv"

    # return response
    
from fastapi.responses import FileResponse
from starlette.background import BackgroundTasks

@noida_stats_router.get("/download/placedBranchWise/", response_description='xlsx')
async def studentbranch_list2(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    rows=1
    col=0
    branches=[]
    urns=[]
    
    output = 'export.xlsx'
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet()
    a=[]
    with engine.connect() as con:
        sql1 = 'select DISTINCT students.branch from placed_category INNER JOIN students on placed_category.urn=students.urn and students.college_id= 3'

        rs = con.execute(sql1)
        for row in rs:
            branches.append(str(row['branch']))    
        for i in branches:
           worksheet.write(rows,col,i)
           rows+=1
           sql2= """SELECT DISTINCT students.urn, students.full_name, students.branch FROM placed_category INNER JOIN students ON placed_category.urn = students.urn WHERE students.college_id= 3 and students.branch = '{}'""".format(i)
           rp=con.execute((sql2))
           
           for row in rp:
               urns.append(str(row['urn']))
               sql3="""SELECT company.cname FROM placed_category INNER JOIN company ON company.cid = placed_category.cid WHERE placed_category.college_id= 3 and  placed_category.urn ='{}'""".format(row['urn'])
               rr=con.execute((sql3))
             
               for j in row.values():
                   worksheet.write(rows, col, j)
                   col+=1
                
               for k in rr:
                   worksheet.write(rows, col, str(k['cname']))
                   col+=1        
               col = 0
               rows += 1
    workbook.close()
    bg_tasks.add_task(os.remove, output)

    return FileResponse(path=output,filename=output, background=bg_tasks)

# @noida_stats_router.get("/download/company_reglist/{cid}", response_description='xlsx')
# async def company_id(cid:int,bg_tasks: BackgroundTasks,dba: Session = Depends(get_db)):
#     row=1
#     col=0

#     with engine.connect() as con:

#         sql = """select s.urn,email,branch,full_name,first_name,middle_name,last_name,ssc,hsc,ug,ug_percentage,pg,backlogs,sem1,sem2,sem3,sem4,sem5,sem6,sem7,sem8,current_backlogs,history_backlogs,no_of_x_grades,other_grades,ug_start_year,ug_end_year,ssc_board,ssc_start_year,ssc_end_year,hsc_board,hsc_start_year,hsc_end_year,entry_to_college,rank,gap_in_studies,dob,gender,category,native,parents_name,present_addr,permanent_addr,phone,secondary_phone
#         from students s 
# inner join registrations a on s.urn = a.urn
# where a.cid ={};""".format(cid)
    
#         rs = con.execute(sql)
#         output = 'export.xlsx'
#         workbook = xlsxwriter.Workbook(output)
#         worksheet = workbook.add_worksheet()
        
                
#         for i in rs:
#             for j in i.values():
#                worksheet.write(row, col, j)
#                col+=1     
#             col = 0
#             row += 1
#     workbook.close()
#     bg_tasks.add_task(os.remove, output)

    
#     return FileResponse(path=output,filename=output, background=bg_tasks)
@noida_stats_router.get("/download/placedbycompany/", response_description='xlsx')
async def placed_list(bg_tasks: BackgroundTasks,cid:int,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    row=1
    col=0
    hrow=0
    hcol=0
    output = 'placedbycompany.xlsx'
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet()
    headers=['Branch', 'urn','Name','Gender','Phone','Email']
    for i in headers:
        worksheet.write(hrow,hcol,i)
        hcol+=1
    with engine.connect() as con:

        sql = """select DISTINCT students.branch,students.urn,students.full_name,students.gender,students.phone,students.email from placed INNER JOIN students on placed.urn=students.urn where placed.college_id = 3 and  placed.cid={}""".format(cid)

        rs = con.execute(sql)
        
                
        for i in rs:
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1     
            col = 0
            row += 1
    workbook.close()
    bg_tasks.add_task(os.remove, output)

    
    return FileResponse(path=output,filename=output, background=bg_tasks)
@noida_stats_router.get("/download/branch_list2/", response_description='xlsx')
async def branch_list2(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    row=1
    col=0
    branch_list = []
    for i in dba.query(models.Placed_category.branch).distinct():
        branch_list.append(i[0])
    student_details=[]
    for i in dba.query(models.User).filter(models.User.urn.in_(dba.query(models.Placed_category.urn).distinct())):
        student_details.append(i)
    cname_list=[]
    for i in student_details:
        cid_urn=dba.query(models.Placed.cid).filter(models.Placed.urn==i.urn).first()
        cname_urn=dba.query(models.Company.cname).filter(models.Company.cid==cid_urn[0]).first()
        cname_list.append(cname_urn[0])
    final_details_list=[]
    # # dba.query(models.Company.cname).filter(models.Company.cid.in_(dba.query(models.Placed.cid))):
    #     student_details.append(i)
    final_details_list.append(student_details)
    final_details_list.append(cname_list)
    return final_details_list

@noida_stats_router.get("/download/placedbycompany/", response_description='xlsx')
async def placed_list(bg_tasks: BackgroundTasks,cid:int,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    row=1
    col=0
    hrow=0
    hcol=0
    output = 'placedbycompany.xlsx'
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet()
    headers=['Branch', 'urn','Name','Gender','Phone','Email']
    for i in headers:
        worksheet.write(hrow,hcol,i)
        hcol+=1
    with engine.connect() as con:

        sql = """select DISTINCT students.branch,students.urn,students.full_name,students.gender,students.phone,students.email from placed INNER JOIN students on placed.urn=students.urn where college_id = 3 and placed.cid={}""".format(cid)

        rs = con.execute(sql)
        
                
        for i in rs:
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1     
            col = 0
            row += 1
    workbook.close()
    bg_tasks.add_task(os.remove, output)

    
    return FileResponse(path=output,filename=output, background=bg_tasks)

@noida_stats_router.get("/download/eligibilitysheet/", response_description='xlsx')
async def eligibility(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    rows=1
    col=0
    hrow=0
    hcol=0
    headers=['Company','CSE','IT','CSBS','ME','MCA','ISE','ECE','EI','MBA','CE','EE','EEE','MECH','IP','CV','CTM','PST','BT','ENV','BCA','MSC','MCA',
                  'Computer_Engineering','Software_Engineering','Data_Science','Biomedical_Signal_Processing','Networking_Internet_Engineering',
'Industrial_Electronics','Polymer_Science','Energy_Systems_Management','Mechanical_Engineering_PG','Automotive_Electronics','Industrial_Structures','Infrastructure_Engineering_Management','Environmental_PG','Health_Science_Water_Treatment','Material_Science','MBA_Finance','MBA_HR','MBA_Marketing',
'Corporate_Finance','Digital_Marketing','Retail_Marketing','Total Placed','Total Registered','SSC Cutoff','HSC Cutoff','UG Cutoff','PG Cutoff','Package']
    
    branches=['CSE','CSBS','ISE','IT','ECE','EI','EEE','MECH','EE','MBA','ME','CE','MCA','IP','CV','CTM','PST','BT','ENV','BCA','MSC','MCA',
                  'Computer_Engineering','Software_Engineering','Data_Science','Biomedical_Signal_Processing','Networking_Internet_Engineering',
'Industrial_Electronics','Polymer_Science','Energy_Systems_Management','Mechanical_Engineering_PG','Automotive_Electronics','Industrial_Structures','Infrastructure_Engineering_Management','Environmental_PG','Health_Science_Water_Treatment','Material_Science','MBA_Finance','MBA_HR','MBA_Marketing',
'Corporate_Finance','Digital_Marketing','Retail_Marketing']
    urns=[]
    
    output = 'eligibility.xlsx'
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet()
    fmt = workbook.add_format({'bold': True})
    worksheet.set_row(0, None, fmt)
    worksheet.set_column('A:AS', 20)
    for i in headers:
        worksheet.write(hrow,hcol,i)
        hcol+=1
    with engine.connect() as con:

        sql1 = """SELECT cid, cname, branch, ssc, hsc, ug, pg, package FROM company"""

        rs = con.execute(sql1)
        for row in rs:
            comp_name=row['cname']
            comp_id=row['cid']
            worksheet.write(rows,col,comp_name)
            col+=1
            temp=row['branch']
            branch=temp.split(',')
            for a in branches:
                if a in branch:
                    sql2="""SELECT COUNT(DISTINCT placed.urn) AS "c" FROM placed WHERE placed.urn IN (SELECT urn FROM students WHERE students.branch = '{}') and college_id = 3 AND cid ={}""".format(a,comp_id)
                    ra = con.execute(sql2)
                    for j in ra:
                        placed_count=str(j['c'])
                    sql3="""SELECT COUNT(DISTINCT registrations.urn) AS "c" FROM registrations WHERE registrations.urn IN (SELECT urn FROM students WHERE students.branch = '{}') and college_id = 3 AND cid ={}""".format(a,comp_id)
                    rb=con.execute(sql3)
                    for k in rb:
                         reg_count=str(k['c'])
                        
                   
                    worksheet.write_string(rows,col,'Yes({}/{})'.format(reg_count,placed_count))
                    col+=1
                else:
                    worksheet.write(rows,col,'No')
                    col+=1
            sql4="""SELECT COUNT(DISTINCT placed.urn) AS "c" FROM placed WHERE  placed.college_id = 3 and placed.cid ={}""".format(comp_id)
            sql5="""SELECT COUNT(DISTINCT registrations.urn) AS "c" FROM registrations WHERE registrations.college_id = 3 and registrations.cid ={}""".format(comp_id)
            rc = con.execute(sql4)
            for j in rc:
                    totplaced=str(j['c'])
            rd = con.execute(sql5)
            for j in rd:
                    totreg=str(j['c'])
                
            worksheet.write_string(rows,col,totplaced)
            col+=1
            worksheet.write_string(rows,col,totreg)
            col+=1
            worksheet.write_number(rows,col,row['ssc'])
            col+=1
            worksheet.write_number(rows,col,row['hsc'])
            col+=1
            worksheet.write_number(rows,col,row['ug'])
            col+=1
            worksheet.write_number(rows,col,row['pg'])
            col+=1
            worksheet.write_number(rows,col,row['package'])
            col+=1
                        
            col=0
                
            rows+=1
                    
        
        
    workbook.close()
    bg_tasks.add_task(os.remove, output)

    
    return FileResponse(path=output,filename=output, background=bg_tasks)
                      

    
@noida_stats_router.get("/download/offerperstudent/{cid}", response_description='xlsx')
async def offer(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    rows=1
    col=0
    hrow=0
    hcol=0
    urns=[]
    headers=["University Roll Number", "Name", "Branch", "E-mail", "SSC", "HSC", "Sem-1", "Sem-2", "Sem-3", "Sem-4", "Sem-5", "Sem-6", "Sem-7", "Sem-8", "UG", "UG Percentage", "PG", "Backlogs", "Current Backlogs", "Backlog History", "Number of X grades", "Other Grades", "UG Start Year", "UG End Year", "SSC Board", "SSC Start Year", "SSC End Year", "HSC Board", "HSC Start Year", "HSC End Year", "Method of entry to College", "Rank in entrance test", "Gap in Studies", "DOB", "Gender", "Category", "Native", "Parent's Name", "Present Address", "Permanent Address", "Phone", "Secondary Phone", "Number of offers","Companies Placed In"]
    output = 'offer.xlsx'
   
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet()
    format2 = workbook.add_format({'num_format': 'd-m-yyyy'})
    fmt = workbook.add_format({'bold': True})
    
    worksheet.set_column('AH:AH', None, format2)
    worksheet.set_column('A:AS', 20)
    
    worksheet.set_row(0, None, fmt)
    for i in headers:
        worksheet.write(hrow,hcol,i)
        hcol+=1
    with engine.connect() as con:
        sql="""SELECT DISTINCT placed.urn FROM placed where placed.college_id = 3 """
        rs = con.execute(sql)
        for row in rs:
            urns.append(str(row['urn']))
        
        for i in urns:
            sql1 = """select s.urn,full_name,branch,email,ssc,hsc,sem1,sem2,sem3,sem4,sem5,sem6,sem7,sem8,ug,ug_percentage,pg,backlogs,current_backlogs,history_backlogs,no_of_x_grades,other_grades,ug_start_year,ug_end_year,ssc_board,ssc_start_year,ssc_end_year,hsc_board,hsc_start_year,hsc_end_year,entry_to_college,rank,gap_in_studies,dob,gender,category,native,parents_name,present_addr,permanent_addr,phone,secondary_phone
                from students s where s.college_id = 3 and s.urn='{}'""".format(i)
            rp=con.execute(sql1)
            for x in rp:
                for y in x.values():
                    worksheet.write(rows, col, y)
                    col+=1
                    
            sql2="""SELECT count(*) FROM placed WHERE placed.college_id = 3 and placed.urn = '{}'""".format(i)
            rs=con.execute(sql2)
            for x in rs:
                compcount=str(x[0])
            worksheet.write(rows,col,compcount)
            col+=1
            
            sql3="""SELECT company.cname FROM placed INNER JOIN company ON company.cid = placed.cid WHERE placed.college_id = 3 and placed.urn ='{}'""".format(i)
            rr=con.execute(sql3)
            for k in rr:
                    worksheet.write(rows, col, k['cname'])
                    col+=1
                
                
            col=0
            rows+=1
            
           
        
        workbook.close()
    bg_tasks.add_task(os.remove, output)
    return FileResponse(path=output,filename=output, background=bg_tasks)       
           
                
@noida_stats_router.get("/download/tier1detailed", response_description='xlsx')
async def tier1detail(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    row=1
    col=0
   
    with engine.connect() as con:
        sql = """select s.urn,email,branch,full_name,first_name,middle_name,last_name,ssc,hsc,ug,ug_percentage,pg,backlogs,sem1,sem2,sem3,sem4,sem5,sem6,sem7,sem8,current_backlogs,history_backlogs,no_of_x_grades,other_grades,ug_start_year,ug_end_year,ssc_board,ssc_start_year,ssc_end_year,hsc_board,hsc_start_year,hsc_end_year,entry_to_college,rank,gap_in_studies,dob,gender,category,native,parents_name,present_addr,permanent_addr,phone,secondary_phone
        from students s 
inner join placed a on s.urn = a.urn
where s.college_id = 3 and a.category_placed='tier1';"""
        
        rs = con.execute(sql)
        output = 'tier1detail.xlsx'
        workbook = xlsxwriter.Workbook(output)
        bold = workbook.add_format({'bold': True,'bg_color':'#00C7CE'})
        format2=workbook.add_format({'num_format': 'dd/mm/yy','border': 2})
        format3 = workbook.add_format({'border': 2})
        format4= workbook.add_format({'border': 2})
        worksheet = workbook.add_worksheet()
        worksheet.set_row(0, 20, bold)
        
        worksheet.write(0,0,"University Roll Number")
        worksheet.write(0,1,"email")
        worksheet.write(0,2,"branch")
        worksheet.write(0,3,"full_name")
        worksheet.write(0,4,"first_name")
        worksheet.write(0,5,"middle_name")
        worksheet.write(0,6,"last_name")
        worksheet.write(0,7,"10th_percent")
        worksheet.write(0,8,"12th_percent")
        worksheet.write(0,9,"ug_cgpa")
        worksheet.write(0,10,"ug_percentage")
        worksheet.write(0,11,"pg")
        worksheet.write(0,12,"backlogs")
        worksheet.write(0,13,"sem1_cgpa")
        worksheet.write(0,14,"sem2_cgpa")
        worksheet.write(0,15,"sem3_cgpa")
        worksheet.write(0,16,"sem4_cgpa")
        worksheet.write(0,17,"sem5_cgpa")
        worksheet.write(0,18,"sem6_cgpa")
        worksheet.write(0,19,"sem7_cgpa")
        worksheet.write(0,20,"sem8_cgpa")
        worksheet.write(0,21,"current_backlogs")
        worksheet.write(0,22,"history_backlogs")
        worksheet.write(0,23,"no_of_x_grades")
        worksheet.write(0,24,"other_grades")
        worksheet.write(0,25,"ug_start_year")
        worksheet.write(0,26,"ug_end_year")
        worksheet.write(0,27,"10th_board")
        worksheet.write(0,28,"10th_board_start_year")
        worksheet.write(0,29,"10th_board_end_year")
        worksheet.write(0,30,"12th_board")
        worksheet.write(0,31,"12th_board_start_year")
        worksheet.write(0,32,"12th_board_end_year")
        worksheet.write(0,33,"entry_to_college")
        worksheet.write(0,34,"rank")
        worksheet.write(0,35,"gap_in_studies")
        worksheet.write(0,36,"date_of_birth")
        worksheet.write(0,37,"gender")
        worksheet.write(0,38,"category")
        worksheet.write(0,39,"native")
        worksheet.write(0,40,"parent's name")
        worksheet.write(0,41,"present_address")
        worksheet.write(0,42,"permanent_address")
        worksheet.write(0,43,"phone_number")
        worksheet.write(0,44,"secondary_phone_number")
        worksheet.write(0,45,"Company Placed In")        
        
            
                
        for i in rs:
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1
            
            sql3="""SELECT company.cname FROM placed INNER JOIN company ON company.cid = placed.cid WHERE placed.college_id = 3 and placed.urn ='{}' AND placed.category_placed='tier1'""".format(i['urn'])   
            rr=con.execute(sql3)
            for k in rr:
                    worksheet.write(row, col, k['cname'])
                    col+=1     
            col = 0
            row += 1
        worksheet.set_column('A:AJ', 25, format3)
        worksheet.set_column('AK:AK', 25, format2)
        worksheet.set_column('AL:AU', 25, format3)
    workbook.close()
    bg_tasks.add_task(os.remove, output)
    return FileResponse(path=output,filename=output, background=bg_tasks)      



@noida_stats_router.get("/download/tier1short", response_description='xlsx')
async def tier1short(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    row=1
    col=0
    
    with engine.connect() as con:
        sql = """select s.urn,email,branch,full_name,ssc,hsc,ug,ug_percentage,backlogs,current_backlogs,pg,dob,gender,phone
        from students s 
inner join placed a on s.urn = a.urn
where a.category_placed='tier1';"""
        
        rs = con.execute(sql)
        output = 'tier1short.xlsx'
        workbook = xlsxwriter.Workbook(output)
        bold = workbook.add_format({'bold': True,'bg_color':'#00C7CE'})
        format2=workbook.add_format({'num_format': 'dd/mm/yy','border': 2})
        format3 = workbook.add_format({'border': 2})
       
        worksheet = workbook.add_worksheet()
        worksheet.set_row(0, 20, bold)
        
        worksheet.write(0,0,"University Roll Number")
        worksheet.write(0,1,"email")
        worksheet.write(0,2,"branch")
        worksheet.write(0,3,"full_name")
        worksheet.write(0,4,"10th_percent")
        worksheet.write(0,5,"12th_percent")
        worksheet.write(0,6,"ug_cgpa")
        worksheet.write(0,7,"ug_percentage")
        worksheet.write(0,8,"backlogs")
        worksheet.write(0,9,"current_backlogs")
        worksheet.write(0,10,"pg")
        worksheet.write(0,11,"date_of_birth")
        worksheet.write(0,12,"gender")
        worksheet.write(0,13,"phone_number")
        worksheet.write(0,14,'Company Placed In')
        
        
                
        for i in rs:
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1
            
            sql3="""SELECT company.cname FROM placed INNER JOIN company ON company.cid = placed.cid WHERE placed.urn ='{}' AND placed.category_placed='tier1'""".format(i['urn'])   
            rr=con.execute(sql3)
            for k in rr:
                    worksheet.write(row, col, k['cname'])
                    col+=1     
            col = 0
            row += 1
        worksheet.set_column('A:K', 25, format3)
        worksheet.set_column('L:L', 25, format2)
        worksheet.set_column('M:Q', 25, format3)
    workbook.close()
    bg_tasks.add_task(os.remove, output)
    return FileResponse(path=output,filename=output, background=bg_tasks)



@noida_stats_router.get("/download/tier2detailed", response_description='xlsx')
async def tier2detail(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    row=1
    col=0
   
    with engine.connect() as con:
        sql = """select s.urn,email,branch,full_name,first_name,middle_name,last_name,ssc,hsc,ug,ug_percentage,pg,backlogs,sem1,sem2,sem3,sem4,sem5,sem6,sem7,sem8,current_backlogs,history_backlogs,no_of_x_grades,other_grades,ug_start_year,ug_end_year,ssc_board,ssc_start_year,ssc_end_year,hsc_board,hsc_start_year,hsc_end_year,entry_to_college,rank,gap_in_studies,dob,gender,category,native,parents_name,present_addr,permanent_addr,phone,secondary_phone
        from students s 
inner join placed a on s.urn = a.urn
where a.category_placed='tier2';"""
        
        rs = con.execute(sql)
        output = 'tier2detail.xlsx'
        workbook = xlsxwriter.Workbook(output)
        bold = workbook.add_format({'bold': True,'bg_color':'#00C7CE'})
        format2=workbook.add_format({'num_format': 'dd/mm/yy','border': 2})
        format3 = workbook.add_format({'border': 2})
        format4= workbook.add_format({'border': 2})
        worksheet = workbook.add_worksheet()
        worksheet.set_row(0, 20, bold)
        
        worksheet.write(0,0,"University Roll Number")
        worksheet.write(0,1,"email")
        worksheet.write(0,2,"branch")
        worksheet.write(0,3,"full_name")
        worksheet.write(0,4,"first_name")
        worksheet.write(0,5,"middle_name")
        worksheet.write(0,6,"last_name")
        worksheet.write(0,7,"10th_percent")
        worksheet.write(0,8,"12th_percent")
        worksheet.write(0,9,"ug_cgpa")
        worksheet.write(0,10,"ug_percentage")
        worksheet.write(0,11,"pg")
        worksheet.write(0,12,"backlogs")
        worksheet.write(0,13,"sem1_cgpa")
        worksheet.write(0,14,"sem2_cgpa")
        worksheet.write(0,15,"sem3_cgpa")
        worksheet.write(0,16,"sem4_cgpa")
        worksheet.write(0,17,"sem5_cgpa")
        worksheet.write(0,18,"sem6_cgpa")
        worksheet.write(0,19,"sem7_cgpa")
        worksheet.write(0,20,"sem8_cgpa")
        worksheet.write(0,21,"current_backlogs")
        worksheet.write(0,22,"history_backlogs")
        worksheet.write(0,23,"no_of_x_grades")
        worksheet.write(0,24,"other_grades")
        worksheet.write(0,25,"ug_start_year")
        worksheet.write(0,26,"ug_end_year")
        worksheet.write(0,27,"10th_board")
        worksheet.write(0,28,"10th_board_start_year")
        worksheet.write(0,29,"10th_board_end_year")
        worksheet.write(0,30,"12th_board")
        worksheet.write(0,31,"12th_board_start_year")
        worksheet.write(0,32,"12th_board_end_year")
        worksheet.write(0,33,"entry_to_college")
        worksheet.write(0,34,"rank")
        worksheet.write(0,35,"gap_in_studies")
        worksheet.write(0,36,"date_of_birth")
        worksheet.write(0,37,"gender")
        worksheet.write(0,38,"category")
        worksheet.write(0,39,"native")
        worksheet.write(0,40,"parent's name")
        worksheet.write(0,41,"present_address")
        worksheet.write(0,42,"permanent_address")
        worksheet.write(0,43,"phone_number")
        worksheet.write(0,44,"secondary_phone_number")
        worksheet.write(0,45,"Company Placed In")        
        
            
                
        for i in rs:
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1
            
            sql3="""SELECT company.cname FROM placed INNER JOIN company ON company.cid = placed.cid WHERE placed.urn ='{}' AND placed.category_placed='tier2'""".format(i['urn'])   
            rr=con.execute(sql3)
            for k in rr:
                    worksheet.write(row, col, k['cname'])
                    col+=1     
            col = 0
            row += 1
        worksheet.set_column('A:AJ', 25, format3)
        worksheet.set_column('AK:AK', 25, format2)
        worksheet.set_column('AL:AU', 25, format3)
    workbook.close()
    bg_tasks.add_task(os.remove, output)
    return FileResponse(path=output,filename=output, background=bg_tasks)      



@noida_stats_router.get("/download/tier2short", response_description='xlsx')
async def tier2short(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    row=1
    col=0
    
    with engine.connect() as con:
        sql = """select s.urn,email,branch,full_name,ssc,hsc,ug,ug_percentage,backlogs,current_backlogs,pg,dob,gender,phone
        from students s 
inner join placed a on s.urn = a.urn
where a.category_placed='tier2';"""
        
        rs = con.execute(sql)
        output = 'tier2short.xlsx'
        workbook = xlsxwriter.Workbook(output)
        bold = workbook.add_format({'bold': True,'bg_color':'#00C7CE'})
        format2=workbook.add_format({'num_format': 'dd/mm/yy','border': 2})
        format3 = workbook.add_format({'border': 2})
       
        worksheet = workbook.add_worksheet()
        worksheet.set_row(0, 20, bold)
        
        worksheet.write(0,0,"University Roll Number")
        worksheet.write(0,1,"email")
        worksheet.write(0,2,"branch")
        worksheet.write(0,3,"full_name")
        worksheet.write(0,4,"10th_percent")
        worksheet.write(0,5,"12th_percent")
        worksheet.write(0,6,"ug_cgpa")
        worksheet.write(0,7,"ug_percentage")
        worksheet.write(0,8,"backlogs")
        worksheet.write(0,9,"current_backlogs")
        worksheet.write(0,10,"pg")
        worksheet.write(0,11,"date_of_birth")
        worksheet.write(0,12,"gender")
        worksheet.write(0,13,"phone_number")
        worksheet.write(0,14,'Company Placed In')
        
        
                
        for i in rs:
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1
            
            sql3="""SELECT company.cname FROM placed INNER JOIN company ON company.cid = placed.cid WHERE placed.urn ='{}' AND placed.category_placed='tier2'""".format(i['urn'])   
            rr=con.execute(sql3)
            for k in rr:
                    worksheet.write(row, col, k['cname'])
                    col+=1     
            col = 0
            row += 1
        worksheet.set_column('A:K', 25, format3)
        worksheet.set_column('L:L', 25, format2)
        worksheet.set_column('M:Q', 25, format3)
    workbook.close()
    bg_tasks.add_task(os.remove, output)
    return FileResponse(path=output,filename=output, background=bg_tasks)

@noida_stats_router.get("/download/dreamdetailed", response_description='xlsx')
async def dreamdetail(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    row=1
    col=0
   
    with engine.connect() as con:
        sql = """select s.urn,email,branch,full_name,first_name,middle_name,last_name,ssc,hsc,ug,ug_percentage,pg,backlogs,sem1,sem2,sem3,sem4,sem5,sem6,sem7,sem8,current_backlogs,history_backlogs,no_of_x_grades,other_grades,ug_start_year,ug_end_year,ssc_board,ssc_start_year,ssc_end_year,hsc_board,hsc_start_year,hsc_end_year,entry_to_college,rank,gap_in_studies,dob,gender,category,native,parents_name,present_addr,permanent_addr,phone,secondary_phone
        from students s 
inner join placed a on s.urn = a.urn
where a.category_placed='dream';"""
        
        rs = con.execute(sql)
        output = 'dreamdetail.xlsx'
        workbook = xlsxwriter.Workbook(output)
        bold = workbook.add_format({'bold': True,'bg_color':'#00C7CE'})
        format2=workbook.add_format({'num_format': 'dd/mm/yy','border': 2})
        format3 = workbook.add_format({'border': 2})
        format4= workbook.add_format({'border': 2})
        worksheet = workbook.add_worksheet()
        worksheet.set_row(0, 20, bold)
        
        worksheet.write(0,0,"University Roll Number")
        worksheet.write(0,1,"email")
        worksheet.write(0,2,"branch")
        worksheet.write(0,3,"full_name")
        worksheet.write(0,4,"first_name")
        worksheet.write(0,5,"middle_name")
        worksheet.write(0,6,"last_name")
        worksheet.write(0,7,"10th_percent")
        worksheet.write(0,8,"12th_percent")
        worksheet.write(0,9,"ug_cgpa")
        worksheet.write(0,10,"ug_percentage")
        worksheet.write(0,11,"pg")
        worksheet.write(0,12,"backlogs")
        worksheet.write(0,13,"sem1_cgpa")
        worksheet.write(0,14,"sem2_cgpa")
        worksheet.write(0,15,"sem3_cgpa")
        worksheet.write(0,16,"sem4_cgpa")
        worksheet.write(0,17,"sem5_cgpa")
        worksheet.write(0,18,"sem6_cgpa")
        worksheet.write(0,19,"sem7_cgpa")
        worksheet.write(0,20,"sem8_cgpa")
        worksheet.write(0,21,"current_backlogs")
        worksheet.write(0,22,"history_backlogs")
        worksheet.write(0,23,"no_of_x_grades")
        worksheet.write(0,24,"other_grades")
        worksheet.write(0,25,"ug_start_year")
        worksheet.write(0,26,"ug_end_year")
        worksheet.write(0,27,"10th_board")
        worksheet.write(0,28,"10th_board_start_year")
        worksheet.write(0,29,"10th_board_end_year")
        worksheet.write(0,30,"12th_board")
        worksheet.write(0,31,"12th_board_start_year")
        worksheet.write(0,32,"12th_board_end_year")
        worksheet.write(0,33,"entry_to_college")
        worksheet.write(0,34,"rank")
        worksheet.write(0,35,"gap_in_studies")
        worksheet.write(0,36,"date_of_birth")
        worksheet.write(0,37,"gender")
        worksheet.write(0,38,"category")
        worksheet.write(0,39,"native")
        worksheet.write(0,40,"parent's name")
        worksheet.write(0,41,"present_address")
        worksheet.write(0,42,"permanent_address")
        worksheet.write(0,43,"phone_number")
        worksheet.write(0,44,"secondary_phone_number")
        worksheet.write(0,45,"Company Placed In")        
        
            
                
        for i in rs:
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1
            
            sql3="""SELECT company.cname FROM placed INNER JOIN company ON company.cid = placed.cid WHERE placed.urn ='{}' AND placed.category_placed='dream'""".format(i['urn'])   
            rr=con.execute(sql3)
            for k in rr:
                    worksheet.write(row, col, k['cname'])
                    col+=1     
            col = 0
            row += 1
        worksheet.set_column('A:AJ', 25, format3)
        worksheet.set_column('AK:AK', 25, format2)
        worksheet.set_column('AL:AU', 25, format3)
    workbook.close()
    bg_tasks.add_task(os.remove, output)
    return FileResponse(path=output,filename=output, background=bg_tasks)      



@noida_stats_router.get("/download/dreamshort", response_description='xlsx')
async def dreamshort(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    row=1
    col=0
    
    with engine.connect() as con:
        sql = """select s.urn,email,branch,full_name,ssc,hsc,ug,ug_percentage,backlogs,current_backlogs,pg,dob,gender,phone
        from students s 
inner join placed a on s.urn = a.urn
where a.category_placed='dream';"""
        
        rs = con.execute(sql)
        output = 'tier1short.xlsx'
        workbook = xlsxwriter.Workbook(output)
        bold = workbook.add_format({'bold': True,'bg_color':'#00C7CE'})
        format2=workbook.add_format({'num_format': 'dd/mm/yy','border': 2})
        format3 = workbook.add_format({'border': 2})
       
        worksheet = workbook.add_worksheet()
        worksheet.set_row(0, 20, bold)
        
        worksheet.write(0,0,"University Roll Number")
        worksheet.write(0,1,"email")
        worksheet.write(0,2,"branch")
        worksheet.write(0,3,"full_name")
        worksheet.write(0,4,"10th_percent")
        worksheet.write(0,5,"12th_percent")
        worksheet.write(0,6,"ug_cgpa")
        worksheet.write(0,7,"ug_percentage")
        worksheet.write(0,8,"backlogs")
        worksheet.write(0,9,"current_backlogs")
        worksheet.write(0,10,"pg")
        worksheet.write(0,11,"date_of_birth")
        worksheet.write(0,12,"gender")
        worksheet.write(0,13,"phone_number")
        worksheet.write(0,14,'Company Placed In')
        
        
                
        for i in rs:
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1
            
            sql3="""SELECT company.cname FROM placed INNER JOIN company ON company.cid = placed.cid WHERE placed.urn ='{}' AND placed.category_placed='dream'""".format(i['urn'])   
            rr=con.execute(sql3)
            for k in rr:
                    worksheet.write(row, col, k['cname'])
                    col+=1     
            col = 0
            row += 1
        worksheet.set_column('A:K', 25, format3)
        worksheet.set_column('L:L', 25, format2)
        worksheet.set_column('M:Q', 25, format3)
    workbook.close()
    bg_tasks.add_task(os.remove, output)
    return FileResponse(path=output,filename=output, background=bg_tasks)

@noida_stats_router.get("/download/coredetailed", response_description='xlsx')
async def coredetail(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    row=1
    col=0
   
    with engine.connect() as con:
        sql = """select s.urn,email,branch,full_name,first_name,middle_name,last_name,ssc,hsc,ug,ug_percentage,pg,backlogs,sem1,sem2,sem3,sem4,sem5,sem6,sem7,sem8,current_backlogs,history_backlogs,no_of_x_grades,other_grades,ug_start_year,ug_end_year,ssc_board,ssc_start_year,ssc_end_year,hsc_board,hsc_start_year,hsc_end_year,entry_to_college,rank,gap_in_studies,dob,gender,category,native,parents_name,present_addr,permanent_addr,phone,secondary_phone
        from students s 
inner join placed a on s.urn = a.urn
where a.category_placed='core';"""
        
        rs = con.execute(sql)
        output = 'coredetailed.xlsx'
        workbook = xlsxwriter.Workbook(output)
        bold = workbook.add_format({'bold': True,'bg_color':'#00C7CE'})
        format2=workbook.add_format({'num_format': 'dd/mm/yy','border': 2})
        format3 = workbook.add_format({'border': 2})
        format4= workbook.add_format({'border': 2})
        worksheet = workbook.add_worksheet()
        worksheet.set_row(0, 20, bold)
        
        worksheet.write(0,0,"University Roll Number")
        worksheet.write(0,1,"email")
        worksheet.write(0,2,"branch")
        worksheet.write(0,3,"full_name")
        worksheet.write(0,4,"first_name")
        worksheet.write(0,5,"middle_name")
        worksheet.write(0,6,"last_name")
        worksheet.write(0,7,"10th_percent")
        worksheet.write(0,8,"12th_percent")
        worksheet.write(0,9,"ug_cgpa")
        worksheet.write(0,10,"ug_percentage")
        worksheet.write(0,11,"pg")
        worksheet.write(0,12,"backlogs")
        worksheet.write(0,13,"sem1_cgpa")
        worksheet.write(0,14,"sem2_cgpa")
        worksheet.write(0,15,"sem3_cgpa")
        worksheet.write(0,16,"sem4_cgpa")
        worksheet.write(0,17,"sem5_cgpa")
        worksheet.write(0,18,"sem6_cgpa")
        worksheet.write(0,19,"sem7_cgpa")
        worksheet.write(0,20,"sem8_cgpa")
        worksheet.write(0,21,"current_backlogs")
        worksheet.write(0,22,"history_backlogs")
        worksheet.write(0,23,"no_of_x_grades")
        worksheet.write(0,24,"other_grades")
        worksheet.write(0,25,"ug_start_year")
        worksheet.write(0,26,"ug_end_year")
        worksheet.write(0,27,"10th_board")
        worksheet.write(0,28,"10th_board_start_year")
        worksheet.write(0,29,"10th_board_end_year")
        worksheet.write(0,30,"12th_board")
        worksheet.write(0,31,"12th_board_start_year")
        worksheet.write(0,32,"12th_board_end_year")
        worksheet.write(0,33,"entry_to_college")
        worksheet.write(0,34,"rank")
        worksheet.write(0,35,"gap_in_studies")
        worksheet.write(0,36,"date_of_birth")
        worksheet.write(0,37,"gender")
        worksheet.write(0,38,"category")
        worksheet.write(0,39,"native")
        worksheet.write(0,40,"parent's name")
        worksheet.write(0,41,"present_address")
        worksheet.write(0,42,"permanent_address")
        worksheet.write(0,43,"phone_number")
        worksheet.write(0,44,"secondary_phone_number")
        worksheet.write(0,45,"Company Placed In")        
        
            
                
        for i in rs:
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1
            
            sql3="""SELECT company.cname FROM placed INNER JOIN company ON company.cid = placed.cid WHERE placed.urn ='{}' AND placed.category_placed='core'""".format(i['urn'])   
            rr=con.execute(sql3)
            for k in rr:
                    worksheet.write(row, col, k['cname'])
                    col+=1     
            col = 0
            row += 1
        worksheet.set_column('A:AJ', 25, format3)
        worksheet.set_column('AK:AK', 25, format2)
        worksheet.set_column('AL:AU', 25, format3)
    workbook.close()
    bg_tasks.add_task(os.remove, output)
    return FileResponse(path=output,filename=output, background=bg_tasks)      



@noida_stats_router.get("/download/coreshort", response_description='xlsx')
async def coreshort(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    row=1
    col=0
    
    with engine.connect() as con:
        sql = """select s.urn,email,branch,full_name,ssc,hsc,ug,ug_percentage,backlogs,current_backlogs,pg,dob,gender,phone
        from students s 
inner join placed a on s.urn = a.urn
where a.category_placed='core';"""
        
        rs = con.execute(sql)
        output = 'coreshort.xlsx'
        workbook = xlsxwriter.Workbook(output)
        bold = workbook.add_format({'bold': True,'bg_color':'#00C7CE'})
        format2=workbook.add_format({'num_format': 'dd/mm/yy','border': 2})
        format3 = workbook.add_format({'border': 2})
       
        worksheet = workbook.add_worksheet()
        worksheet.set_row(0, 20, bold)
        
        worksheet.write(0,0,"University Roll Number")
        worksheet.write(0,1,"email")
        worksheet.write(0,2,"branch")
        worksheet.write(0,3,"full_name")
        worksheet.write(0,4,"10th_percent")
        worksheet.write(0,5,"12th_percent")
        worksheet.write(0,6,"ug_cgpa")
        worksheet.write(0,7,"ug_percentage")
        worksheet.write(0,8,"backlogs")
        worksheet.write(0,9,"current_backlogs")
        worksheet.write(0,10,"pg")
        worksheet.write(0,11,"date_of_birth")
        worksheet.write(0,12,"gender")
        worksheet.write(0,13,"phone_number")
        worksheet.write(0,14,'Company Placed In')
        
        
                
        for i in rs:
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1
            
            sql3="""SELECT company.cname FROM placed INNER JOIN company ON company.cid = placed.cid WHERE placed.urn ='{}' AND placed.category_placed='core'""".format(i['urn'])   
            rr=con.execute(sql3)
            for k in rr:
                    worksheet.write(row, col, k['cname'])
                    col+=1     
            col = 0
            row += 1
        worksheet.set_column('A:K', 25, format3)
        worksheet.set_column('L:L', 25, format2)
        worksheet.set_column('M:Q', 25, format3)
    workbook.close()
    bg_tasks.add_task(os.remove, output)
    return FileResponse(path=output,filename=output, background=bg_tasks)

@noida_stats_router.get("/download/specialdetailed", response_description='xlsx')
async def specialdetail(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    row=1
    col=0
   
    with engine.connect() as con:
        sql = """select s.urn,email,branch,full_name,first_name,middle_name,last_name,ssc,hsc,ug,ug_percentage,pg,backlogs,sem1,sem2,sem3,sem4,sem5,sem6,sem7,sem8,current_backlogs,history_backlogs,no_of_x_grades,other_grades,ug_start_year,ug_end_year,ssc_board,ssc_start_year,ssc_end_year,hsc_board,hsc_start_year,hsc_end_year,entry_to_college,rank,gap_in_studies,dob,gender,category,native,parents_name,present_addr,permanent_addr,phone,secondary_phone
        from students s 
inner join placed a on s.urn = a.urn
where a.category_placed='special';"""
        
        rs = con.execute(sql)
        output = 'specialdetail.xlsx'
        workbook = xlsxwriter.Workbook(output)
        bold = workbook.add_format({'bold': True,'bg_color':'#00C7CE'})
        format2=workbook.add_format({'num_format': 'dd/mm/yy','border': 2})
        format3 = workbook.add_format({'border': 2})
        format4= workbook.add_format({'border': 2})
        worksheet = workbook.add_worksheet()
        worksheet.set_row(0, 20, bold)
        
        worksheet.write(0,0,"University Roll Number")
        worksheet.write(0,1,"email")
        worksheet.write(0,2,"branch")
        worksheet.write(0,3,"full_name")
        worksheet.write(0,4,"first_name")
        worksheet.write(0,5,"middle_name")
        worksheet.write(0,6,"last_name")
        worksheet.write(0,7,"10th_percent")
        worksheet.write(0,8,"12th_percent")
        worksheet.write(0,9,"ug_cgpa")
        worksheet.write(0,10,"ug_percentage")
        worksheet.write(0,11,"pg")
        worksheet.write(0,12,"backlogs")
        worksheet.write(0,13,"sem1_cgpa")
        worksheet.write(0,14,"sem2_cgpa")
        worksheet.write(0,15,"sem3_cgpa")
        worksheet.write(0,16,"sem4_cgpa")
        worksheet.write(0,17,"sem5_cgpa")
        worksheet.write(0,18,"sem6_cgpa")
        worksheet.write(0,19,"sem7_cgpa")
        worksheet.write(0,20,"sem8_cgpa")
        worksheet.write(0,21,"current_backlogs")
        worksheet.write(0,22,"history_backlogs")
        worksheet.write(0,23,"no_of_x_grades")
        worksheet.write(0,24,"other_grades")
        worksheet.write(0,25,"ug_start_year")
        worksheet.write(0,26,"ug_end_year")
        worksheet.write(0,27,"10th_board")
        worksheet.write(0,28,"10th_board_start_year")
        worksheet.write(0,29,"10th_board_end_year")
        worksheet.write(0,30,"12th_board")
        worksheet.write(0,31,"12th_board_start_year")
        worksheet.write(0,32,"12th_board_end_year")
        worksheet.write(0,33,"entry_to_college")
        worksheet.write(0,34,"rank")
        worksheet.write(0,35,"gap_in_studies")
        worksheet.write(0,36,"date_of_birth")
        worksheet.write(0,37,"gender")
        worksheet.write(0,38,"category")
        worksheet.write(0,39,"native")
        worksheet.write(0,40,"parent's name")
        worksheet.write(0,41,"present_address")
        worksheet.write(0,42,"permanent_address")
        worksheet.write(0,43,"phone_number")
        worksheet.write(0,44,"secondary_phone_number")
        worksheet.write(0,45,"Company Placed In")        
        
            
                
        for i in rs:
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1
            
            sql3="""SELECT company.cname FROM placed INNER JOIN company ON company.cid = placed.cid WHERE placed.urn ='{}' AND placed.category_placed='special'""".format(i['urn'])   
            rr=con.execute(sql3)
            for k in rr:
                    worksheet.write(row, col, k['cname'])
                    col+=1     
            col = 0
            row += 1
        worksheet.set_column('A:AJ', 25, format3)
        worksheet.set_column('AK:AK', 25, format2)
        worksheet.set_column('AL:AU', 25, format3)
    workbook.close()
    bg_tasks.add_task(os.remove, output)
    return FileResponse(path=output,filename=output, background=bg_tasks)      



@noida_stats_router.get("/download/specialshort", response_description='xlsx')
async def specialshort(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    row=1
    col=0
    
    with engine.connect() as con:
        sql = """select s.urn,email,branch,full_name,ssc,hsc,ug,ug_percentage,backlogs,current_backlogs,pg,dob,gender,phone
        from students s 
inner join placed a on s.urn = a.urn
where a.category_placed='special';"""
        
        rs = con.execute(sql)
        output = 'specialshort.xlsx'
        workbook = xlsxwriter.Workbook(output)
        bold = workbook.add_format({'bold': True,'bg_color':'#00C7CE'})
        format2=workbook.add_format({'num_format': 'dd/mm/yy','border': 2})
        format3 = workbook.add_format({'border': 2})
       
        worksheet = workbook.add_worksheet()
        worksheet.set_row(0, 20, bold)
        
        worksheet.write(0,0,"University Roll Number")
        worksheet.write(0,1,"email")
        worksheet.write(0,2,"branch")
        worksheet.write(0,3,"full_name")
        worksheet.write(0,4,"10th_percent")
        worksheet.write(0,5,"12th_percent")
        worksheet.write(0,6,"ug_cgpa")
        worksheet.write(0,7,"ug_percentage")
        worksheet.write(0,8,"backlogs")
        worksheet.write(0,9,"current_backlogs")
        worksheet.write(0,10,"pg")
        worksheet.write(0,11,"date_of_birth")
        worksheet.write(0,12,"gender")
        worksheet.write(0,13,"phone_number")
        worksheet.write(0,14,'Company Placed In')
        
        
                
        for i in rs:
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1
            
            sql3="""SELECT company.cname FROM placed INNER JOIN company ON company.cid = placed.cid WHERE placed.urn ='{}' AND placed.category_placed='special'""".format(i['urn'])   
            rr=con.execute(sql3)
            for k in rr:
                    worksheet.write(row, col, k['cname'])
                    col+=1     
            col = 0
            row += 1
        worksheet.set_column('A:K', 25, format3)
        worksheet.set_column('L:L', 25, format2)
        worksheet.set_column('M:Q', 25, format3)
    workbook.close()
    bg_tasks.add_task(os.remove, output)
    return FileResponse(path=output,filename=output, background=bg_tasks)


@noida_stats_router.get("/download/interndetailed", response_description='xlsx')
async def interndetail(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    row=1
    col=0
   
    with engine.connect() as con:
        sql = """select s.urn,email,branch,full_name,first_name,middle_name,last_name,ssc,hsc,ug,ug_percentage,pg,backlogs,sem1,sem2,sem3,sem4,sem5,sem6,sem7,sem8,current_backlogs,history_backlogs,no_of_x_grades,other_grades,ug_start_year,ug_end_year,ssc_board,ssc_start_year,ssc_end_year,hsc_board,hsc_start_year,hsc_end_year,entry_to_college,rank,gap_in_studies,dob,gender,category,native,parents_name,present_addr,permanent_addr,phone,secondary_phone
        from students s 
inner join placed a on s.urn = a.urn
where a.category_placed='internship';"""
        
        rs = con.execute(sql)
        output = 'interndetail.xlsx'
        workbook = xlsxwriter.Workbook(output)
        bold = workbook.add_format({'bold': True,'bg_color':'#00C7CE'})
        format2=workbook.add_format({'num_format': 'dd/mm/yy','border': 2})
        format3 = workbook.add_format({'border': 2})
        format4= workbook.add_format({'border': 2})
        worksheet = workbook.add_worksheet()
        worksheet.set_row(0, 20, bold)
        
        worksheet.write(0,0,"University Roll Number")
        worksheet.write(0,1,"email")
        worksheet.write(0,2,"branch")
        worksheet.write(0,3,"full_name")
        worksheet.write(0,4,"first_name")
        worksheet.write(0,5,"middle_name")
        worksheet.write(0,6,"last_name")
        worksheet.write(0,7,"10th_percent")
        worksheet.write(0,8,"12th_percent")
        worksheet.write(0,9,"ug_cgpa")
        worksheet.write(0,10,"ug_percentage")
        worksheet.write(0,11,"pg")
        worksheet.write(0,12,"backlogs")
        worksheet.write(0,13,"sem1_cgpa")
        worksheet.write(0,14,"sem2_cgpa")
        worksheet.write(0,15,"sem3_cgpa")
        worksheet.write(0,16,"sem4_cgpa")
        worksheet.write(0,17,"sem5_cgpa")
        worksheet.write(0,18,"sem6_cgpa")
        worksheet.write(0,19,"sem7_cgpa")
        worksheet.write(0,20,"sem8_cgpa")
        worksheet.write(0,21,"current_backlogs")
        worksheet.write(0,22,"history_backlogs")
        worksheet.write(0,23,"no_of_x_grades")
        worksheet.write(0,24,"other_grades")
        worksheet.write(0,25,"ug_start_year")
        worksheet.write(0,26,"ug_end_year")
        worksheet.write(0,27,"10th_board")
        worksheet.write(0,28,"10th_board_start_year")
        worksheet.write(0,29,"10th_board_end_year")
        worksheet.write(0,30,"12th_board")
        worksheet.write(0,31,"12th_board_start_year")
        worksheet.write(0,32,"12th_board_end_year")
        worksheet.write(0,33,"entry_to_college")
        worksheet.write(0,34,"rank")
        worksheet.write(0,35,"gap_in_studies")
        worksheet.write(0,36,"date_of_birth")
        worksheet.write(0,37,"gender")
        worksheet.write(0,38,"category")
        worksheet.write(0,39,"native")
        worksheet.write(0,40,"parent's name")
        worksheet.write(0,41,"present_address")
        worksheet.write(0,42,"permanent_address")
        worksheet.write(0,43,"phone_number")
        worksheet.write(0,44,"secondary_phone_number")
        worksheet.write(0,45,"Company Placed In")        
        
            
                
        for i in rs:
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1
            
            sql3="""SELECT company.cname FROM placed INNER JOIN company ON company.cid = placed.cid WHERE placed.urn ='{}' AND placed.category_placed='internship'""".format(i['urn'])   
            rr=con.execute(sql3)
            for k in rr:
                    worksheet.write(row, col, k['cname'])
                    col+=1     
            col = 0
            row += 1
        worksheet.set_column('A:AJ', 25, format3)
        worksheet.set_column('AK:AK', 25, format2)
        worksheet.set_column('AL:AU', 25, format3)
    workbook.close()
    bg_tasks.add_task(os.remove, output)
    return FileResponse(path=output,filename=output, background=bg_tasks)      

be=['CSE','CSBS','ISE','ECE','EI','EEE','EE','MECH','IP','CV','CTM','PST','BT','ENV','BCA','MSC','MCA',
             'Computer_Engineering','Software_Engineering','Data_Science','Biomedical_Signal_Processing','Networking_Internet_Engineering',
'Industrial_Electronics','Polymer_Science','Energy_Systems_Management','Mechanical_Engineering_PG','Automotive_Electronics','Industrial_Structures','Infrastructure_Engineering_Management','Environmental_PG','Health_Science_Water_Treatment','Material_Science','MBA_Finance','MBA_HR','MBA_Marketing',
'Corporate_Finance','Digital_Marketing','Retail_Marketing']

@noida_stats_router.get("/download/internshort", response_description='xlsx')
async def specialshort(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    row=1
    col=0
    
    with engine.connect() as con:
        sql = """select s.urn,email,branch,full_name,ssc,hsc,ug,ug_percentage,backlogs,current_backlogs,pg,dob,gender,phone
        from students s 
inner join placed a on s.urn = a.urn
where a.category_placed='internship';"""
        
        rs = con.execute(sql)
        output = 'internshort.xlsx'
        workbook = xlsxwriter.Workbook(output)
        bold = workbook.add_format({'bold': True,'bg_color':'#00C7CE'})
        format2=workbook.add_format({'num_format': 'dd/mm/yy','border': 2})
        format3 = workbook.add_format({'border': 2})
       
        worksheet = workbook.add_worksheet()
        worksheet.set_row(0, 20, bold)
        
        worksheet.write(0,0,"University Roll Number")
        worksheet.write(0,1,"email")
        worksheet.write(0,2,"branch")
        worksheet.write(0,3,"full_name")
        worksheet.write(0,4,"10th_percent")
        worksheet.write(0,5,"12th_percent")
        worksheet.write(0,6,"ug_cgpa")
        worksheet.write(0,7,"ug_percentage")
        worksheet.write(0,8,"backlogs")
        worksheet.write(0,9,"current_backlogs")
        worksheet.write(0,10,"pg")
        worksheet.write(0,11,"date_of_birth")
        worksheet.write(0,12,"gender")
        worksheet.write(0,13,"phone_number")
        worksheet.write(0,14,'Company Placed In')
        
        
                
        for i in rs:
            for j in i.values():
               worksheet.write(row, col, j)
               col+=1
            
            sql3="""SELECT company.cname FROM placed INNER JOIN company ON company.cid = placed.cid WHERE placed.urn ='{}' AND placed.category_placed='internship'""".format(i['urn'])   
            rr=con.execute(sql3)
            for k in rr:
                    worksheet.write(row, col, k['cname'])
                    col+=1     
            col = 0
            row += 1
        worksheet.set_column('A:K', 25, format3)
        worksheet.set_column('L:L', 25, format2)
        worksheet.set_column('M:Q', 25, format3)
    workbook.close()
    bg_tasks.add_task(os.remove, output)
    return FileResponse(path=output,filename=output, background=bg_tasks)

circuit=['CSE','IT','ECE','EEE','EE']

@noida_stats_router.get("/graph1")
def graph1(a:bool=Depends(get_current_admin)):
    with engine.connect() as con:
        sql = """select count(*) as count,branch from students group by branch;"""
        rs = con.execute(sql)
        branch=[]
        count=[]
        for i in rs:
            if i['branch'] in be:
                branch.append(i['branch'])
                count.append(i['count'])
        ans=[]
        ans.append(branch)
        ans.append(count)
        return ans
@noida_stats_router.get("/placed_branchwise_graph")
def placed_branchwise_graph(a:bool=Depends(get_current_admin)):
    with engine.connect() as con:
        sql="""select count(*) as count,branch from students s inner join placed a on s.urn = a.urn where college_id = 3 group by branch;"""    
        sql1 = """select count(*) as count,branch from students where college_id = 3 group by branch;"""
        rs1 = con.execute(sql1)
        branch1=[]
        count1=[]
        for i in rs1:
            if i['branch'] in be:
                branch1.append(i['branch'])
                count1.append(i['count'])
        ans=[]
        ans.append(branch1)
        ans.append(count1)
        
        rs = con.execute(sql)
        branch=[]
        count=[]
        for i in rs:
            if i['branch'] in be:
                branch.append(i['branch'])
                count.append(i['count'])
        
        ans.append(branch)
        ans.append(count)
        return ans
@noida_stats_router.get("/placed_branchwise_stats")
def placed_branchwise_stats(a:bool=Depends(get_current_admin)):
    with engine.connect() as con:
        sql="""select count(*) as count,branch from students s inner join placed a on s.urn = a.urn group by branch;"""    
        rs = con.execute(sql)
        branchwise={"branch":[],"count":[]}
        
        for i in rs:
            branchwise["branch"].append(i['branch'])
            branchwise["count"].append(i['count'])
        return branchwise
@noida_stats_router.get("/placed_branchwise_placed_category_wise_graph")
def placed_branchwise_placed_tier2_graph(a:bool=Depends(get_current_admin)):
    with engine.connect() as con:
        sql="""select count(*) as count,branch from students s inner join placed a on s.urn = a.urn where s.college_id = 3 and (a.category_placed = 'tier2') group by branch;"""  
        rs = con.execute(sql)
        branch=[]
        count=[]
        for i in rs:
            if i['branch'] in be:
                branch.append(i['branch'])
                count.append(i['count'])
        ans=[]  
        ans.append(branch)
        ans.append(count)
        return ans
@noida_stats_router.get("/placed_branchwise_placedratio_graph")
def placed_branchwise_placedratio_graph(a:bool=Depends(get_current_admin)):
    with engine.connect() as con:
        sql="""select count(*) as count,branch from students s inner join placed a on s.urn = a.urn where s.college_id = 3 group by branch;"""
        branchwise_count="""select count(*) as count,branch from students where college_id = 3 group by branch;"""
        rs = con.execute(sql)
        rs2=con.execute(branchwise_count)
        branch={"branch":[],"count":[]}
        branch1={"branch":[],"count":[]}
        for i in rs:
            if i['branch'] in be:
                branch['branch'].append(i['branch'])
                branch['count'].append(i['count'])
        for i in rs2:
            if i['branch'] in be:
                branch1['branch'].append(i['branch'])
                branch1['count'].append(i['count'])
        placed_ratio={"branch":[],"ratio":[]}
       
        for i in branch["branch"]:
            if i in branch1["branch"]:
                placed_ratio["branch"].append(i)
                placed_ratio["ratio"].append(floor((branch["count"][branch["branch"].index(i)]/branch1["count"][branch1["branch"].index(i)])*100))
                
        return placed_ratio
@noida_stats_router.get("/genderwise_placed_ratio")
def genderwise_placed_pie_chart(a:bool=Depends(get_current_admin)):
    with engine.connect() as con:
        sql="""select s.gender from students s inner join placed a on s.urn = a.urn where s.college_id = 3;"""
        rs = con.execute(sql)
        gender={"male":[],"female":[]}
        count_male=0
        count_female=0
        aa=[]
        for i in rs:
            i=i[0]
            if i == 'M' or i == 'Male' or i == 'male' or i== 'MALE':
                count_male+=1
            else:
                count_female+=1
        total=count_female+count_male
        gender["male"]=(count_male/total)*100
        gender["female"]=(count_female/total)*100
        a=[]
        a.append(gender["male"])
        a.append(gender["female"])
        return a
    
@noida_stats_router.get("/tierwise_placed_count")
def tierwisewise_placed_bar_chart(a:bool=Depends(get_current_admin)):
    with engine.connect() as con:
        sql="""select count(*) as count,category_placed from placed where college_id = 3 group by category_placed;"""
        rs = con.execute(sql)
        tier=[]
        count=[]
        for i in rs:
            tier.append(i['category_placed'])
            count.append(i['count'])
        ans=[]
        ans.append(tier)
        ans.append(count)
        return ans

@noida_stats_router.get("/average_package")
def package_analysis(a:bool=Depends(get_current_admin)):
    with engine.connect() as con:
        sql="""select c.package from company c inner join placed a on c.cid = a.cid where a.college_id = 3 ;"""
        rs = con.execute(sql)
        package=[]
        dummy_package=[]
        for i in rs:
            if i['package'] != 99 and i['package'] > 0:
                package.append(i['package'])
        dummy_package=package
        avg_package=sum(package)/len(package)
        dummy_package=sorted(dummy_package)
        median_package=dummy_package[(len(dummy_package)//2)]
        highest_package=max(package)
        lowest_package=min(package)
        ans=[]
        ans.append(avg_package)
        ans.append(median_package)
        ans.append(highest_package)
        ans.append(lowest_package)
        return ans
@noida_stats_router.get("/studentside_success_rate_per_student/{urn}")
def studentside_student_registrations_vs_placement_count_ratio(urn:str,a:bool=Depends(get_current_admin)):
    with engine.connect() as con:
        urn=urn.upper()
        #sql query to find number of companies a student has registered in and number of companies he has been placed in
        sql="""select count(*) as count from registrations where urn='"""+urn+"""';"""
        rs = con.execute(sql)
        sql1="""select count(*) as count from placed_category where urn='"""+urn+"""';"""
        rs1 = con.execute(sql1)
        for i in rs:
            registered_count=i['count']
        for i in rs1:
            placed_count=i['count']
        if registered_count != 0:
            ratio=ceil((placed_count/registered_count)*100)
        else:
            ratio=0
        return ratio

@noida_stats_router.get("/success_rate_per_student", response_description='xlsx')
async def student_registrations_vs_placement_count_ratio(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    rows=0
    col=0

    output = 'ratio_student.xlsx'
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet()

    with engine.connect() as con:
        urn_list=[]
        #sql query to store details of all urn from student table in a list
        sql0="""select urn from students where college_id = 3;"""
        rs = con.execute(sql0)
        worksheet.write(0,0,"urn")
        worksheet.write(0,1,"Name")
        worksheet.write(0,2,"Branch")
        worksheet.write(0,3,"Registration Count")
        worksheet.write(0,4,"Offer Count")
        worksheet.write(0,5,"Success(in percent)")
        
        rows=rows+1
            
        for i in rs:
            urn_list.append(i['urn'])
        for urn in urn_list:
            #sql query to find number of companies a student has registered in and number of companies he has been placed in
            sql="""select count(*) as count from registrations where urn='"""+urn+"""';"""
            rs = con.execute(sql)
            sql1="""select count(*) as count from placed_category where urn='"""+urn+"""';"""
            rs1 = con.execute(sql1)
            for i in rs:
                registered_count=i['count']
            for i in rs1:
                placed_count=i['count']
            if registered_count != 0:
                ratio=ceil((placed_count/registered_count)*100)
            else:
                ratio=0
            
            #plot a pie chart to show the placed count to registered count ratio
            worksheet.write(rows,col,urn)
            #get name,branch of student and write it in excel
            sql2="""select full_name,branch from students where urn='"""+urn+"""';"""
            rs2 = con.execute(sql2)
            for i in rs2:
                worksheet.write(rows,col+1,i['full_name'])
                worksheet.write(rows,col+2,i['branch'])
            worksheet.write(rows,col+3,registered_count)
            worksheet.write(rows,col+4,placed_count)
                    
            worksheet.write(rows,col+5,ratio)
            rows+=1
    
    workbook.close()
    bg_tasks.add_task(os.remove, output)

    return FileResponse(path=output,filename=output, background=bg_tasks)

@noida_stats_router.get("/download/branchwisecompany/", response_description='xlsx')
async def placedbranch_company(bg_tasks: BackgroundTasks,dba: Session = Depends(get_db),a:bool=Depends(get_current_admin)):
    rows=0
    col=0
    branches=['CSE','ECE','EEE','ME','CE','IT','EE','MCA','MBA']
    urns=[]
    
    output = 'branchwisecompany.xlsx'
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet()
    
    with engine.connect() as con:
        for i in branches:
            worksheet.write(rows,col,i)
            rows=rows+1
            #sort the query result by company name
        
            sql2= """select company.cname from company  where company.eligible_college_ids like '%3%'and  company.branch like '%%{}%%'""".format(i)
            rp=con.execute((sql2))
            #print branch name in row
            #print company names in columns after branch
            
            for j in rp:
                worksheet.write(rows,col,j['cname'])
                col=col+1
            col=0
            rows=rows+2
        
    workbook.close()
    bg_tasks.add_task(os.remove, output)

    
    return FileResponse(path=output,filename=output, background=bg_tasks)

@noida_stats_router.get("/branchwise_average_package")
def branchwise_package_analysis(a:bool=Depends(get_current_admin)):
    with engine.connect() as con:
        sql="""select c.package,s.branch from company c inner join placed a on c.cid = a.cid inner join students s on a.urn = s.urn where s.college_id = 3 ;"""
        rs = con.execute(sql)
        branchwise={"branch":[[]],"package":[]}
        dummy_package=[]
        k=0
        # l=0
        package=dict()
        for i in rs:
            if i['branch'] in be:
                if i['branch'] in package:
                    if i['package'] != 99 and i['package'] > 0:
                        package[i['branch']].append(i['package'])
                else:
                    if i['package'] != 99 and i['package'] > 0:
                        package[i['branch']]=[]
                        package[i['branch']].append(i['package'])
        a={"branch":[],"avg":[],"median":[],"highest":[],"lowest":[]}
        for i in package:
            a["branch"].append(i)
            sum=0
            for j in range(len(package[i])):
                sum+=package[i][j]
            a["avg"].append(sum/len(package[i]))
            a["highest"].append(max(package[i]))
            a["lowest"].append(min(package[i]))
            a["median"].append(sorted(package[i])[len(package[i])//2])
        
        return a
# while branch:
     
# 		$placedBranches[] = $branch['branch'];
	


#     with engine.connect() as con:

#         sql = """select s.urn,email,branch,full_name,first_name,middle_name,last_name,ssc,hsc,ug,ug_percentage,pg,backlogs,sem1,sem2,sem3,sem4,sem5,sem6,sem7,sem8,current_backlogs,history_backlogs,no_of_x_grades,other_grades,ug_start_year,ug_end_year,ssc_board,ssc_start_year,ssc_end_year,hsc_board,hsc_start_year,hsc_end_year,entry_to_college,rank,gap_in_studies,dob,gender,category,native,parents_name,present_addr,permanent_addr,phone,secondary_phone
#         from students s 
# inner join registrations a on s.urn = a.urn
# where a.cid ={};""".format(cid)
    
#         rs = con.execute(sql)
#         output = 'export.xlsx'
#         workbook = xlsxwriter.Workbook(output)
#         worksheet = workbook.add_worksheet()
        
                
#         for i in rs:
#             for j in i.values():
#                worksheet.write(row, col, j)
#                col+=1     
#             col = 0
#             row += 1
#     workbook.close()
#     bg_tasks.add_task(os.remove, output)

    
#     return FileResponse(path=output,filename=output, background=bg_tasks)

# @noida_stats_router.get("/download/xlsxtest/{cid}", response_description='xlsx')
# async def data(cid:int,reg:Request,dba: Session = Depends(get_db)):
#     a=[]
#     b=[]
#     c=[]
#     hrow=0
#     hcol=0
#     row=1
#     col=0
    
#     with engine.connect() as con:
        
#         sql = """select * from students"""

#         rs = con.execute(sql)
#         output = BytesIO()
#         workbook = xlsxwriter.Workbook(output)
#         worksheet = workbook.add_worksheet()
#         for i in rs:
#             for j in i.keys():
#                 worksheet.write(hrow, hcol, j)
#                 hcol+=1
#             break
                
#         for i in rs:
#             for j in i.values():
#                worksheet.write(row, col, j)
#                col+=1     
#             col = 0
#             row += 1
         
#     workbook.close()
#     output.seek(0)

#     headers = {
#         'Content-Disposition': 'attachment; filename="filename.xlsx"'
#     }
#     return StreamingResponse(output, headers=headers)

# @noida_stats_router.get("/download/placed_list/{cid}", response_description='xlsx')
# async def cid_list(cid:int,reg:Request,dba: Session = Depends(get_db)):
#     row=1
#     col=0

#     with engine.connect() as con:

#         sql = """select s.urn,email,branch,full_name,first_name,middle_name,last_name,ssc,hsc,ug,ug_percentage,pg,backlogs,sem1,sem2,sem3,sem4,sem5,sem6,sem7,sem8,current_backlogs,history_backlogs,no_of_x_grades,other_grades,ug_start_year,ug_end_year,ssc_board,ssc_start_year,ssc_end_year,hsc_board,hsc_start_year,hsc_end_year,entry_to_college,rank,gap_in_studies,dob,gender,category,native,parents_name,present_addr,permanent_addr,phone,secondary_phone
#         from students s 
# inner join registrations a on s.urn = a.urn
# where a.cid ={};""".format(cid)

#         rs = con.execute(sql)
#         output = BytesIO()
#         workbook = xlsxwriter.Workbook(output)
#         worksheet = workbook.add_worksheet()
        
                
#         for i in rs:
#             for j in i.values():
#                worksheet.write(row, col, j)
#                col+=1     
#             col = 0
#             row += 1
#     workbook.close()
#     output.seek(0)

#     headers = {
#         'Content-Disposition': 'attachment; filename="filename.xlsx"'
#     }
#     return StreamingResponse(output, headers=headers)

# @noida_stats_router.get("/download/regcid_list_detailed/{cid}", response_description='xlsx')
# async def regcid_list_detailed(cid:int,reg:Request,dba: Session = Depends(get_db)):
#     row=1
#     col=0
    
#     with engine.connect() as con:
#         sql = """select s.urn,email,branch,full_name,first_name,middle_name,last_name,ssc,hsc,ug,ug_percentage,pg,backlogs,sem1,sem2,sem3,sem4,sem5,sem6,sem7,sem8,current_backlogs,history_backlogs,no_of_x_grades,other_grades,ug_start_year,ug_end_year,ssc_board,ssc_start_year,ssc_end_year,hsc_board,hsc_start_year,hsc_end_year,entry_to_college,rank,gap_in_studies,dob,gender,category,native,parents_name,present_addr,permanent_addr,phone,secondary_phone
#         from students s 
# inner join registrations a on s.urn = a.urn
# where a.cid ={};""".format(cid)

#         rs = con.execute(sql)
#         output = BytesIO()
#         workbook = xlsxwriter.Workbook(output)
#         bold = workbook.add_format({'bold': True,'bg_color':'#00C7CE'})
#         format2=workbook.add_format({'num_format': 'dd/mm/yy','border': 2})
#         format3 = workbook.add_format({'border': 2})
#         format4= workbook.add_format({'border': 2})
#         worksheet = workbook.add_worksheet()
#         worksheet.set_row(0, 20, bold)
        
#         worksheet.write(0,0,"urn")
#         worksheet.write(0,1,"email")
#         worksheet.write(0,2,"branch")
#         worksheet.write(0,3,"full_name")
#         worksheet.write(0,4,"first_name")
#         worksheet.write(0,5,"middle_name")
#         worksheet.write(0,6,"last_name")
#         worksheet.write(0,7,"10th_percent")
#         worksheet.write(0,8,"12th_percent")
#         worksheet.write(0,9,"ug_cgpa")
#         worksheet.write(0,10,"ug_percentage")
#         worksheet.write(0,11,"pg")
#         worksheet.write(0,12,"backlogs")
#         worksheet.write(0,13,"sem1_cgpa")
#         worksheet.write(0,14,"sem2_cgpa")
#         worksheet.write(0,15,"sem3_cgpa")
#         worksheet.write(0,16,"sem4_cgpa")
#         worksheet.write(0,17,"sem5_cgpa")
#         worksheet.write(0,18,"sem6_cgpa")
#         worksheet.write(0,19,"sem7_cgpa")
#         worksheet.write(0,20,"sem8_cgpa")
#         worksheet.write(0,21,"current_backlogs")
#         worksheet.write(0,22,"history_backlogs")
#         worksheet.write(0,23,"no_of_x_grades")
#         worksheet.write(0,24,"other_grades")
#         worksheet.write(0,25,"ug_start_year")
#         worksheet.write(0,26,"ug_end_year")
#         worksheet.write(0,27,"10th_board")
#         worksheet.write(0,28,"10th_board_start_year")
#         worksheet.write(0,29,"10th_board_end_year")
#         worksheet.write(0,30,"12th_board")
#         worksheet.write(0,31,"12th_board_start_year")
#         worksheet.write(0,32,"12th_board_end_year")
#         worksheet.write(0,33,"entry_to_college")
#         worksheet.write(0,34,"rank")
#         worksheet.write(0,35,"gap_in_studies")
#         worksheet.write(0,36,"date_of_birth")
#         worksheet.write(0,37,"gender")
#         worksheet.write(0,38,"category")
#         worksheet.write(0,39,"native")
#         worksheet.write(0,40,"parent's name")
#         worksheet.write(0,41,"present_address")
#         worksheet.write(0,42,"permanent_address")
#         worksheet.write(0,43,"phone_number")
#         worksheet.write(0,44,"secondary_phone_number")
        
        
                
#         for i in rs:
#             for j in i.values():
#                worksheet.write(row, col, j)
#                col+=1     
#             col = 0
#             row += 1
#         worksheet.set_column('A:AJ', 25, format3)
#         worksheet.set_column('AK:AK', 25, format2)
#         worksheet.set_column('AL:AS', 25, format3)
#     workbook.close()
#     output.seek(0)

#     headers = {
#         'Content-Disposition': 'attachment; filename="filename.xlsx"'
#     }
#     return StreamingResponse(output, headers=headers)

# @noida_stats_router.get("/download/regcid_list_short/{cid}", response_description='xlsx')
# async def regcid_list_short(cid:int,reg:Request,dba: Session = Depends(get_db)):
#     row=1
#     col=0
    
#     with engine.connect() as con:
#         sql = """select s.urn,email,branch,full_name,ssc,hsc,ug,ug_percentage,backlogs,current_backlogs,history_backlogs,dob,gender,phone
#         from students s 
# inner join registrations a on s.urn = a.urn
# where a.cid ={};""".format(cid)

#         rs = con.execute(sql)
#         output = BytesIO()
        
#         workbook = xlsxwriter.Workbook(output, {'in_memory': True})
#         bold = workbook.add_format({'bold': True,'bg_color':'#00C7CE'})
#         format2=workbook.add_format({'num_format': 'dd/mm/yy','border': 2})
#         format3 = workbook.add_format({'border': 2})
#         format4= workbook.add_format({'border': 2})
#         worksheet = workbook.add_worksheet()
#         worksheet.set_row(0, 20, bold)
        
#         worksheet.write(0,0,"urn")
#         worksheet.write(0,1,"email")
#         worksheet.write(0,2,"branch")
#         worksheet.write(0,3,"full_name")
#         worksheet.write(0,4,"10th_percent")
#         worksheet.write(0,5,"12th_percent")
#         worksheet.write(0,6,"ug_cgpa")
#         worksheet.write(0,7,"ug_percentage")
#         worksheet.write(0,8,"backlogs")
#         worksheet.write(0,9,"current_backlogs")
#         worksheet.write(0,10,"history_backlogs")
#         worksheet.write(0,11,"date_of_birth")
#         worksheet.write(0,12,"gender")
#         worksheet.write(0,13,"phone_number")
        
        
                
#         for i in rs:
#             for j in i.values():
#                worksheet.write(row, col, j)
#                col+=1     
#             col = 0
#             row += 1
#         worksheet.set_column('A:K', 25, format3)
#         worksheet.set_column('L:L', 25, format2)
#         worksheet.set_column('M:N', 25, format3)
#     workbook.close()
#     output.seek(0)

#     headers = {
#         'Content-Disposition': 'attachment; filename="filename.xlsx"'
#     }
#     return StreamingResponse(output, headers=headers)

# @noida_stats_router.get("/download/regcid_count/{cid}", response_description='xlsx')
# async def regcid_count(cid:int,reg:Request,dba: Session = Depends(get_db)):
#     c=0
#     row=1
#     col=0

#     with engine.connect() as con:

#         sql = """select * from students s 
# inner join registrations a on s.urn = a.urn
# where a.cid ={};""".format(cid)

#         rs = con.execute(sql)
        
                
#         for i in rs:
#             c+=1
#     return c

#from sqlalchemy import create_engine

# @noida_stats_router.get("/download/xlsxtest8", response_description='xlsx')
# async def data8(reg:Request,dba: Session = Depends(get_db)):
#     a=[]
#     b=[]
#     c=[]
#     hrow=0
#     hcol=0
#     row=1
#     col=0
    
#     engine=create_engine('postgresql://postgres:harshshah14@placementsjce-database.cpzsfk8mvw8y.ap-south-1.rds.amazonaws.com:5432/postgres', echo=True)
#     with engine.connect() as con:

#         rs = con.execute('SELECT * FROM Students OFFSET 0 ROWS')
#         output = BytesIO()
#         workbook = xlsxwriter.Workbook(output)
#         worksheet = workbook.add_worksheet()
        
#         # for i in rs:
#         #     for j in i.keys():
#         #         worksheet.write(hrow, hcol, j)
#         #         hcol+=1
#         #     break
                
#         for i in rs:
#             for j in i.values():
#                worksheet.write(row, col, j)
#                col+=1     
#             col = 0
#             row += 1
         
#     workbook.close()
#     output.seek(0)

#     headers = {
#         'Content-Disposition': 'attachment; filename="filename.xlsx"'
#     }
#     return StreamingResponse(output, headers=headers)            













