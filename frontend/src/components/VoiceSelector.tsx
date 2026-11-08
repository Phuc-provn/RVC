import type { Voice } from '../services/api';

interface VoiceSelectorProps {
  voices: Voice[];
  selectedVoice: Voice | null;
  onSelect: (voice: Voice) => void;
  disabled: boolean;
  defaultModel: string;
}

export default function VoiceSelector({
  voices,
  selectedVoice,
  onSelect,
  disabled,
  defaultModel,
}: VoiceSelectorProps) {
  return (
    <div>
      <label
        htmlFor="voice-select"
        className="block text-sm font-semibold text-gray-700 mb-2"
      >
        Target Voice
      </label>
      <select
        id="voice-select"
        value={selectedVoice?.id ?? ''}
        onChange={(e) => {
          const voice = voices.find((v) => v.id === e.target.value);
          if (voice) onSelect(voice);
        }}
        disabled={disabled}
        className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-gray-800 text-sm
                   focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500
                   disabled:opacity-50 disabled:cursor-not-allowed
                   transition-colors"
      >
        <option value="" disabled>
          Select a singer...
        </option>
        {voices.map((voice) => (
          <option key={voice.id} value={voice.id}>
            {voice.name}
          </option>
        ))}
      </select>
      {defaultModel && (
        <p className="mt-1.5 text-xs text-gray-400">Model: {defaultModel}</p>
      )}
    </div>
  );
}
