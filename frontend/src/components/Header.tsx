interface HeaderProps {
  isConnected?: boolean;
  isConnecting?: boolean;
}

export default function Header({}: HeaderProps) {
  return (
    <header className="bg-white border-b border-slate-200/80 sticky top-0 z-30 shadow-xs">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-teal-500 to-emerald-400 flex items-center justify-center text-white shadow-xs">
            <span className="text-xl">🎙️</span>
          </div>
          <div>
            <h1 className="text-lg sm:text-xl font-bold text-slate-900 tracking-tight">
              Real-time Singing Voice Conversion
            </h1>
          </div>
        </div>
      </div>
    </header>
  );
}
