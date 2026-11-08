interface MicrophoneInputProps {
  isConverting: boolean;
  isInitializing: boolean;
  inputLevel: number;
  onStart: () => void;
  onStop: () => void;
  disabled: boolean;
}

export default function MicrophoneInput({
  isConverting,
  isInitializing,
  inputLevel,
  onStart,
  onStop,
  disabled,
}: MicrophoneInputProps) {
  const levelPercent = Math.round(inputLevel * 100);

  return (
    <div className="bg-gray-50 rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-lg" role="img" aria-label="microphone">
          🎤
        </span>
        <h3 className="text-sm font-semibold text-gray-700">Microphone Input</h3>
        {isConverting && (
          <span className="ml-auto flex items-center gap-1.5 text-xs text-red-500 font-medium animate-pulse-recording">
            <span className="inline-block w-2 h-2 rounded-full bg-red-500" />
            Recording
          </span>
        )}
      </div>

      {/* Level bar */}
      <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
        <div
          className="level-bar-fill h-full rounded-full"
          style={{
            width: `${levelPercent}%`,
            background: 'linear-gradient(90deg, #22c55e, #16a34a)',
          }}
        />
      </div>

      {/* Buttons */}
      <div className="flex gap-3">
        {!isConverting ? (
          <button
            onClick={onStart}
            disabled={disabled || isInitializing}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg
                       bg-teal-600 text-white font-semibold text-sm
                       hover:bg-teal-700 active:bg-teal-800
                       disabled:opacity-50 disabled:cursor-not-allowed
                       transition-colors shadow-sm"
          >
            {isInitializing ? (
              <>
                <svg
                  className="animate-spin h-4 w-4"
                  viewBox="0 0 24 24"
                  fill="none"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
                  />
                </svg>
                Loading AI Model...
              </>
            ) : (
              <>🔴 Start Conversion</>
            )}
          </button>
        ) : (
          <button
            onClick={onStop}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg
                       bg-red-500 text-white font-semibold text-sm
                       hover:bg-red-600 active:bg-red-700
                       transition-colors shadow-sm"
          >
            ⬛ Stop Conversion
          </button>
        )}
      </div>

      {isInitializing && (
        <p className="text-xs text-amber-600 text-center animate-pulse">
          ⏳ Đang nạp mô hình vào GPU... Lần đầu khởi động có thể mất ~20-30s để nạp 2.5GB weights.
        </p>
      )}
    </div>
  );
}
