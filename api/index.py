from typing import List
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request as FastAPIRequest
from fastapi.responses import StreamingResponse
from openai import OpenAI
from vercel import oidc
from vercel.headers import set_headers
from main import app


load_dotenv(".env.local")


@app.get("/hello")
async def hello_world():
    return {"message": "Hello, world!"}
