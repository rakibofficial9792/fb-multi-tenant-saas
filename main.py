from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client
import requests
import os
from jose import jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta

app = FastAPI()

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

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("Missing Supabase environment variables")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

SECRET_KEY = "SUPER_SECRET_KEY_2026"
ALGORITHM  = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security    = HTTPBearer()


# ── Helpers ──────────────────────────────────────────────

def create_access_token(data: dict, expires_days: int = 7):
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(days=expires_days)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        return jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def auto_delete_old_posts(client_id: int):
    """Calendar month শুরুর আগের সব post delete করে"""
    now = datetime.utcnow()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    supabase.table("posts").delete().eq(
        "client_id", client_id
    ).lt("created_at", start_of_month).execute()


# ── Models ───────────────────────────────────────────────

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


# ── Routes ───────────────────────────────────────────────

@app.get("/")
def home():
    return {"status": "running", "message": "FB Multi Tenant SaaS Live 🚀"}


@app.post("/client-login")
def client_login(data: ClientLogin):
    result = supabase.table("clients").select("*").eq("email", data.email).execute()
    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid login")
    user = result.data[0]
    if not pwd_context.verify(data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid password")
    token = create_access_token({"client_id": user["id"], "role": "client"}, expires_days=30)
    return {"success": True, "token": token, "client": user}


@app.post("/employee-login")
def employee_login(data: EmployeeLogin):
    result = supabase.table("employees").select("*").eq("username", data.username).execute()
    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid login")
    user = result.data[0]
    if not pwd_context.verify(data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid password")
    token = create_access_token(
        {"employee_id": user["id"], "client_id": user["client_id"], "role": "employee"},
        expires_days=7
    )
    return {"success": True, "token": token, "employee": user}


@app.post("/create-employee/{client_id}")
def create_employee(client_id: int, data: CreateEmployee, user=Depends(verify_token)):
    if user["client_id"] != client_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if supabase.table("employees").select("*").eq("username", data.username).execute().data:
        raise HTTPException(status_code=400, detail="Username already exists")
    result = supabase.table("employees").insert({
        "client_id":     client_id,
        "employee_name": data.employee_name,
        "username":      data.username,
        "password":      pwd_context.hash(data.password)
    }).execute()
    return {"success": True, "employee": result.data[0]}


@app.get("/collect-posts/{client_id}")
def collect_posts(client_id: int, user=Depends(verify_token)):
    if user["client_id"] != client_id:
        raise HTTPException(status_code=403, detail="Access denied")

    client = supabase.table("clients").select("*").eq("id", client_id).execute()
    if not client.data:
        raise HTTPException(status_code=404, detail="Client not found")

    c          = client.data[0]
    fb_url     = f"https://graph.facebook.com/v23.0/{c.get('page_id')}/posts"
    params     = {
        "access_token": c.get("access_token"),
        "fields": "id,message,created_time,full_picture,scheduled_publish_time",
        "limit": 100
    }

    # ✅ Pagination — সব post আনবে
    all_posts = []
    while True:
        response  = requests.get(fb_url, params=params)
        data      = response.json()
        batch     = data.get("data", [])
        all_posts.extend(batch)
        next_page = data.get("paging", {}).get("next")
        if not next_page:
            break
        fb_url = next_page
        params = {}

    posts       = all_posts
    saved_posts = []

    for post in posts:
        post_id = post.get("id")
        if supabase.table("posts").select("id").eq("post_id", post_id).execute().data:
            continue

        # scheduled_publish_time থাকলে সেটা, না হলে created_time
        scheduled = post.get("scheduled_publish_time")
        post_time = scheduled if scheduled else post.get("created_time")

        supabase.table("posts").insert({
            "client_id":  client_id,
            "post_id":    post_id,
            "caption":    post.get("message", ""),
            "image_url":  post.get("full_picture", ""),
            "post_time":  post_time,
        }).execute()

        saved_posts.append(post_id)

    # ✅ পুরনো post auto delete
    auto_delete_old_posts(client_id)

    return {
        "success":      True,
        "total_fetched": len(posts),
        "new_saved":    len(saved_posts),
    }


@app.get("/posts/{client_id}")
def get_posts(client_id: int, user=Depends(verify_token)):
    if user["client_id"] != client_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # ✅ Auto delete পুরনো post
    auto_delete_old_posts(client_id)

    now = datetime.utcnow()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    # সব post count (stats এর জন্য)
    all_posts = supabase.table("posts").select("*").eq(
        "client_id", client_id
    ).order("id", desc=True).limit(1000).execute()

    total      = len(all_posts.data)
    published  = sum(1 for p in all_posts.data if p.get("post_time") and p["post_time"] <= now.isoformat())
    scheduled  = sum(1 for p in all_posts.data if p.get("post_time") and p["post_time"] >  now.isoformat())
    this_month = sum(1 for p in all_posts.data if p.get("created_at") and p["created_at"] >= start_of_month)

    # এই মাসের post (table এর জন্য)
    month_posts = supabase.table("posts").select("*").eq(
        "client_id", client_id
    ).gte("created_at", start_of_month).order("id", desc=True).execute()

    return {
        "success":    True,
        "total":      total,
        "published":  published,
        "scheduled":  scheduled,
        "this_month": this_month,
        "posts":      month_posts.data,
    }


@app.get("/employee-posts/{employee_id}")
def employee_posts(employee_id: int, user=Depends(verify_token)):
    if user.get("employee_id") != employee_id:
        raise HTTPException(status_code=403, detail="Access denied")
    employee = supabase.table("employees").select("*").eq("id", employee_id).execute()
    if not employee.data:
        raise HTTPException(status_code=404, detail="Employee not found")
    emp       = employee.data[0]
    posts     = supabase.table("posts").select("*").eq(
        "client_id", emp["client_id"]
    ).order("id", desc=True).execute()
    return {"success": True, "employee": emp["employee_name"], "posts": posts.data}


@app.get("/generate-hash/{password}")
def generate_hash(password: str):
    return {"password": password, "hashed_password": pwd_context.hash(password)}
