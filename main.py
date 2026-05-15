from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

from supabase import create_client

from jose import jwt

from passlib.context import CryptContext

from datetime import datetime, timedelta, timezone

import requests
import os

app = FastAPI()

# ─────────────────────────────────────────────
# CORS
# ─────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://rakibofficial9792.github.io",
        "http://localhost",
        "http://127.0.0.1",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# SUPABASE
# ─────────────────────────────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("Missing Supabase environment variables")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

# ─────────────────────────────────────────────
# SECURITY
# ─────────────────────────────────────────────

SECRET_KEY = "SUPER_SECRET_KEY_2026"
ALGORITHM  = "HS256"

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

security = HTTPBearer()

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def create_access_token(
    data: dict,
    expires_days: int = 7
):

    to_encode = data.copy()

    to_encode.update({
        "exp": datetime.utcnow() + timedelta(days=expires_days)
    })

    return jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):

    try:

        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        return payload

    except:

        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )

def auto_delete_old_posts(client_id: int):

    now = datetime.utcnow()

    start_of_month = now.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    ).isoformat()

    supabase.table("posts").delete().eq(
        "client_id",
        client_id
    ).lt(
        "post_time",
        start_of_month
    ).execute()

# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────

class ClientLogin(BaseModel):
    email: str
    password: str

class EmployeeLogin(BaseModel):
    username: str
    password: str

class CreateEmployee(BaseModel):
    employee_name: str
    username: str
    password: str

# ─────────────────────────────────────────────
# HOME
# ─────────────────────────────────────────────

@app.get("/")
def home():

    return {
        "status": "running",
        "message": "FB Multi Tenant SaaS Live 🚀"
    }

# ─────────────────────────────────────────────
# CLIENT LOGIN
# ─────────────────────────────────────────────

@app.post("/client-login")
def client_login(data: ClientLogin):

    result = supabase.table("clients").select("*").eq(
        "email",
        data.email
    ).execute()

    if not result.data:

        raise HTTPException(
            status_code=401,
            detail="Invalid login"
        )

    user = result.data[0]

    if not pwd_context.verify(
        data.password,
        user["password"]
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid password"
        )

    token = create_access_token(
        {
            "client_id": user["id"],
            "role": "client"
        },
        expires_days=30
    )

    return {
        "success": True,
        "token": token,
        "client": user
    }

# ─────────────────────────────────────────────
# EMPLOYEE LOGIN
# ─────────────────────────────────────────────

@app.post("/employee-login")
def employee_login(data: EmployeeLogin):

    result = supabase.table("employees").select("*").eq(
        "username",
        data.username
    ).execute()

    if not result.data:

        raise HTTPException(
            status_code=401,
            detail="Invalid login"
        )

    user = result.data[0]

    if not pwd_context.verify(
        data.password,
        user["password"]
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid password"
        )

    token = create_access_token(
        {
            "employee_id": user["id"],
            "client_id": user["client_id"],
            "role": "employee"
        },
        expires_days=7
    )

    return {
        "success": True,
        "token": token,
        "employee": user
    }

# ─────────────────────────────────────────────
# CREATE EMPLOYEE
# ─────────────────────────────────────────────

@app.post("/create-employee/{client_id}")
def create_employee(
    client_id: int,
    data: CreateEmployee,
    user=Depends(verify_token)
):

    if user["client_id"] != client_id:

        raise HTTPException(
            status_code=403,
            detail="Access denied"
        )

    existing = supabase.table("employees").select("*").eq(
        "username",
        data.username
    ).execute()

    if existing.data:

        raise HTTPException(
            status_code=400,
            detail="Username already exists"
        )

    result = supabase.table("employees").insert({

        "client_id": client_id,

        "employee_name": data.employee_name,

        "username": data.username,

        "password": pwd_context.hash(data.password)

    }).execute()

    return {
        "success": True,
        "employee": result.data[0]
    }

# ─────────────────────────────────────────────
# COLLECT POSTS
# ─────────────────────────────────────────────

@app.get("/collect-posts/{client_id}")
def collect_posts(
    client_id: int,
    user=Depends(verify_token)
):

    if user["client_id"] != client_id:

        raise HTTPException(
            status_code=403,
            detail="Access denied"
        )

    client = supabase.table("clients").select("*").eq(
        "id",
        client_id
    ).execute()

    if not client.data:

        raise HTTPException(
            status_code=404,
            detail="Client not found"
        )

    c = client.data[0]

    fb_url = f"https://graph.facebook.com/v23.0/{c.get('page_id')}/posts"

    params = {

        "access_token": c.get("access_token"),

        "fields": "id,message,created_time,full_picture,scheduled_publish_time,is_published",

        "limit": 100
    }

    all_posts = []

    while True:

        response = requests.get(
            fb_url,
            params=params
        )

        data = response.json()

        batch = data.get("data", [])

        all_posts.extend(batch)

        next_page = data.get("paging", {}).get("next")

        if not next_page:
            break

        fb_url = next_page
        params = {}

    saved_posts = []

    for post in all_posts:

        post_id = post.get("id")

        existing = supabase.table("posts").select("id").eq(
            "post_id",
            post_id
        ).execute()

        if existing.data:
            continue

        scheduled = post.get("scheduled_publish_time")

        post_time = (
            scheduled
            if scheduled
            else post.get("created_time")
        )

        supabase.table("posts").insert({

            "client_id": client_id,

            "post_id": post_id,

            "caption": post.get("message", ""),

            "image_url": post.get("full_picture", ""),

            "post_time": post_time,

            "is_published": post.get(
                "is_published",
                True
            )

        }).execute()

        saved_posts.append(post_id)

    auto_delete_old_posts(client_id)

    return {

        "success": True,

        "total_fetched": len(all_posts),

        "new_saved": len(saved_posts)
    }

# ─────────────────────────────────────────────
# GET POSTS
# ─────────────────────────────────────────────

@app.get("/posts/{client_id}")
def get_posts(
    client_id: int,
    user=Depends(verify_token)
):

    if user["client_id"] != client_id:

        raise HTTPException(
            status_code=403,
            detail="Access denied"
        )

    auto_delete_old_posts(client_id)

    posts_result = supabase.table("posts").select("*").eq(
        "client_id",
        client_id
    ).order(
        "post_time",
        desc=True
    ).execute()

    posts = posts_result.data or []

    now = datetime.now(timezone.utc)

    published = 0
    scheduled = 0
    this_month = 0

    current_month = now.month
    current_year = now.year

    for p in posts:

        try:

            if not p.get("post_time"):
                continue

            post_time = datetime.fromisoformat(
                p["post_time"].replace("Z", "+00:00")
            )

            if post_time > now:
                scheduled += 1
            else:
                published += 1

            if (
                post_time.month == current_month
                and
                post_time.year == current_year
            ):
                this_month += 1

        except:
            pass

    return {

        "success": True,

        "total": len(posts),

        "published": published,

        "scheduled": scheduled,

        "this_month": this_month,

        "posts": posts
    }

# ─────────────────────────────────────────────
# EMPLOYEE POSTS
# ─────────────────────────────────────────────

@app.get("/employee-posts/{employee_id}")
def employee_posts(
    employee_id: int,
    user=Depends(verify_token)
):

    if user.get("employee_id") != employee_id:

        raise HTTPException(
            status_code=403,
            detail="Access denied"
        )

    employee = supabase.table("employees").select("*").eq(
        "id",
        employee_id
    ).execute()

    if not employee.data:

        raise HTTPException(
            status_code=404,
            detail="Employee not found"
        )

    emp = employee.data[0]

    posts = supabase.table("posts").select("*").eq(
        "client_id",
        emp["client_id"]
    ).order(
        "post_time",
        desc=True
    ).execute()

    return {

        "success": True,

        "employee": emp["employee_name"],

        "posts": posts.data
    }

# ─────────────────────────────────────────────
# HASH PASSWORD
# ─────────────────────────────────────────────

@app.get("/generate-hash/{password}")
def generate_hash(password: str):

    return {

        "password": password,

        "hashed_password": pwd_context.hash(password)
    }
