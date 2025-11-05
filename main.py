from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from routers import courses_router, schedule_router, users_router
from config import settings
from db import Base, init_models

app = FastAPI(
    title="Microservices API",
    description="A simple FastAPI microservices setup",
    version="1.0.0",
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


@app.on_event("startup")
async def on_startup() -> None:
    await init_models(Base.metadata)


if __name__ == "__main__":
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
