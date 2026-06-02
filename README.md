# Kitchen Assistant

Real-time voice agent for high-noise kitchen environments. Built with FastAPI, WebSocket audio streaming, and LLM-powered orchestration.

## Features
- **Hands-Free Operation**: Designed for noisy kitchens (sizzling, water).
- **Real-Time Streaming**: Low-latency audio ingestion and synthesis.
- **Smart Orchestration**: LLM-driven state management for timers and recipe scaling.

## Project Structure
- `backend/`: FastAPI server, state management, and API routes.
- `workplan.md`: Detailed engineering roadmap and milestones.

## Setup
1. `cd backend`
2. `python -m venv venv`
3. `.\venv\Scripts\activate`
4. `pip install -r requirements.txt`
5. `python -m uvicorn backend.main:app --reload`
