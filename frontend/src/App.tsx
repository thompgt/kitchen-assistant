import { StatusBar } from './components/StatusBar'
import { InstructionCard } from './components/InstructionCard'
import { IngredientChecklist } from './components/IngredientChecklist'
import { ActiveTimerBoard } from './components/ActiveTimerBoard'
import { TranscriptPane } from './components/TranscriptPane'
import { MicButton } from './components/MicButton'
import { CameraPreview } from './components/CameraPreview'
import { useVoiceSocket } from './hooks/useVoiceSocket'

export default function App() {
  const { sendText, toggleMic, toggleCamera, camVideoRef } = useVoiceSocket()

  return (
    <div className="flex min-h-screen flex-col bg-kitchen-bg text-white">
      <StatusBar />
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 p-6">
        <InstructionCard />
        <div className="grid gap-6 md:grid-cols-2">
          <IngredientChecklist />
          <ActiveTimerBoard />
        </div>
        <TranscriptPane />
      </main>
      <CameraPreview videoRef={camVideoRef} />
      <MicButton onToggle={toggleMic} onToggleCamera={toggleCamera} onSendText={sendText} />
    </div>
  )
}
