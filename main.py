from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client
import requests
import os

app = FastAPI()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("Missing Supabase environment variables")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


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

    return {
        "success": True,
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

    return {
        "success": True,
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

    response = requests.get(
        fb_url,
        params={
            "access_token": access_token,
            "fields": "id,message,created_time,full_picture"
        }
    )

    fb_data = response.json()

    if "error" in fb_data:
        raise HTTPException(
            status_code=400,
            detail=fb_data["error"]
        )

    posts = fb_data.get("data", [])

    saved = []

    for post in posts:

        post_id = post.get("id")

        exists = supabase.table("posts").select("id").eq(
            "post_id",
            post_id
        ).execute()

        if exists.data:
            continue

        new_post = {
            "client_id": client_id,
            "post_id": post_id,
            "caption": post.get("message", ""),
            "image_url": post.get("full_picture", ""),
            "post_time": post.get("created_time", "")
        }

        insert = supabase.table("posts").insert(
            new_post
        ).execute()

        saved.append(insert.data)

    return {
        "success": True,
        "total_saved": len(saved),
        "posts": saved
    }


@app.get("/posts/{client_id}")
def get_posts(client_id: int):

    result = supabase.table("posts").select("*").eq(
        "client_id",
        client_id
    ).execute()

    return {
        "success": True,
        "posts": result.data
    }

@app.post("/employee-login")
def employee_login(data: dict):

    username = data.get("username")
    password = data.get("password")

    result = supabase.table("employees").select("*").match({
        "username": username,
        "password": password
    }).execute()

    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid employee login")

    employee = result.data[0]

    return {
        "success": True,
        "employee": employee
    }
