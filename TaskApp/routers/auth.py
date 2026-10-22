from datetime import timedelta, datetime, timezone
import hashlib
import logging
import os
import secrets
import smtplib
from typing import Annotated
from pathlib import Path as PyPath
from urllib.parse import urlencode
from email.message import EmailMessage

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from starlette import status
from dotenv import load_dotenv
from database import SessionLocal
from models import Users
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from jose import jwt, JWTError
from fastapi.templating import Jinja2Templates

router = APIRouter(
    prefix='/auth',
    tags=['auth']
)
logger = logging.getLogger(__name__)
load_dotenv(PyPath(__file__).resolve().parents[2] / ".env")

SECRET_KEY = '197b2c37c391bed93fe80344fe73b806947a65e36206e05a1a23c2fa12702fe3'
ALGORITHM = 'HS256'

bcrypt_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
oauth2_bearer = OAuth2PasswordBearer(tokenUrl='auth/token')


class CreateUserRequest(BaseModel):
    username: str
    email: EmailStr
    first_name: str
    last_name: str
    password: str
    role: str
    phone_number: str


class Token(BaseModel):
    access_token: str
    token_type: str


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


db_dependency = Annotated[Session, Depends(get_db)]
templates = Jinja2Templates(directory=PyPath(__file__).resolve().parent.parent / "templates")



### Pages ###

@router.get("/login-page")
def render_login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")

@router.get("/register-page")
def render_register_page(request: Request):
    return templates.TemplateResponse(request, "register.html")

### Endpoints ###
def authenticate_user(username: str, password: str, db):
    user = db.query(Users).filter(Users.username == username).first()
    if not user:
        return False
    if not bcrypt_context.verify(password, user.hashed_password):
        return False
    return user


def create_access_token(username: str, user_id: int, role: str, expires_delta: timedelta):
    encode = {'sub': username, 'id': user_id, 'role': role}
    expires = datetime.now(timezone.utc) + expires_delta
    encode.update({'exp': expires})
    return jwt.encode(encode, SECRET_KEY, algorithm=ALGORITHM)


def send_verification_email(email: str, token: str):
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM") or smtp_username
    try:
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError as exc:
        raise RuntimeError("SMTP_PORT must be a valid port number.") from exc

    if not smtp_username or not smtp_password or not sender:
        raise RuntimeError("SMTP_USERNAME and SMTP_PASSWORD must be configured.")
    if not 1 <= smtp_port <= 65535:
        raise RuntimeError("SMTP_PORT must be between 1 and 65535.")

    base_url = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    verification_url = f"{base_url}/auth/verify-email?{urlencode({'token': token})}"

    message = EmailMessage()
    message["Subject"] = "Verify your TaskApp email address"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        "Please verify your TaskApp email address by opening this link:\n\n"
        f"{verification_url}\n\n"
        "This link expires in 24 hours."
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
        smtp.starttls()
        smtp.login(smtp_username, smtp_password)
        smtp.send_message(message)


async def get_current_user(token: Annotated[str, Depends(oauth2_bearer)]):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get('sub')
        user_id: int = payload.get('id')
        user_role: str = payload.get('role')
        if username is None or user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail='Could not validate user.')
        return {'username': username, 'id': user_id, 'user_role': user_role}
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail='Could not validate user.')


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_user(db: db_dependency,
                create_user_request: CreateUserRequest):
    email = str(create_user_request.email).strip().lower()
    existing_user = db.query(Users).filter(
        (func.lower(Users.email) == email) |
        (Users.username == create_user_request.username)
    ).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Email or username is already registered.")

    verification_token = secrets.token_urlsafe(32)
    create_user_model = Users(
        email=email,
        username=create_user_request.username,
        first_name=create_user_request.first_name,
        last_name=create_user_request.last_name,
        role=create_user_request.role,
        hashed_password=bcrypt_context.hash(create_user_request.password),
        is_active=True,
        phone_number=create_user_request.phone_number,
        is_email_verified=False,
        email_verification_token_hash=hashlib.sha256(
            verification_token.encode("utf-8")
        ).hexdigest(),
        email_verification_expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
    )

    db.add(create_user_model)
    try:
        db.flush()
        send_verification_email(email, verification_token)
        db.commit()
    except (smtplib.SMTPException, OSError, RuntimeError) as exc:
        db.rollback()
        logger.exception("Could not send verification email.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not send the verification email. Please try again later."
        ) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or username is already registered."
        ) from exc

    return {"message": "Account created. Check your email to verify it."}


@router.get("/verify-email")
async def verify_email(token: str, db: db_dependency, request: Request):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    user = db.query(Users).filter(
        Users.email_verification_token_hash == token_hash
    ).first()
    if user is None:
        return templates.TemplateResponse(
            request,
            "verify_email.html",
            {"verified": False, "message": "This verification link is invalid or has expired."},
            status_code=status.HTTP_400_BAD_REQUEST
        )

    expires_at = user.email_verification_expires_at
    if expires_at is None:
        return templates.TemplateResponse(
            request,
            "verify_email.html",
            {"verified": False, "message": "This verification link is invalid or has expired."},
            status_code=status.HTTP_400_BAD_REQUEST
        )
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        return templates.TemplateResponse(
            request,
            "verify_email.html",
            {"verified": False, "message": "This verification link is invalid or has expired."},
            status_code=status.HTTP_400_BAD_REQUEST
        )

    user.is_email_verified = True
    user.email_verification_token_hash = None
    user.email_verification_expires_at = None
    db.commit()
    return templates.TemplateResponse(
        request,
        "verify_email.html",
        {"verified": True, "message": "Your email is verified. You can now sign in."}
    )


@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
                                 db: db_dependency):
    user = authenticate_user(form_data.username, form_data.password, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail='Could not validate user.')
    if not user.is_email_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='Please verify your email before signing in.')
    token = create_access_token(user.username, user.id, user.role, timedelta(minutes=20))

    return {'access_token': token, 'token_type': 'bearer'}



