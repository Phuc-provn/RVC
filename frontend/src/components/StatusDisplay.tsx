interface StatusDisplayProps {
  status: string;
  error: string | null;
  selectedVoiceName: string;
  modelSampleRate: number;
  sessionDuration: number;
  chunksProcessed: number;
  isConverting: boolean;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

export default function StatusDisplay({
  status,
  error,
  selectedVoiceName,
  modelSampleRate,
  sessionDuration,
  chunksProcessed,
  isConverting,
}: StatusDisplayProps) {
  const statusColor = error
    ? 'text-red-600 bg-red-50 border-red-200'
    : isConverting
      ? 'text-teal-700 bg-teal-50 border-teal-200'
      : 'text-gray-600 bg-gray-50 border-gray-200';

  return (
    <div className="space-y-4">
      {/* Status Badge */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">Status</h3>
        <div
          className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full border text-sm font-medium ${statusColor}`}
        >
          {isConverting && (
            <span className="inline-block w-2 h-2 rounded-full bg-teal-500 animate-pulse" />
          )}
          {error ? `Error: ${error}` : status}
        </div>
      </div>

      {/* Session Info */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">Session Info</h3>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between text-gray-600">
            <span>Voice</span>
            <span className="font-medium text-gray-800">
              {selectedVoiceName || '—'}
            </span>
          </div>
          <div className="flex justify-between text-gray-600">
            <span>Model Sample Rate</span>
            <span className="font-medium text-gray-800">
              {modelSampleRate > 0 ? `${modelSampleRate} Hz` : '—'}
            </span>
          </div>
          <div className="flex justify-between text-gray-600">
            <span>Duration</span>
            <span className="font-medium text-gray-800 tabular-nums">
              {formatDuration(sessionDuration)}
            </span>
          </div>
          <div className="flex justify-between text-gray-600">
            <span>Chunks Processed</span>
            <span className="font-medium text-gray-800 tabular-nums">
              {chunksProcessed}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
