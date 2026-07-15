import { useCallback, useEffect, useRef } from 'react'
import { useSessionStore } from '../store/useSessionStore'
import type { ServerEnvelope } from '../types'

// Same binary/JSON WS protocol as static/app.js — binary frames are PCM16
// audio (16 kHz up, 24 kHz down), JSON text frames carry the envelopes
// documented in ARCHITECTURE.md.

function makeSessionId(): string {
  return crypto.randomUUID().slice(0, 8)
}

const CAMERA_FRAME_INTERVAL_MS = 1500

export function useVoiceSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const captureCtxRef = useRef<AudioContext | null>(null)
  const playbackCtxRef = useRef<AudioContext | null>(null)
  const nextStartTimeRef = useRef(0)
  const scheduledSourcesRef = useRef<AudioBufferSourceNode[]>([])
  const camStreamRef = useRef<MediaStream | null>(null)
  const camVideoRef = useRef<HTMLVideoElement | null>(null)
  const camCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const camTimerRef = useRef<number | null>(null)

  const setStatus = useSessionStore((s) => s.setStatus)
  const setMicLive = useSessionStore((s) => s.setMicLive)
  const setCameraLive = useSessionStore((s) => s.setCameraLive)
  const appendTranscript = useSessionStore((s) => s.appendTranscript)
  const resetTranscriptCursor = useSessionStore((s) => s.resetTranscriptCursor)
  const applySnapshot = useSessionStore((s) => s.applySnapshot)
  const upsertTimer = useSessionStore((s) => s.upsertTimer)

  const flushPlayback = useCallback(() => {
    for (const source of scheduledSourcesRef.current) {
      try {
        source.stop()
      } catch {
        // already ended
      }
    }
    scheduledSourcesRef.current = []
    nextStartTimeRef.current = 0
  }, [])

  const enqueueAudio = useCallback((arrayBuffer: ArrayBuffer) => {
    if (!playbackCtxRef.current) {
      playbackCtxRef.current = new AudioContext({ sampleRate: 24000 })
    }
    const ctx = playbackCtxRef.current
    if (ctx.state === 'suspended') ctx.resume()

    const int16 = new Int16Array(arrayBuffer)
    const float32 = new Float32Array(int16.length)
    for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768

    const buffer = ctx.createBuffer(1, float32.length, 24000)
    buffer.copyToChannel(float32, 0)
    const source = ctx.createBufferSource()
    source.buffer = buffer
    source.connect(ctx.destination)

    const startAt = Math.max(nextStartTimeRef.current, ctx.currentTime)
    source.start(startAt)
    nextStartTimeRef.current = startAt + buffer.duration
    scheduledSourcesRef.current.push(source)
    source.onended = () => {
      scheduledSourcesRef.current = scheduledSourcesRef.current.filter((s) => s !== source)
    }
  }, [])

  const handleEnvelope = useCallback(
    (envelope: ServerEnvelope) => {
      switch (envelope.type) {
        case 'session.status':
          setStatus(envelope.status)
          break
        case 'transcript.user':
          appendTranscript('user', envelope.text)
          break
        case 'transcript.agent':
          appendTranscript('agent', envelope.text)
          break
        case 'interrupted':
          flushPlayback()
          resetTranscriptCursor()
          break
        case 'state.snapshot':
          applySnapshot(envelope.state)
          break
        case 'timer.update':
        case 'timer.expired':
          if (envelope.timer) upsertTimer(envelope.timer)
          break
        case 'error':
          appendTranscript('error', envelope.message, { newLine: true })
          break
      }
    },
    [appendTranscript, applySnapshot, flushPlayback, resetTranscriptCursor, setStatus, upsertTimer]
  )

  useEffect(() => {
    const sessionId = makeSessionId()
    const wsUrl = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/voice/${sessionId}`
    const ws = new WebSocket(wsUrl)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        enqueueAudio(event.data)
      } else {
        handleEnvelope(JSON.parse(event.data))
      }
    }
    ws.onclose = () => setStatus('closed')

    return () => {
      ws.close()
      wsRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const sendText = useCallback(
    (text: string) => {
      const ws = wsRef.current
      if (!text.trim() || !ws || ws.readyState !== WebSocket.OPEN) return
      ws.send(JSON.stringify({ type: 'user.text', text }))
      appendTranscript('user', text, { newLine: true })
      resetTranscriptCursor()
    },
    [appendTranscript, resetTranscriptCursor]
  )

  const startMic = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    })
    const ctx = new AudioContext({ sampleRate: 16000 })
    captureCtxRef.current = ctx
    await ctx.audioWorklet.addModule(`${import.meta.env.BASE_URL}pcm-worklet.js`)
    const source = ctx.createMediaStreamSource(stream)
    const worklet = new AudioWorkletNode(ctx, 'pcm-capture')
    worklet.port.onmessage = (event) => {
      const ws = wsRef.current
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(event.data)
    }
    source.connect(worklet)
    setMicLive(true)
  }, [setMicLive])

  const stopMic = useCallback(async () => {
    if (captureCtxRef.current) {
      await captureCtxRef.current.close()
      captureCtxRef.current = null
    }
    setMicLive(false)
  }, [setMicLive])

  const toggleMic = useCallback(() => {
    if (captureCtxRef.current) {
      void stopMic()
    } else {
      void startMic()
    }
  }, [startMic, stopMic])

  // --- camera: throttled JPEG frames for doneness checks -----------------

  const startCamera = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment' },
    })
    camStreamRef.current = stream
    const video = camVideoRef.current
    if (video) video.srcObject = stream

    if (!camCanvasRef.current) camCanvasRef.current = document.createElement('canvas')
    const canvas = camCanvasRef.current

    camTimerRef.current = window.setInterval(() => {
      const ws = wsRef.current
      const v = camVideoRef.current
      if (!ws || ws.readyState !== WebSocket.OPEN || !v || v.videoWidth === 0) return
      canvas.width = v.videoWidth
      canvas.height = v.videoHeight
      canvas.getContext('2d')?.drawImage(v, 0, 0)
      canvas.toBlob(
        (blob) => {
          if (!blob) return
          const reader = new FileReader()
          reader.onloadend = () => {
            const result = reader.result as string
            const base64 = result.split(',')[1]
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: 'video.frame', data: base64, mime_type: 'image/jpeg' }))
            }
          }
          reader.readAsDataURL(blob)
        },
        'image/jpeg',
        0.7
      )
    }, CAMERA_FRAME_INTERVAL_MS)

    setCameraLive(true)
  }, [setCameraLive])

  const stopCamera = useCallback(() => {
    if (camTimerRef.current !== null) {
      clearInterval(camTimerRef.current)
      camTimerRef.current = null
    }
    if (camStreamRef.current) {
      for (const track of camStreamRef.current.getTracks()) track.stop()
      camStreamRef.current = null
    }
    if (camVideoRef.current) camVideoRef.current.srcObject = null
    setCameraLive(false)
  }, [setCameraLive])

  const toggleCamera = useCallback(() => {
    if (camStreamRef.current) {
      stopCamera()
    } else {
      void startCamera()
    }
  }, [startCamera, stopCamera])

  return { sendText, toggleMic, toggleCamera, camVideoRef }
}
