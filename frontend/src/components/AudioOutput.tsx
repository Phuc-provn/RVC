interface AudioOutputProps {
  outputLevel: number;
  isActive: boolean;
}

export default function AudioOutput({ outputLevel, isActive }: AudioOutputProps) {
  const levelPercent = Math.round(outputLevel * 100);

  return (
    <div className="bg-gray-50 rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-lg" role="img" aria-label="speaker">
          🔊
        </span>
        <h3 className="text-sm font-semibold text-gray-700">Live Output</h3>
        {isActive && (
          <span className="ml-auto text-xs text-teal-600 font-medium flex items-center gap-1.5">
            <span className="inline-block w-2 h-2 rounded-full bg-teal-500 animate-pulse" />
            Playing
          </span>
        )}
      </div>

      {/* Level bar */}
      <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
        <div
          className="level-bar-fill h-full rounded-full"
          style={{
            width: `${levelPercent}%`,
            background: 'linear-gradient(90deg, #8b5cf6, #6d28d9)',
          }}
        />
      </div>

      <p className="text-xs text-gray-400">AI-generated audio</p>
    </div>
  );
}
