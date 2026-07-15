// Kitchen Assistant browser client.
// Binary WS frames = PCM16 audio (16 kHz up, 24 kHz down); JSON text frames
// carry the envelopes documented in ARCHITECTURE.md.

const sessionId = crypto.randomUUID().slice(0, 8);
const wsUrl = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/voice/${sessionId}`;

const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const transcriptEl = document.getElementById("transcript");
const timersEl = document.getElementById("timers");
const micBtn = document.getElementById("mic-btn");
const camBtn = document.getElementById("cam-btn");
const camPreview = document.getElementById("cam-preview");
const textInput = document.getElementById("text-input");

let ws = null;
let lastLine = { role: null, el: null };

function setStatus(status) {
  statusDot.className = status;
  statusText.textContent = status;
}

function appendTranscript(role, text) {
  if (lastLine.role !== role) {
    const el = document.createElement("div");
    el.className = `line ${role}`;
    transcriptEl.appendChild(el);
    lastLine = { role, el };
  }
  lastLine.el.textContent += text;
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
}

// --- timers ------------------------------------------------------------

let activeTimers = {}; // id -> {label, start_time, duration_seconds}

function renderTimers() {
  timersEl.textContent = "";
  const now = Date.now();
  for (const t of Object.values(activeTimers)) {
    const end = new Date(t.start_time).getTime() + t.duration_seconds * 1000;
    const left = Math.ceil((end - now) / 1000);
    const chip = document.createElement("span");
    chip.className = "timer-chip" + (left <= 0 ? " expired" : "");
    chip.textContent = left > 0
      ? `⏱ ${t.label} — ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`
      : `⏱ ${t.label} — done`;
    timersEl.appendChild(chip);
  }
}
setInterval(renderTimers, 1000);

// --- websocket ----------------------------------------------------------

function handleEnvelope(envelope) {
  switch (envelope.type) {
    case "session.status":
      setStatus(envelope.status);
      break;
    case "transcript.user":
      appendTranscript("user", envelope.text);
      break;
    case "transcript.agent":
      appendTranscript("agent", envelope.text);
      break;
    case "interrupted":
      flushPlayback();
      lastLine = { role: null, el: null };
      break;
    case "state.snapshot":
      activeTimers = envelope.state.active_timers || {};
      renderTimers();
      break;
    case "timer.update":
    case "timer.expired":
      if (envelope.timer) activeTimers[envelope.timer.id] = envelope.timer;
      renderTimers();
      break;
    case "error":
      appendTranscript("error", envelope.message);
      break;
  }
}

function connect() {
  ws = new WebSocket(wsUrl);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => { micBtn.disabled = false; camBtn.disabled = false; };
  ws.onmessage = (event) => {
    if (event.data instanceof ArrayBuffer) {
      enqueueAudio(event.data);
    } else {
      handleEnvelope(JSON.parse(event.data));
    }
  };
  ws.onclose = () => {
    setStatus("closed");
    micBtn.disabled = true;
    camBtn.disabled = true;
  };
}
connect();

textInput.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || !textInput.value.trim() || !ws || ws.readyState !== 1) return;
  const text = textInput.value.trim();
  ws.send(JSON.stringify({ type: "user.text", text }));
  appendTranscript("user", text);
  lastLine = { role: null, el: null }; // typed input is a complete utterance
  textInput.value = "";
});

// --- mic capture: 16 kHz PCM16 uplink ------------------------------------

let captureCtx = null;

async function startMic() {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  });
  captureCtx = new AudioContext({ sampleRate: 16000 });
  await captureCtx.audioWorklet.addModule("/static/pcm-worklet.js");
  const source = captureCtx.createMediaStreamSource(stream);
  const worklet = new AudioWorkletNode(captureCtx, "pcm-capture");
  worklet.port.onmessage = (event) => {
    if (ws && ws.readyState === 1) ws.send(event.data);
  };
  source.connect(worklet);
  micBtn.textContent = "⏹ Stop";
  micBtn.classList.add("live");
}

async function stopMic() {
  if (captureCtx) {
    await captureCtx.close();
    captureCtx = null;
  }
  micBtn.textContent = "🎤 Start";
  micBtn.classList.remove("live");
}

micBtn.addEventListener("click", () => (captureCtx ? stopMic() : startMic()));

// --- camera: throttled JPEG frames for doneness checks ---------------------

const FRAME_INTERVAL_MS = 1500;
let camStream = null;
let camFrameTimer = null;
const camCanvas = document.createElement("canvas");

async function startCamera() {
  camStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
  camPreview.srcObject = camStream;
  camPreview.classList.add("live");
  camBtn.textContent = "⏹ Camera";
  camBtn.classList.add("live");

  camFrameTimer = setInterval(() => {
    if (!ws || ws.readyState !== 1 || camPreview.videoWidth === 0) return;
    camCanvas.width = camPreview.videoWidth;
    camCanvas.height = camPreview.videoHeight;
    camCanvas.getContext("2d").drawImage(camPreview, 0, 0);
    camCanvas.toBlob(
      (blob) => {
        if (!blob) return;
        const reader = new FileReader();
        reader.onloadend = () => {
          const base64 = reader.result.split(",")[1];
          if (ws && ws.readyState === 1) {
            ws.send(JSON.stringify({ type: "video.frame", data: base64, mime_type: "image/jpeg" }));
          }
        };
        reader.readAsDataURL(blob);
      },
      "image/jpeg",
      0.7
    );
  }, FRAME_INTERVAL_MS);
}

function stopCamera() {
  if (camFrameTimer) {
    clearInterval(camFrameTimer);
    camFrameTimer = null;
  }
  if (camStream) {
    for (const track of camStream.getTracks()) track.stop();
    camStream = null;
  }
  camPreview.srcObject = null;
  camPreview.classList.remove("live");
  camBtn.textContent = "📷 Camera";
  camBtn.classList.remove("live");
}

camBtn.addEventListener("click", () => (camStream ? stopCamera() : startCamera()));

// --- playback: 24 kHz queue with barge-in flush ---------------------------

const playbackCtx = new AudioContext({ sampleRate: 24000 });
let nextStartTime = 0;
let scheduledSources = [];

function enqueueAudio(arrayBuffer) {
  if (playbackCtx.state === "suspended") playbackCtx.resume();
  const int16 = new Int16Array(arrayBuffer);
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768;

  const buffer = playbackCtx.createBuffer(1, float32.length, 24000);
  buffer.copyToChannel(float32, 0);
  const source = playbackCtx.createBufferSource();
  source.buffer = buffer;
  source.connect(playbackCtx.destination);

  const startAt = Math.max(nextStartTime, playbackCtx.currentTime);
  source.start(startAt);
  nextStartTime = startAt + buffer.duration;
  scheduledSources.push(source);
  source.onended = () => {
    scheduledSources = scheduledSources.filter((s) => s !== source);
  };
}

function flushPlayback() {
  for (const source of scheduledSources) {
    try { source.stop(); } catch (_) { /* already ended */ }
  }
  scheduledSources = [];
  nextStartTime = 0;
}
