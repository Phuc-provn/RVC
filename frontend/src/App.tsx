import { useState, useEffect, useRef, useCallback } from 'react';
import Header from './components/Header';
import VoiceSelector from './components/VoiceSelector';
import MicrophoneInput from './components/MicrophoneInput';
import AudioOutput from './components/AudioOutput';
import StatusDisplay from './components/StatusDisplay';
import { useWebSocket } from './hooks/useWebSocket';
import { useAudioStream } from './hooks/useAudioStream';
import { fetchVoices, healthCheck, type Voice } from './services/api';

export default function App() {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [selectedVoice, setSelectedVoice] = useState<Voice | null>(null);
  const [defaultModel, setDefaultModel] = useState('');
  const [backendOnline, setBackendOnline] = useState(false);
  const [isInitializing, setIsInitializing] = useState(false);
  const [isConverting, setIsConverting] = useState(false);
  const [status, setStatus] = useState('Ready');
  const [error, setError] = useState<string | null>(null);
  const [modelSampleRate, setModelSampleRate] = useState(0);
  const [sessionDuration, setSessionDuration] = useState(0);
  const [chunksProcessed, setChunksProcessed] = useState(0);

  const durationTimerRef = useRef<number | null>(null);
  const modelSampleRateRef = useRef<number>(0);
  modelSampleRateRef.current = modelSampleRate;
  const isStreamingRef = useRef(false);
  const selectedVoiceRef = useRef<Voice | null>(null);
  selectedVoiceRef.current = selectedVoice;
  const defaultModelRef = useRef<string>('');
  defaultModelRef.current = defaultModel;
  const sendJsonRef = useRef<((data: Record<string, unknown>) => void) | null>(null);

  // Audio streaming hook
  const {
    startCapture,
    stopCapture,
    playChunk,
    stopPlayback,
    inputLevel,
    outputLevel,
  } = useAudioStream();

  // Handle incoming WebSocket messages
  const handleWsMessage = useCallback(
    (data: ArrayBuffer | string) => {
      if (typeof data === 'string') {
        try {
          const msg = JSON.parse(data);
          if (msg.type === 'init') {
            const sr = msg.sample_rate || 40000;
            setModelSampleRate(sr);
            setIsInitializing(false);
            setIsConverting(true);
            isStreamingRef.current = true;
            setStatus('Live conversion active');
            setError(null);
          } else if (msg.type === 'status') {
            setStatus(msg.status);
          } else if (msg.type === 'error') {
            setError(msg.message);
            setIsInitializing(false);
            setIsConverting(false);
            isStreamingRef.current = false;
            stopCapture();
            stopPlayback();
          } else if (msg.type === 'stopped') {
            setIsConverting(false);
            setIsInitializing(false);
            isStreamingRef.current = false;
            setStatus('Stopped');
          }
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e);
        }
      } else if (data instanceof ArrayBuffer) {
        // Binary converted audio chunk from the model
        setChunksProcessed((prev) => prev + 1);
        playChunk(data, modelSampleRateRef.current || 40000);
      }
    },
    [playChunk, stopCapture, stopPlayback]
  );

  const handleWsOpen = useCallback(() => {
    // Once WS connects, send start message
    const voice = selectedVoiceRef.current;
    const model = defaultModelRef.current;
    if (voice) {
      setStatus('Initializing voice model on GPU...');
      sendJsonRef.current?.({
        type: 'start',
        voice_id: voice.speaker_name,
        model: model,
        sample_rate: 48000,
      });
    }
  }, []);

  const handleWsClose = useCallback(() => {
    isStreamingRef.current = false;
    setIsConverting(false);
    setIsInitializing(false);
    stopCapture();
    stopPlayback();
  }, [stopCapture, stopPlayback]);

  const handleWsError = useCallback((msg: string) => {
    isStreamingRef.current = false;
    setError(msg);
    setIsInitializing(false);
    setIsConverting(false);
  }, []);

  const { connect, disconnect, sendJson, sendBinary, isConnected } =
    useWebSocket(handleWsMessage, handleWsOpen, handleWsClose, handleWsError);
  sendJsonRef.current = sendJson;

  // Poll backend health and fetch voices on load
  useEffect(() => {
    async function init() {
      const isUp = await healthCheck();
      setBackendOnline(isUp);
      if (isUp) {
        try {
          const res = await fetchVoices();
          setVoices(res.voices);
          setDefaultModel(res.default_model);
          if (res.voices.length > 0) {
            setSelectedVoice(res.voices[0]);
          }
        } catch (err: unknown) {
          const message = err instanceof Error ? err.message : 'Unknown error';
          setError(`Failed to load voices: ${message}`);
        }
      }
    }
    init();

    // Check health every 5 seconds
    const interval = setInterval(async () => {
      const up = await healthCheck();
      setBackendOnline(up);
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  // Duration timer
  useEffect(() => {
    if (isConverting) {
      setSessionDuration(0);
      setChunksProcessed(0);
      durationTimerRef.current = window.setInterval(() => {
        setSessionDuration((prev) => prev + 1);
      }, 1000);
    } else {
      if (durationTimerRef.current) {
        clearInterval(durationTimerRef.current);
        durationTimerRef.current = null;
      }
    }
    return () => {
      if (durationTimerRef.current) {
        clearInterval(durationTimerRef.current);
      }
    };
  }, [isConverting]);

  // Start conversion
  const handleStart = async () => {
    if (!selectedVoice) {
      setError('Please select a target singer voice first.');
      return;
    }

    setError(null);
    setIsInitializing(true);
    setStatus('Requesting microphone access...');

    try {
      // 1. Capture microphone audio (will only transmit once session is initialized)
      await startCapture((chunk: ArrayBuffer) => {
        if (isStreamingRef.current) {
          sendBinary(chunk);
        }
      });

      setStatus('Connecting to voice conversion engine...');

      // 2. Connect WebSocket (the handleWsOpen callback will send 'start')
      connect();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Microphone error';
      setIsInitializing(false);
      setError(`Microphone error: ${message}. Please allow microphone access.`);
      setStatus('Ready');
      stopCapture();
    }
  };

  // Stop conversion
  const handleStop = () => {
    setStatus('Stopping...');
    sendJson({ type: 'stop' });
    stopCapture();
    stopPlayback();
    disconnect();
    setIsConverting(false);
    setIsInitializing(false);
    setStatus('Ready');
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 flex flex-col font-sans">
      <Header isConnected={backendOnline || isConnected} isConnecting={isInitializing} />

      <main className="flex-1 max-w-6xl w-full mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
        {/* Error banner */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl flex items-start justify-between gap-3 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-red-500 font-bold">⚠️</span>
              <span>{error}</span>
            </div>
            <button
              onClick={() => setError(null)}
              className="text-red-400 hover:text-red-600 font-bold px-1"
            >
              ✕
            </button>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* CARD 1: Real-Time Voice Conversion (Main workspace) */}
          <div className="lg:col-span-7 bg-white rounded-2xl p-6 shadow-sm border border-slate-200/80 space-y-6">
            <div>
              <h2 className="text-lg font-bold text-slate-900 tracking-tight">
                Real-Time Voice Conversion
              </h2>
              <p className="text-sm text-slate-500 mt-1">
                Sing or speak into your microphone to hear your voice transformed live.
              </p>
            </div>

            {/* Quick instructions */}
            <div className="bg-teal-50/60 border border-teal-100 rounded-xl p-4 text-xs sm:text-sm text-slate-700 space-y-1.5 leading-relaxed">
              <p className="font-semibold text-teal-900 flex items-center gap-1.5">
                <span>💡</span> Quick Steps
              </p>
              <ol className="list-decimal list-inside space-y-1 text-slate-600 pl-1">
                <li>Select a target singer voice on the right.</li>
                <li>Allow microphone access when prompted.</li>
                <li>Click <strong>Start Conversion</strong> and begin singing.</li>
                <li>Listen to your converted voice through headphones.</li>
                <li>Click <strong>Stop</strong> when finished.</li>
              </ol>
            </div>

            {/* Microphone Input Component */}
            <MicrophoneInput
              isConverting={isConverting}
              isInitializing={isInitializing}
              inputLevel={inputLevel}
              onStart={handleStart}
              onStop={handleStop}
              disabled={!backendOnline || !selectedVoice}
            />

            {/* Converted Live Audio Output Component */}
            <AudioOutput
              outputLevel={outputLevel}
              isActive={isConverting && chunksProcessed > 0}
            />
          </div>

          {/* CARD 2: Voice Settings & Session Status */}
          <div className="lg:col-span-5 bg-white rounded-2xl p-6 shadow-sm border border-slate-200/80 space-y-6">
            <div>
              <h2 className="text-lg font-bold text-slate-900 tracking-tight">
                Voice Settings
              </h2>
              <p className="text-sm text-slate-500 mt-1">
                Configure your target singer model and view live session details.
              </p>
            </div>

            {/* Voice Selector */}
            <VoiceSelector
              voices={voices}
              selectedVoice={selectedVoice}
              onSelect={setSelectedVoice}
              disabled={isConverting || isInitializing}
              defaultModel={defaultModel}
            />

            <hr className="border-slate-100" />

            {/* Live Status Display */}
            <StatusDisplay
              status={status}
              error={error}
              selectedVoiceName={selectedVoice?.name || ''}
              modelSampleRate={modelSampleRate}
              sessionDuration={sessionDuration}
              chunksProcessed={chunksProcessed}
              isConverting={isConverting}
            />
          </div>
        </div>
      </main>

      <footer className="border-t border-slate-200 bg-white py-4 text-center text-xs text-slate-400">
        RVC Singing Voice Conversion • Powered by AI
      </footer>
    </div>
  );
}
