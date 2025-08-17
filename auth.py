from typing import Optional, Dict, List, Callable
from fastapi import Depends, HTTPException, status, APIRouter, Header, Form
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from passlib.context import CryptContext
from functools import wraps
from model import User
import jwt
from datetime import datetime, timedelta

# 路由
router = APIRouter()

# 密码加密
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT 配置
SECRET_KEY = "f4b2e8a1-9c3d-4e2a-8c7e-1a2b3c4d5e6f"  # 固定密钥，建议仅用于开发或测试环境
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 5256000  # token 永久有效

# OAuth2 方案
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Pydantic 模型
class UserLogin(BaseModel):
    username: str
    password: str

from enum import Enum
class UserTypeEnum(str, Enum):
    saler = "saler"
    incomer = "incomer"
    ivoicer = "ivoicer"
    admin = "admin"

class UserCreate(BaseModel):
    username: str
    password: str
    user_type: UserTypeEnum

# JWT 工具函数
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# 工具函数
def verify_password(plain_password, hashed_password):
    """验证密码"""
    if not hashed_password or not hashed_password.startswith("$2b$"):
        raise HTTPException(status_code=500, detail="无效的密码哈希格式")
    return pwd_context.verify(plain_password, hashed_password)

async def get_user(username: str):
    """获取用户信息"""
    try:
        return await User.get(username=username).values()
    except User.DoesNotExist:
        return None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据库查询失败: {str(e)}")

async def authenticate_user(username: str, password: str):
    """用户认证"""
    try:
        user = await get_user(username)
        if not user:
            return False
        if not verify_password(password, user["hashed_password"]):
            return False
        return user
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"认证失败: {str(e)}")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """获取当前认证用户（基于 JWT）"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="无效的 token")
        user = await get_user(username)
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")
        if not user["is_active"]:
            raise HTTPException(status_code=400, detail="账户已禁用")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的 token")

def require_roles(allowed_roles: List[str]):
    """角色验证装饰器，检查用户是否具有指定角色"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, current_user: dict = Depends(get_current_user), **kwargs):
            if current_user["user_type"] == "admin" or current_user["user_type"] in allowed_roles:
                return await func(*args, current_user=current_user, **kwargs)
            raise HTTPException(status_code=403, detail="权限不足")
        return wrapper
    return decorator

class OAuth2TokenResponse(BaseModel):
    access_token: str
    token_type: str
    message: Optional[str] = None  # 可选字段
    user: Optional[dict] = None    # 可选字段

# 用户登录 API
@router.post("/login", response_model=OAuth2TokenResponse, tags=["auth"])
async def login(username: str = Form(...), password: str = Form(...)):
    user = await authenticate_user(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user["is_active"]:
        raise HTTPException(status_code=400, detail="账户已禁用")
    access_token = create_access_token(data={"sub": user["username"]})
    
    # 构建符合 OAuth2 规范的返回结构
    response = {
        "access_token": access_token,
        "token_type": "bearer",
        # 保留你需要的额外信息
        "message": "登录成功",
        "user": user
    }
    
    return response

# 创建用户 API
@router.post("/create_user", tags=["auth"])
@require_roles(["admin"])
async def create_user(user: UserCreate, current_user: dict = Depends(get_current_user)):
    hashed_password = pwd_context.hash(user.password)
    if not hashed_password.startswith("$2b$"):
        raise HTTPException(status_code=500, detail="密码哈希生成失败")
    try:
        allowed_types = ["saler", "incomer", "invoicer", "admin"]
        if user.user_type not in allowed_types:
            raise HTTPException(status_code=400, detail="无效的用户类型")
        new_user = await User.create(
            username=user.username,
            hashed_password=hashed_password,
            user_type=user.user_type
        )
        return {"message": "用户创建成功", "user_id": new_user.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"用户创建失败: {str(e)}")

# 删除用户 API
@router.delete("/delete_user/{username}", tags=["auth"])
@require_roles(["admin"])
async def delete_user(username: str, current_user: dict = Depends(get_current_user)):
    try:
        user = await User.get(username=username)
        await user.delete()
        return {"message": "用户删除成功"}
    except User.DoesNotExist:
        raise HTTPException(status_code=404, detail="用户不存在")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"用户删除失败: {str(e)}")