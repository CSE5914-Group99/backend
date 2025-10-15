from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import user_router, product_router
import uvicorn
from config import settings
from db import lifespan 

app = FastAPI(
    title="Microservices API",
    description="A simple FastAPI microservices setup",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Welcome to the Microservices API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

app.include_router(user_router)
app.include_router(product_router)

if __name__ == "__main__":
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
