# 👨‍🍳 Kitchen Assistant: Executive Sous-Chef AI

A high-performance, real-time, hands-free kitchen voice assistant powered by **Google Gemini 1.5 Flash**, **FastAPI**, and **DuckDB**. Designed for the heat of the kitchen, it handles low-latency audio streaming, complex tool orchestration, and multimodal recipe extraction.

---

## 🏗️ System Architecture

The Kitchen Assistant operates on a "Glass-to-Glass" (G2G) latency target of <800ms. It uses a bi-directional WebSocket pipeline to bridge the chef's voice to Gemini's reasoning engine.

![App Architecture](./assets/architecture.png)
*(Architecture diagram showing: Client -> WebSocket -> STT -> Gemini (Function Calling) -> TTS -> Client)*

### Core Components:
- **Orchestrator (Gemini 1.5 Flash)**: The "brain" that processes transcripts, maintains session history, and triggers function calling.
- **Streaming Pipeline**: Async WebSocket handlers for binary audio ingestion (PCM16) and egress.
- **Cooking Tools**: Native Python helpers for timers, unit conversions, and recipe scaling.
- **Persistence Layer**: DuckDB for high-speed recipe lookups and session state caching.

---

## ✨ Key Features

- **🎙️ Hands-Free Control**: Complete kitchen management via voice. No touch required.
- **⏱️ Multi-Timer Management**: Set, label, and track multiple overlapping timers simultaneously.
- **⚖️ Dynamic Recipe Scaling**: Instant ingredient recalculation (e.g., "Double this recipe").
- **👁️ Multimodal Vision**: Extract recipes from photos of cookbooks or identify ingredients on your counter.
- **📊 Interactive Research**: In-depth Jupyter notebooks for recipe EDA and multimodal testing.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- [Poetry](https://python-poetry.org/)
- Google AI (Gemini) API Key

### Installation
```bash
# Clone the repository
git clone https://github.com/thompgt/kitchen-assistant.git
cd kitchen-assistant

# Install dependencies
poetry install

# Configure environment
cp .env.example .env
# Add your GOOGLE_API_KEY to .env
```

### Running the Assistant
```bash
# Start the FastAPI Backend
poetry run uvicorn app.main:app --reload
```

---

## 📓 Research & Development

The project includes advanced research notebooks in the `notebooks/` folder:
1. `01_recipe_eda.ipynb`: Visual analytics of the recipe database using Seaborn/DuckDB.
2. `02_multimodal_practice.ipynb`: Testing Gemini Vision for ingredient recognition.
3. `03_tool_implementation.ipynb`: Edge-case testing for cooking logic.

---

## 🛠️ Tech Stack

- **LLM**: Google Gemini 1.5 Flash
- **API**: FastAPI (Asynchronous)
- **Database**: DuckDB (Persistent SQL)
- **Package Manager**: Poetry
- **DevOps**: GitHub Actions (Planned)

---

## 📜 License
MIT License. Created by [thompgt](https://github.com/thompgt).
