import React from 'react';
import { Camera, CheckCircle2, ArrowRight } from 'lucide-react';

export const HowItWorks: React.FC = () => {
  const steps = [
    {
      step: '01',
      title: 'Scan',
      desc: 'Capture medicine strips or purchase bills with your mobile camera or barcode scanner.',
      icon: Camera,
    },
    {
      step: '02',
      title: 'Confirm',
      desc: 'Review the matched inventory items, batches, and quantities with a single glance.',
      icon: CheckCircle2,
    },
    {
      step: '03',
      title: 'Move on',
      desc: 'Print receipt, update stock automatically, and get back to serving customers.',
      icon: ArrowRight,
    },
  ];

  return (
    <section id="how-it-works" className="py-14 sm:py-20 bg-slate-950 border-t border-slate-800/80">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        {/* Header */}
        <h2 className="text-2xl sm:text-3xl lg:text-4xl font-extrabold text-white tracking-tight">
          How it works
        </h2>
        <p className="mt-2.5 sm:mt-3 text-xs sm:text-base text-slate-400 max-w-lg mx-auto">
          Simplicity by design. Three steps from counter request to completed receipt.
        </p>

        {/* 3 Steps: Vertical with subtle connector on mobile, 3 columns on desktop */}
        <div className="mt-10 sm:mt-12 grid grid-cols-1 md:grid-cols-3 gap-4 sm:gap-5 text-left relative">
          {steps.map((item, index) => {
            const Icon = item.icon;
            return (
              <div
                key={item.step}
                className="p-5 sm:p-6 rounded-xl sm:rounded-2xl bg-slate-900/80 border border-slate-800 flex flex-col justify-between relative"
              >
                <div>
                  <div className="flex items-center justify-between mb-4 sm:mb-6">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-2xl sm:text-3xl font-extrabold text-emerald-400">
                        {item.step}
                      </span>
                      <span className="text-slate-600 text-lg sm:text-xl font-mono">—</span>
                      <span className="text-lg sm:text-xl font-bold text-white">
                        {item.title}
                      </span>
                    </div>

                    <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-center text-slate-300 shrink-0">
                      <Icon className="w-4 h-4 sm:w-5 sm:h-5 text-emerald-400" />
                    </div>
                  </div>

                  <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                    {item.desc}
                  </p>
                </div>

                {index < steps.length - 1 && (
                  <div className="hidden sm:block absolute -right-3 top-1/2 -translate-y-1/2 z-10 text-slate-600 font-mono text-sm">
                    →
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};
