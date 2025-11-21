from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from routers import (
    course_search_router,
    courses_router,
    rate_my_professor_router,
    reddit_router,
    schedule_router,
    users_router,
    generate_schedule_router,
)
from config import settings
from db import Base, init_models


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Optionally sync models during startup (useful for local dev or tests without migrations).
    if settings.sync_models:
        await init_models(Base.metadata)
    yield

app = FastAPI(
    title="Microservices API",
    description="A simple FastAPI microservices setup",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Welcome to the Microservices API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

app.include_router(users_router)
app.include_router(courses_router)
app.include_router(schedule_router)
app.include_router(generate_schedule_router)
app.include_router(course_search_router)
app.include_router(rate_my_professor_router)
app.include_router(reddit_router)


if __name__ == "__main__":
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
