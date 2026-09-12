import React from 'react';
import { Clock, Zap } from 'lucide-react';

export const TimeSavingSection: React.FC = () => {
  return (
    <section className="py-14 sm:py-20 bg-slate-900/30 border-t border-slate-800/80">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        {/* Heading */}
        <h2 className="text-2xl sm:text-3xl lg:text-4xl font-extrabold text-white tracking-tight">
          Built around your time, not your software.
        </h2>

        {/* Short Paragraph */}
        <p className="mt-3 sm:mt-4 text-xs sm:text-base text-slate-300 max-w-2xl mx-auto leading-relaxed">
          Everyday pharmacy work involves hundreds of small repetitive actions. DawaiFlow is designed to reduce them.
        </p>

        {/* Comparison Layout: Stacks on mobile, side-by-side on desktop */}
        <div className="mt-10 sm:mt-12 grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6 text-left">
          {/* WITHOUT DAWAIFLOW */}
          <div className="p-5 sm:p-6 rounded-xl sm:rounded-2xl bg-slate-950 border border-slate-800 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-3 sm:mb-4">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                  Without DawaiFlow
                </span>
                <Clock className="w-4 h-4 text-slate-400" />
              </div>

              <p className="text-xs text-slate-400 mb-4 sm:mb-5">
                Manual multi-step keyboard typing for every single product:
              </p>

              {/* Vertical Steps with Downward Indicators */}
              <div className="space-y-1.5 font-mono text-xs text-slate-400 text-center">
                <div className="p-2 sm:p-2.5 bg-slate-900 rounded-lg border border-slate-800 text-slate-300 font-medium">
                  Search
                </div>
                <div className="text-slate-400 text-xs py-0.5">↓</div>

                <div className="p-2 sm:p-2.5 bg-slate-900 rounded-lg border border-slate-800 text-slate-300 font-medium">
                  Type
                </div>
                <div className="text-slate-400 text-xs py-0.5">↓</div>

                <div className="p-2 sm:p-2.5 bg-slate-900 rounded-lg border border-slate-800 text-slate-300 font-medium">
                  Select
                </div>
                <div className="text-slate-400 text-xs py-0.5">↓</div>

                <div className="p-2 sm:p-2.5 bg-slate-900 rounded-lg border border-slate-800 text-slate-300 font-medium">
                  Check
                </div>
                <div className="text-slate-400 text-xs py-0.5">↓</div>

                <div className="p-2 sm:p-2.5 bg-slate-900 rounded-lg border border-slate-800 text-slate-300 font-medium">
                  Enter
                </div>
                <div className="text-slate-400 text-xs py-0.5">↓</div>

                <div className="p-2 sm:p-2.5 bg-slate-900/60 rounded-lg border border-dashed border-slate-800 text-slate-400 font-semibold">
                  Repeat for every item
                </div>
              </div>
            </div>
          </div>

          {/* WITH DAWAIFLOW */}
          <div className="p-5 sm:p-6 rounded-xl sm:rounded-2xl bg-slate-950 border border-emerald-500/50 flex flex-col justify-between shadow-lg shadow-emerald-950/20">
            <div>
              <div className="flex items-center justify-between mb-3 sm:mb-4">
                <span className="text-xs font-bold uppercase tracking-wider text-emerald-400">
                  With DawaiFlow
                </span>
                <Zap className="w-4 h-4 text-emerald-400" />
              </div>

              <p className="text-xs text-slate-300 mb-4 sm:mb-5">
                Streamlined capture, verification, and instant dispensing:
              </p>

              {/* Vertical Steps with Downward Indicators */}
              <div className="space-y-2 font-mono text-xs text-center">
                <div className="p-3 bg-slate-900 rounded-lg border border-slate-800 text-emerald-400 font-bold text-sm">
                  Scan
                </div>
                <div className="text-emerald-400 text-xs py-0.5 font-bold">↓</div>

                <div className="p-3 bg-slate-900 rounded-lg border border-slate-800 text-emerald-400 font-bold text-sm">
                  Confirm
                </div>
                <div className="text-emerald-400 text-xs py-0.5 font-bold">↓</div>

                <div className="p-3 bg-emerald-950/80 rounded-lg border border-emerald-700/80 text-white font-bold text-sm shadow-sm">
                  Move on
                </div>
              </div>
            </div>

            <div className="mt-6 pt-3 border-t border-slate-800/80 text-xs text-center sm:text-left text-slate-300">
              Save crucial seconds on every customer checkout.
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
