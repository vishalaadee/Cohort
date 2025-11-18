from .admin_routes import get_current_admin
from fastapi import FastAPI
from . import models
from .analytics import stats_router
from .auth_routes import auth_router
from .admin_routes import admin_router
from .student_routes import itemrouter
from .mysore_analytics import mysore_stats_router
from .bangalore_analytics import bangalore_stats_router
from .noida_analytics import noida_stats_router
from fastapi_jwt_auth import AuthJWT
from .schemas import Settings
import os , logging
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session  # type: ignore

load_dotenv()

origins = ["*"]

security = HTTPBasic()

from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware


app=FastAPI()


@AuthJWT.load_config
def get_config():
    return Settings()

# Create a logger
logger = logging.getLogger("my_logger")
logger.setLevel(logging.ERROR)  # Set the log level to capture errors and warnings

# Create a file handler to store log messages in a file
log_file = "error.log"
file_handler = logging.FileHandler(log_file)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)

# Add the file handler to the logger
logger.addHandler(file_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(itemrouter,include_in_schema=True)
app.include_router(stats_router,include_in_schema=True)
app.include_router(mysore_stats_router,include_in_schema=True)
app.include_router(bangalore_stats_router,include_in_schema=True)
app.include_router(noida_stats_router,include_in_schema=True)

