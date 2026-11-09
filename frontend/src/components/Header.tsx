interface HeaderProps {
  isConnected: boolean;
  isConnecting: boolean;
}

export default function Header({ isConnected, isConnecting }: HeaderProps) {
  return (
    <header className="bg-white border-b border-slate-200/80 sticky top-0 z-30 shadow-xs">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-teal-500 to-emerald-400 flex items-center justify-center text-white shadow-xs">
            <span className="text-xl">🎙️</span>
          </div>
          <div>
            <h1 className="text-lg sm:text-xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
              Real-time Singing Voice Conversion
              <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-teal-50 text-teal-700 border border-teal-200 hidden sm:inline-block">
                AI Live
              </span>
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-50 border border-slate-200">
          <span
            className={`inline-block w-2.5 h-2.5 rounded-full ${
              isConnected
                ? 'bg-emerald-500 ring-2 ring-emerald-200'
                : isConnecting
                  ? 'bg-amber-400 animate-pulse ring-2 ring-amber-200'
                  : 'bg-rose-400'
            }`}
          />
          <span className="text-xs font-semibold text-slate-700">
            {isConnected ? 'Server Online' : isConnecting ? 'Connecting...' : 'Disconnected'}
          </span>
        </div>
      </div>
    </header>
  );
}
