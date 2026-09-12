import React from 'react';
import {
  Camera,
  FileText,
  AlertTriangle,
  Receipt,
  BookOpen,
  CheckCircle2,
} from 'lucide-react';

interface MainFeaturesProps {
  onOpenPilot: () => void;
}

export const MainFeatures: React.FC<MainFeaturesProps> = ({ onOpenPilot }) => {
  return (
    <section id="features" className="py-14 sm:py-20 bg-slate-950 border-t border-slate-800/80">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <div className="text-center max-w-2xl mx-auto mb-10 sm:mb-14">
          <h2 className="text-2xl sm:text-3xl lg:text-4xl font-extrabold text-white tracking-tight">
            Built to save you time.
          </h2>
          <p className="mt-2.5 sm:mt-3 text-xs sm:text-base text-slate-400">
            Five core capabilities focused entirely on cutting repetitive counter and backroom effort.
          </p>
        </div>

        {/* 5 Feature Cards: Clean single-column on mobile, balanced grid on desktop */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 sm:gap-5">
          {/* FEATURE 1: AI Multi-Medicine Strip Scanner */}
          <div className="md:col-span-2 rounded-xl sm:rounded-2xl bg-slate-900/90 border border-emerald-500/40 p-4 sm:p-8 shadow-lg shadow-black/40 relative overflow-hidden">
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-5 sm:gap-6">
              <div className="max-w-xl space-y-2.5 sm:space-y-3">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-emerald-950 border border-emerald-800 flex items-center justify-center text-emerald-400 shrink-0">
                    <Camera className="w-4 h-4" />
                  </div>
                  <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-400 bg-emerald-950/80 px-2 py-0.5 rounded border border-emerald-800/60">
                    Mobile Camera
                  </span>
                </div>

                <h3 className="text-lg sm:text-2xl font-bold text-white">
                  AI Multi-Medicine Strip Scanner
                </h3>

                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  Scan multiple medicine strips in one go and match them with your inventory before billing.
                </p>

                {/* Emphasized: SCAN → MATCH → CONFIRM */}
                <div className="pt-1">
                  <div className="inline-flex items-center gap-1.5 sm:gap-2 px-2.5 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-[11px] sm:text-xs font-mono">
                    <span className="text-emerald-400 font-bold">SCAN</span>
                    <span className="text-slate-600">→</span>
                    <span className="text-emerald-400 font-bold">MATCH</span>
                    <span className="text-slate-600">→</span>
                    <span className="text-emerald-400 font-bold">CONFIRM</span>
                  </div>
                </div>
              </div>

              {/* Visual Strip-Match Box */}
              <div className="w-full lg:w-72 bg-slate-950 border border-slate-800 rounded-xl p-3 sm:p-3.5 space-y-2 text-xs font-mono shrink-0">
                <div className="text-slate-400 text-[10px] uppercase font-bold flex items-center justify-between">
                  <span>Photo Recognition</span>
                  <span className="text-emerald-400">3 Detected</span>
                </div>
                <div className="p-2 bg-slate-900 rounded border border-slate-800 flex justify-between items-center text-slate-200 text-[11px] sm:text-xs">
                  <span>Augmentin 625 Duo</span>
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                </div>
                <div className="p-2 bg-slate-900 rounded border border-slate-800 flex justify-between items-center text-slate-200 text-[11px] sm:text-xs">
                  <span>Pan 40 Tablet</span>
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                </div>
                <div className="p-2 bg-slate-900 rounded border border-slate-800 flex justify-between items-center text-slate-200 text-[11px] sm:text-xs">
                  <span>Dolo 650mg</span>
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                </div>
                <div className="text-[10px] text-slate-400 text-center pt-0.5">
                  Pharmacist confirms before bill addition
                </div>
              </div>
            </div>
          </div>

          {/* FEATURE 2: Bill & Invoice Scanning */}
          <div className="rounded-xl sm:rounded-2xl bg-slate-900/70 border border-slate-800 p-4 sm:p-6 flex flex-col justify-between hover:border-slate-700 transition-colors">
            <div>
              <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-lg sm:rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-center text-emerald-400 mb-3 sm:mb-4">
                <FileText className="w-4 h-4 sm:w-5 sm:h-5" />
              </div>
              <h3 className="text-base sm:text-lg font-bold text-white mb-1.5 sm:mb-2">Bill &amp; Invoice Scanning</h3>
              <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                Scan purchase bills to reduce repetitive inventory entry and get stock into your system faster.
              </p>
            </div>
            <div className="mt-3.5 sm:mt-4 pt-2.5 sm:pt-3 border-t border-slate-800/80 text-[11px] text-slate-400 font-mono">
              Captures supplier lines for review &amp; confirmation
            </div>
          </div>

          {/* FEATURE 3: Smart Expiry Intelligence */}
          <div className="rounded-xl sm:rounded-2xl bg-slate-900/70 border border-slate-800 p-4 sm:p-6 flex flex-col justify-between hover:border-slate-700 transition-colors">
            <div>
              <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-lg sm:rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-center text-amber-400 mb-3 sm:mb-4">
                <AlertTriangle className="w-4 h-4 sm:w-5 sm:h-5" />
              </div>
              <h3 className="text-base sm:text-lg font-bold text-white mb-1.5 sm:mb-2">Smart Expiry Intelligence</h3>
              <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                See expired and approaching-expiry stock clearly, along with the inventory value that needs attention.
              </p>
            </div>
            <div className="mt-3.5 sm:mt-4 pt-2.5 sm:pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px] font-mono">
              <span className="text-slate-400">Value-at-risk tracking</span>
              <span className="text-amber-400">1M • 3M • 6M Windows</span>
            </div>
          </div>

          {/* FEATURE 4: Fast Pharmacy Billing */}
          <div className="rounded-xl sm:rounded-2xl bg-slate-900/70 border border-slate-800 p-4 sm:p-6 flex flex-col justify-between hover:border-slate-700 transition-colors">
            <div>
              <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-lg sm:rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-center text-emerald-400 mb-3 sm:mb-4">
                <Receipt className="w-4 h-4 sm:w-5 sm:h-5" />
              </div>
              <h3 className="text-base sm:text-lg font-bold text-white mb-1.5 sm:mb-2">Fast Pharmacy Billing</h3>
              <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                Barcode scanning, loose tablet billing, FEFO batch selection, payments, invoices and printing in one simple workflow.
              </p>
            </div>
            <div className="mt-3.5 sm:mt-4 pt-2.5 sm:pt-3 border-t border-slate-800/80 text-[11px] text-slate-400 font-mono">
              Full keyboard shortcuts • Sub-3-second checkout
            </div>
          </div>

          {/* FEATURE 5: Simple Customer Khata */}
          <div className="rounded-xl sm:rounded-2xl bg-slate-900/70 border border-slate-800 p-4 sm:p-6 flex flex-col justify-between hover:border-slate-700 transition-colors">
            <div>
              <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-lg sm:rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-center text-emerald-400 mb-3 sm:mb-4">
                <BookOpen className="w-4 h-4 sm:w-5 sm:h-5" />
              </div>
              <h3 className="text-base sm:text-lg font-bold text-white mb-1.5 sm:mb-2">Simple Customer Khata</h3>
              <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                Track customer credit, repayments and send payment reminders through WhatsApp in a few taps.
              </p>
            </div>
            <div className="mt-3.5 sm:mt-4 pt-2.5 sm:pt-3 border-t border-slate-800/80 text-[11px] text-slate-400 font-mono">
              Credit limits &amp; digital ledger receipts
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
