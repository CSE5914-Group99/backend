# Backend Service

This directory contains the FastAPI backend for the application. It provides RESTful APIs for course management, scheduling, and AI-powered agents.

## Deployed Environment

- **Base URL:** [https://g99project-477702.uc.r.appspot.com](https://g99project-477702.uc.r.appspot.com)
- **Swagger Documentation:** [https://g99project-477702.uc.r.appspot.com/docs](https://g99project-477702.uc.r.appspot.com/docs)

## Prerequisites

- **Python 3.10+**
- **Docker & Docker Compose** (Recommended for running the database)

## Local Development Setup

Follow these steps to set up the backend environment on your local machine.

### 1. Python Environment

Create a virtual environment to isolate dependencies:

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# macOS/Linux:
source venv/bin/activate
```

Install the required Python packages:

```bash
pip install -r requirements.txt
```

### 2. Environment Configuration

Create a `.env` file in the `backend` directory to store environment variables. You can use `.env.example` as a template.

```bash
# Copy example file (or manually create .env)
cp .env.example .env
```

**Recommended `.env` for Local Development:**

```ini
# Database Configuration (Connects to local Docker Postgres)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/backend
SYNC_MODELS=false

# AI & External Service Keys (Required for Agent features)
OPENAI_API_KEY=your_openai_key_here
TAVILY_API_KEY=your_tavily_key_here

# Reddit API (Optional, for Reddit search features)
REDDIT_USER_SCRIPT=your_reddit_client_id
REDDIT_SECRET=your_reddit_secret
```

### 3. Database Setup

The easiest way to run the database is using Docker Compose. This spins up a PostgreSQL instance configured for the project.

```bash
# Start the database container in the background
docker compose up -d db
```

*Note: This starts Postgres on port `5432` with user `postgres`, password `postgres`, and database `backend`.*

### 4. Database Migrations

Once the database is running, apply the migrations to create the necessary tables:

```bash
alembic upgrade head
```

### 5. Running the Server

Start the FastAPI development server:

```bash
uvicorn main:app --reload
```

- **API URL**: `http://localhost:8000`
- **Swagger Documentation**: `http://localhost:8000/docs` (Use this to test endpoints interactively)

## Docker Setup (Full Backend)

If you prefer to run both the API and Database in Docker (simulating production):

```bash
docker compose up --build
```

This will start both services. The API will still be accessible at `http://localhost:8000`.

## Project Structure

- **`agents/`**: AI agents logic (e.g., Class Grading, Schedule Grading).
- **`db/`**: Database configuration, SQLAlchemy models, and Alembic migrations.
- **`routers/`**: FastAPI route handlers (endpoints).
- **`schemas/`**: Pydantic models for data validation and serialization.
- **`services/`**: Business logic and integrations with external APIs (OSU Search, RateMyProfessor).
- **`main.py`**: Application entry point.
