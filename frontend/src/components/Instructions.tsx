import { useState } from 'react';

export default function Instructions() {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden transition-all">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-5 py-3.5 bg-gradient-to-r from-slate-50 to-teal-50/30 flex items-center justify-between text-left hover:bg-slate-100/60 transition-colors"
      >
        <div className="flex items-center gap-2.5">
          <span className="text-lg">📖</span>
          <span className="font-bold text-sm sm:text-base text-slate-800">
            How to Use & Best Practices
          </span>
          <span className="text-xs px-2 py-0.5 rounded-md bg-teal-100/80 text-teal-800 font-medium">
            Guide
          </span>
        </div>
        <span className="text-slate-400 text-sm font-semibold">
          {isOpen ? '▲ Hide' : '▼ Show Instructions'}
        </span>
      </button>

      {isOpen && (
        <div className="p-5 space-y-4 text-slate-600 text-sm border-t border-slate-100">
          {/* Step-by-step Grid */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            {/* Step 1 */}
            <div className="bg-slate-50/80 rounded-xl p-3.5 border border-slate-200/60 flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-teal-600 text-white font-bold text-xs flex items-center justify-center">
                  1
                </span>
                <span className="font-semibold text-slate-800 text-xs sm:text-sm">Select Singer</span>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">
                Choose your favorite singer model from the <strong>Target Voice</strong> dropdown on the right.
              </p>
            </div>

            {/* Step 2 */}
            <div className="bg-amber-50/60 rounded-xl p-3.5 border border-amber-200/60 flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-amber-600 text-white font-bold text-xs flex items-center justify-center">
                  2
                </span>
                <span className="font-semibold text-amber-900 text-xs sm:text-sm">Wear Headphones 🎧</span>
              </div>
              <p className="text-xs text-amber-700/90 leading-relaxed font-medium">
                <strong>Crucial:</strong> Always use headphones to prevent the speaker audio from looping back into your mic.
              </p>
            </div>

            {/* Step 3 */}
            <div className="bg-slate-50/80 rounded-xl p-3.5 border border-slate-200/60 flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-teal-600 text-white font-bold text-xs flex items-center justify-center">
                  3
                </span>
                <span className="font-semibold text-slate-800 text-xs sm:text-sm">Start & Allow Mic</span>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">
                Click <strong>Start Conversion</strong>. When your browser prompts for microphone permission, click <strong>Allow</strong>.
              </p>
            </div>

            {/* Step 4 */}
            <div className="bg-emerald-50/60 rounded-xl p-3.5 border border-emerald-200/60 flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-emerald-600 text-white font-bold text-xs flex items-center justify-center">
                  4
                </span>
                <span className="font-semibold text-emerald-900 text-xs sm:text-sm">Sing & Listen Live</span>
              </div>
              <p className="text-xs text-emerald-700/90 leading-relaxed">
                Sing or speak into your microphone. Hear your transformed voice stream live into your headphones!
              </p>
            </div>
          </div>

          {/* Pro Tips Banner */}
          <div className="bg-blue-50/50 border border-blue-100 rounded-xl p-3.5 flex items-start gap-3 text-xs sm:text-sm text-blue-900">
            <span className="text-base">💡</span>
            <div>
              <p className="font-semibold text-blue-950 mb-1">Tips for Best Audio Quality:</p>
              <ul className="list-disc list-inside space-y-0.5 text-xs text-blue-800/90">
                <li>Sing 10–15 cm away from your microphone at a consistent volume.</li>
                <li>Ensure a quiet background environment so the AI pitch extractor (RMVPE) detects your melody accurately.</li>
                <li>Click <strong>Stop Conversion</strong> when you are finished singing to free GPU resources.</li>
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
