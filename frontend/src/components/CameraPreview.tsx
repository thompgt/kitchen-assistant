import type { RefObject } from 'react'
import { useSessionStore } from '../store/useSessionStore'

interface CameraPreviewProps {
  videoRef: RefObject<HTMLVideoElement | null>
}

export function CameraPreview({ videoRef }: CameraPreviewProps) {
  const cameraLive = useSessionStore((s) => s.cameraLive)

  return (
    <video
      ref={videoRef}
      autoPlay
      muted
      playsInline
      className={`fixed bottom-24 right-4 w-40 rounded-lg border border-kitchen-accent bg-black ${
        cameraLive ? 'block' : 'hidden'
      }`}
    />
  )
}
