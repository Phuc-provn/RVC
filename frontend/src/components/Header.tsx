interface HeaderProps {
  isConnected: boolean;
  isConnecting: boolean;
}

export default function Header({ isConnected, isConnecting }: HeaderProps) {
  return (
    <header className="bg-white border-b border-gray-100">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-3xl" role="img" aria-label="music">
            🎵
          </span>
          <div>
            <h1 className="text-xl font-bold text-gray-900 leading-tight">
              Singing Voice Conversion
            </h1>
            <p className="text-sm text-gray-500 hidden sm:block">
              Transform your singing voice with AI-powered voice models
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={`inline-block w-2.5 h-2.5 rounded-full ${
              isConnected
                ? 'bg-emerald-500'
                : isConnecting
                  ? 'bg-amber-400 animate-pulse'
                  : 'bg-red-400'
            }`}
          />
          <span className="text-sm font-medium text-gray-600">
            {isConnected ? 'Connected' : isConnecting ? 'Connecting...' : 'Disconnected'}
          </span>
        </div>
      </div>
    </header>
  );
}
