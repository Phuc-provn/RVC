import { useRef, useCallback, useState } from 'react';

interface UseAudioStreamReturn {
  startCapture: (onAudioChunk: (buffer: ArrayBuffer) => void) => Promise<number>;
  stopCapture: () => void;
  playChunk: (int16Data: ArrayBuffer, sampleRate: number) => void;
  stopPlayback: () => void;
  inputLevel: number;
  outputLevel: number;
  isCapturing: boolean;
}

export function useAudioStream(): UseAudioStreamReturn {
  const audioContextRef = useRef<AudioContext | null>(null);
  const playbackContextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const scriptNodeRef = useRef<ScriptProcessorNode | null>(null);
  const analyserInputRef = useRef<AnalyserNode | null>(null);
  const analyserOutputRef = useRef<AnalyserNode | null>(null);
  const nextPlayTimeRef = useRef<number>(0);
  const inputLevelRafRef = useRef<number>(0);
  const outputLevelRafRef = useRef<number>(0);

  const [inputLevel, setInputLevel] = useState(0);
  const [outputLevel, setOutputLevel] = useState(0);
  const [isCapturing, setIsCapturing] = useState(false);

  const updateInputLevel = useCallback(() => {
    if (!analyserInputRef.current) return;
    const analyser = analyserInputRef.current;
    const data = new Uint8Array(analyser.fftSize);
    analyser.getByteTimeDomainData(data);

    let sum = 0;
    for (let i = 0; i < data.length; i++) {
      const val = (data[i] - 128) / 128;
      sum += val * val;
    }
    const rms = Math.sqrt(sum / data.length);
    const level = Math.min(1, rms * 3);
    setInputLevel(level);
    inputLevelRafRef.current = requestAnimationFrame(updateInputLevel);
  }, []);

  const updateOutputLevel = useCallback(() => {
    if (!analyserOutputRef.current) return;
    const analyser = analyserOutputRef.current;
    const data = new Uint8Array(analyser.fftSize);
    analyser.getByteTimeDomainData(data);

    let sum = 0;
    for (let i = 0; i < data.length; i++) {
      const val = (data[i] - 128) / 128;
      sum += val * val;
    }
    const rms = Math.sqrt(sum / data.length);
    const level = Math.min(1, rms * 3);
    setOutputLevel(level);
    outputLevelRafRef.current = requestAnimationFrame(updateOutputLevel);
  }, []);

  const startCapture = useCallback(async (onAudioChunk: (buffer: ArrayBuffer) => void): Promise<number> => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: 48000,
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
      },
    });

    streamRef.current = stream;

    const audioContext = new AudioContext({ sampleRate: 48000 });
    audioContextRef.current = audioContext;

    const source = audioContext.createMediaStreamSource(stream);
    sourceNodeRef.current = source;

    // Input analyser
    const analyserInput = audioContext.createAnalyser();
    analyserInput.fftSize = 2048;
    analyserInputRef.current = analyserInput;
    source.connect(analyserInput);

    // ScriptProcessor for capturing audio
    const scriptNode = audioContext.createScriptProcessor(4096, 1, 1);
    scriptNodeRef.current = scriptNode;

    scriptNode.onaudioprocess = (e: AudioProcessingEvent) => {
      const inputData = e.inputBuffer.getChannelData(0);
      const int16 = new Int16Array(inputData.length);
      for (let i = 0; i < inputData.length; i++) {
        int16[i] = Math.max(-32768, Math.min(32767, Math.round(inputData[i] * 32767)));
      }
      onAudioChunk(int16.buffer);
    };

    source.connect(scriptNode);
    // Connect to a muted gain node so Chrome fires onaudioprocess without playing raw mic back to speakers
    const muteGain = audioContext.createGain();
    muteGain.gain.value = 0;
    scriptNode.connect(muteGain);
    muteGain.connect(audioContext.destination);

    // Start input level monitoring
    inputLevelRafRef.current = requestAnimationFrame(updateInputLevel);

    // Create playback context
    const playbackContext = new AudioContext();
    playbackContextRef.current = playbackContext;

    // Output analyser
    const analyserOutput = playbackContext.createAnalyser();
    analyserOutput.fftSize = 2048;
    analyserOutputRef.current = analyserOutput;
    analyserOutput.connect(playbackContext.destination);

    // Start output level monitoring
    outputLevelRafRef.current = requestAnimationFrame(updateOutputLevel);

    nextPlayTimeRef.current = 0;
    setIsCapturing(true);

    return audioContext.sampleRate;
  }, [updateInputLevel, updateOutputLevel]);

  const stopCapture = useCallback(() => {
    // Stop input level monitoring
    if (inputLevelRafRef.current) {
      cancelAnimationFrame(inputLevelRafRef.current);
      inputLevelRafRef.current = 0;
    }

    // Stop output level monitoring
    if (outputLevelRafRef.current) {
      cancelAnimationFrame(outputLevelRafRef.current);
      outputLevelRafRef.current = 0;
    }

    // Disconnect script processor
    if (scriptNodeRef.current) {
      scriptNodeRef.current.disconnect();
      scriptNodeRef.current.onaudioprocess = null;
      scriptNodeRef.current = null;
    }

    // Disconnect source
    if (sourceNodeRef.current) {
      sourceNodeRef.current.disconnect();
      sourceNodeRef.current = null;
    }

    // Stop media stream tracks
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }

    // Close audio contexts
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    if (playbackContextRef.current) {
      playbackContextRef.current.close();
      playbackContextRef.current = null;
    }

    analyserInputRef.current = null;
    analyserOutputRef.current = null;
    nextPlayTimeRef.current = 0;
    setInputLevel(0);
    setOutputLevel(0);
    setIsCapturing(false);
  }, []);

  const playChunk = useCallback((int16Data: ArrayBuffer, sampleRate: number) => {
    const playbackContext = playbackContextRef.current;
    const analyserOutput = analyserOutputRef.current;
    if (!playbackContext || !analyserOutput) return;

    const int16Array = new Int16Array(int16Data);
    const float32 = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
      float32[i] = int16Array[i] / 32768;
    }

    const audioBuffer = playbackContext.createBuffer(1, float32.length, sampleRate);
    audioBuffer.getChannelData(0).set(float32);

    const source = playbackContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(analyserOutput);

    const now = playbackContext.currentTime;
    if (nextPlayTimeRef.current < now) {
      nextPlayTimeRef.current = now + 0.05;
    }
    source.start(nextPlayTimeRef.current);
    nextPlayTimeRef.current += audioBuffer.duration;
  }, []);

  const stopPlayback = useCallback(() => {
    nextPlayTimeRef.current = 0;
    setOutputLevel(0);
  }, []);

  return {
    startCapture,
    stopCapture,
    playChunk,
    stopPlayback,
    inputLevel,
    outputLevel,
    isCapturing,
  };
}
