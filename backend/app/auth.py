import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select, delete
from app.database import get_db
from app.models import User, LoginSession, LoginAttempt, AuditEvent, now
from app.config import get_settings

auth_router=APIRouter(prefix="/api/v1/auth",tags=["Authentication"])
bearer=HTTPBearer(auto_error=False)
def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()
def password_hash(password,salt):
    return hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
def ensure_admin(db):
    s=get_settings()
    if db.scalar(select(User).limit(1)):
        return
    if len(s.admin_password)<12:
        raise RuntimeError("ADMIN_PASSWORD must contain at least 12 characters")
    salt=secrets.token_hex(16)
    db.add(User(username=s.admin_username,salt=salt,password_hash=password_hash(s.admin_password,salt)))
    db.commit()
def require_user(request:Request,credentials:HTTPAuthorizationCredentials|None=Depends(bearer),db=Depends(get_db)):
    if request.url.path in ('/api/v1/health','/api/v1/ready'):
        return 'healthcheck'
    if not get_settings().auth_enabled:
        return "local-test"
    if not credentials:
        raise HTTPException(401,"Sign in to continue.")
    session=db.get(LoginSession,digest(credentials.credentials))
    if not session or session.expires_at<now():
        raise HTTPException(401,"Session expired. Sign in again.")
    return session.username

class LoginRequest(BaseModel):
    username:str=Field(min_length=1,max_length=100)
    password:str=Field(min_length=1,max_length=200)

@auth_router.post("/login")
def login(body:LoginRequest,db=Depends(get_db)):
    attempt=db.get(LoginAttempt,body.username)
    cutoff=(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()
    if attempt and attempt.updated_at>cutoff and attempt.count>=10:
        raise HTTPException(429,"Too many attempts. Try again in five minutes.")
    user=db.get(User,body.username)
    salt=user.salt if user else "00"*16
    valid=hmac.compare_digest(password_hash(body.password,salt),user.password_hash if user else "0"*128)
    if not user or not valid:
        if not attempt:
            attempt=LoginAttempt(username=body.username,count=0,updated_at=now())
            db.add(attempt)
        attempt.count=(attempt.count+1) if attempt.updated_at>cutoff else 1
        attempt.updated_at=now()
        db.commit()
        raise HTTPException(401,"Invalid username or password.")
    if attempt:
        db.delete(attempt)
    token=secrets.token_urlsafe(32)
    expires=(datetime.now(timezone.utc)+timedelta(hours=8)).isoformat()
    db.add(LoginSession(token_hash=digest(token),username=user.username,expires_at=expires))
    db.commit()
    return {"access_token":token,"token_type":"bearer","username":user.username,"expires_at":expires}

@auth_router.get("/me")
def me(user=Depends(require_user)):
    return {"username":user}

@auth_router.post("/logout")
def logout(credentials:HTTPAuthorizationCredentials|None=Depends(bearer),db=Depends(get_db)):
    if credentials:
        session=db.get(LoginSession,digest(credentials.credentials))
        if session:
            db.delete(session)
            db.commit()
    return {"message":"Signed out"}


class PasswordChangeRequest(BaseModel):
    current_password: SecretStr = Field(min_length=1, max_length=200)
    new_password: SecretStr = Field(min_length=12, max_length=200)


@auth_router.post('/password')
def change_password(body: PasswordChangeRequest, username=Depends(require_user), db=Depends(get_db)):
    """Verify current credentials, rotate the password, and revoke every session atomically."""
    user = db.get(User, username)
    if not get_settings().auth_enabled or user is None:
        raise HTTPException(400, 'Password changes require an authenticated administrator.')
    attempt_key = 'password:' + digest(username)
    attempt = db.get(LoginAttempt, attempt_key)
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    if attempt and attempt.updated_at > cutoff and attempt.count >= 10:
        raise HTTPException(429, 'Too many attempts. Try again in five minutes.')
    current_password = body.current_password.get_secret_value()
    new_password = body.new_password.get_secret_value()
    if not hmac.compare_digest(password_hash(current_password, user.salt), user.password_hash):
        if attempt is None:
            attempt = LoginAttempt(username=attempt_key, count=0, updated_at=now())
            db.add(attempt)
        attempt.count = attempt.count + 1 if attempt.updated_at > cutoff else 1
        attempt.updated_at = now()
        db.commit()
        raise HTTPException(400, 'Current password is incorrect.')
    if hmac.compare_digest(current_password.encode(), new_password.encode()):
        raise HTTPException(400, 'Choose a different new password.')
    user.salt = secrets.token_hex(16)
    user.password_hash = password_hash(new_password, user.salt)
    db.execute(delete(LoginSession).where(LoginSession.username == username))
    db.execute(delete(LoginAttempt).where(LoginAttempt.username.in_([username, attempt_key])))
    db.add(AuditEvent(entity_id=username, action='password_changed', details={'sessions_revoked': True}))
    db.commit()
    return {'message': 'Password changed. Sign in again with your new password.'}
