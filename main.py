from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client
import requests
import os

from jose import jwt
from datetime import datetime, timedelta

app = FastAPI()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("Missing Supabase environment variables")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

SECRET_KEY = "SUPER_SECRET_KEY_2026"
ALGORITHM = "HS256"


def create_access_token(data: dict, expires_days: int = 7):
    to_encode = data.copy()

    expire = datetime.utcnow() + timedelta(days=expires_days)

    to_encode.update({
        "exp": expire
    })

    encoded_jwt = jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return encoded_jwt


class ClientLogin(BaseModel):
    email: str
    password: str


class EmployeeLogin(BaseModel):
    username: str
    password: str


@app.get("/")
def home():
    return {
        "status": "running",
        "message": "FB Multi Tenant SaaS Live 🚀"
    }


@app.post("/client-login")
def client_login(data: ClientLogin):

    result = supabase.table("clients").select("*").eq(
        "email",
        data.email
    ).eq(
        "password",
        data.password
    ).execute()

    if not result.data:
        raise HTTPException(
            status_code=401,
            detail="Invalid login"
        )

    token = create_access_token(
        {
            "client_id": result.data[0]["id"],
            "role": "client"
        },
        expires_days=30
    )

    return {
        "success": True,
        "token": token,
        "client": result.data[0]
    }


@app.post("/employee-login")
def employee_login(data: EmployeeLogin):

    result = supabase.table("employees").select("*").eq(
        "username",
        data.username
    ).eq(
        "password",
        data.password
    ).execute()

    if not result.data:
        raise HTTPException(
            status_code=401,
            detail="Invalid login"
        )

    token = create_access_token(
        {
            "employee_id": result.data[0]["id"],
            "client_id": result.data[0]["client_id"],
            "role": "employee"
        },
        expires_days=7
    )

    return {
        "success": True,
        "token": token,
        "employee": result.data[0]
    }


@app.get("/collect-posts/{client_id}")
def collect_posts(client_id: int):

    client = supabase.table("clients").select("*").eq(
        "id",
        client_id
    ).execute()

    if not client.data:
        raise HTTPException(
            status_code=404,
            detail="Client not found"
        )

    client_data = client.data[0]

    page_id = client_data.get("page_id")
    access_token = client_data.get("access_token")

    fb_url = f"https://graph.facebook.com/v23.0/{page_id}/posts"

    params = {
        "access_token": access_token,
        "fields": "id,message,created_time,full_picture"
    }

    response = requests.get(
        fb_url,
        params=params
    )

    data = response.json()

    posts = data.get("data", [])

    saved_posts = []

    for post in posts:

        post_data = {
            "client_id": client_id,
            "post_id": post.get("id"),
            "caption": post.get("message", ""),
            "image_url": post.get("full_picture", ""),
            "post_time": post.get("created_time")
        }

        existing = supabase.table("posts").select("*").eq(
            "post_id",
            post.get("id")
        ).execute()

        if not existing.data:

            supabase.table("posts").insert(
                post_data
            ).execute()

            saved_posts.append(post_data)

    return {
        "success": True,
        "total_fetched": len(posts),
        "new_saved": len(saved_posts),
        "posts": saved_posts
    }


@app.get("/posts/{client_id}")
def get_posts(client_id: int):

    posts = supabase.table("posts").select("*").eq(
        "client_id",
        client_id
    ).order(
        "id",
        desc=True
    ).execute()

    return {
        "posts": posts.data
    }


@app.get("/employee-posts/{employee_id}")
def employee_posts(employee_id: int):

    employee = supabase.table("employees").select("*").eq(
        "id",
        employee_id
    ).execute()

    if not employee.data:
        raise HTTPException(
            status_code=404,
            detail="Employee not found"
        )

    client_id = employee.data[0]["client_id"]

    posts = supabase.table("posts").select("*").eq(
        "client_id",
        client_id
    ).order(
        "id",
        desc=True
    ).execute()

    return {
        "employee": employee.data[0],
        "posts": posts.data
    }
