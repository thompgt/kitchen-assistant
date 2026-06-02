# Frontend Development Plan: Kitchen Assistant (Voice-First UX)

## 1. Architectural Vision
The frontend is a "Head-up Display" (HUD) for the Executive Sous-Chef. It must be high-contrast, large-format, and optimized for glancing from across a kitchen. It must handle bi-directional binary audio streaming with sub-50ms overhead.

### Tech Stack
- **Framework**: React 18+ (Vite for fast HMR)
- **Language**: TypeScript (Strict Mode)
- **State Management**: Zustand (Lightweight, ideal for high-frequency updates)
- **Styling**: Tailwind CSS (Utility-first, high performance)
- **Audio Processing**: Web Audio API (Worklets for low-latency capture)
- **Visualization**: Framer Motion & Canvas (GPU-accelerated wave-forms)

---

## 2. Phase 6: Core Implementation Roadmap

### Phase 6.1: Audio Ingestion Layer (Capture)
- **AudioWorklet Integration**: Implement a custom processor to capture 16kHz Mono Linear16 audio chunks.
- **WebSocket Bridge**: Create a persistent `useSocket` hook that handles binary egress of audio and JSON ingress of transcripts/state.
- **Noise Visualization**: Implement a real-time dB meter to show the chef if they are being heard over ambient noise.

### Phase 6.2: Dynamic HUD & State Synchronization
- **State Mirroring**: The UI should precisely reflect the `RecipeState` Pydantic model from the backend.
- **Components**:
    - `ActiveTimerBoard`: Grid of running timers with circular progress visualizers.
    - `InstructionCard`: High-contrast typography for the current recipe step.
    - `IngredientChecklist`: Auto-scaled quantities based on the multiplier.
- **Transitions**: Smooth, non-distracting animations when steps change.

### Phase 6.3: Voice Feedback System (Egress)
- **Audio Buffer Management**: Queue incoming audio chunks from the backend (Cartesia/ElevenLabs) for gapless playback.
- **Interruption Handling**: Stop local playback immediately when the chef starts speaking (Barge-in).

---

## 3. Design Principles (Kitchen-Specific)

| Principle | Implementation |
| :--- | :--- |
| **Glanceability** | Minimum 24pt font size for instructions; color-coded timer urgency. |
| **Zero-Touch** | Every UI change must be achievable via voice. No "Click to Start" after initial auth. |
| **High Contrast** | Dark mode by default (Dark Grey background #121212) to reduce glare in bright kitchens. |
| **Feedback Loops** | Visual "Pulsing" icon when the LLM is thinking to prevent "stale" silence. |

---

## 4. Feature Backlog (Post-MVP)
- **Multimodal Support**: Upload a photo of a recipe from the UI to seed the DuckDB.
- **Timer Sound Selection**: High-pitched vs. low-frequency tones to cut through different ambient noises (vent hoods vs. frying).
- **Multiple Device Sync**: Sync state between a tablet and a smartwatch.

---

## 5. Implementation Commands (Next Steps)
```bash
# Initialize Vite Project
npm create vite@latest frontend -- --template react-ts

# Install Dependencies
npm install lucide-react zustand framer-motion tailwindcss postcss autoprefixer
npx tailwindcss init -p
```
