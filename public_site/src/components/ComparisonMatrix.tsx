import React from 'react';
import { X, Check, ArrowRight, Printer, ShieldCheck, FileSpreadsheet, Lock } from 'lucide-react';
import { ScrollReveal } from './ui/ScrollReveal';

interface ComparisonMatrixProps {
  onOpenPilot: () => void;
}

export const ComparisonMatrix: React.FC<ComparisonMatrixProps> = ({ onOpenPilot }) => {
  const comparisonRows = [
    {
      feature: 'Counter Medicine Entry',
      oldWay: '15–30 slow keyboard keystrokes and manual drug name typing while customer waits',
      newWay: '1 multi-strip camera photo detects names, dosages, and batches in seconds',
    },
    {
      feature: 'Expiry Management',
      oldWay: 'Expired stock discovered only when customer complains or during audit losses',
      newWay: 'Automatic First-Expiry First-Out (FEFO) dispensing selects the right batch first',
    },
    {
      feature: 'Loose & Split Tablets',
      oldWay: 'Mental math & paper slips to calculate 2 or 4 tablets from a strip of 15',
      newWay: 'Exact fractional tablet calculations down to the single pill with zero math errors',
    },
    {
      feature: 'Hardware & Mobility',
      oldWay: 'Tied strictly to one bulky desktop computer; no mobile camera access',
      newWay: 'Use any smartphone camera for scanning + bill on any laptop or desktop screen',
    },
    {
      feature: 'Peak Hour Checkout Speed',
      oldWay: '25–45 seconds per bill causing crowded queues during peak evening rush',
      newWay: 'Sub-3-second billing flow with 1-click GST bill, thermal print, and UPI QR',
    },
  ];

  const trustPoints = [
    {
      icon: Printer,
      title: 'Works with existing hardware',
      desc: 'Compatible with any USB or Bluetooth Barcode Scanner & 80mm/58mm Thermal Printer',
    },
    {
      icon: ShieldCheck,
      title: '100% Offline-Safe Backup',
      desc: 'Never lose a single bill during internet blips with automatic local encrypted sync',
    },
    {
      icon: FileSpreadsheet,
      title: 'Zero Software Lock-in',
      desc: 'Import from Marg / Excel seamlessly and export your complete store data anytime',
    },
    {
      icon: Lock,
      title: 'GST Compliant Invoicing',
      desc: 'B2B & B2C tax invoices, HSN code auto-mapping, and one-click CA Connect reports',
    },
  ];

  return (
    <section id="comparison" className="py-20 sm:py-28 bg-[#F5F4EF] border-b border-[#DCDDD5] relative overflow-hidden">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <ScrollReveal yOffset={16} className="text-center max-w-3xl mx-auto mb-14 sm:mb-20">
          <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-[#EDECE6] border border-[#DCDDD5] text-xs font-medium text-[#526B5A] mb-3 shadow-2xs">
            <span className="w-1.5 h-1.5 rounded-full bg-[#526B5A] animate-pulse" />
            <span className="font-mono uppercase tracking-wider">The Counter Contrast</span>
          </div>
          <h2 className="font-display text-3xl sm:text-4xl lg:text-5xl font-bold text-[#202522] tracking-tight">
            Why pharmacies are leaving legacy software.
          </h2>
          <p className="mt-3 text-sm sm:text-base text-[#5E625D] leading-relaxed">
            Compare everyday retail counter realities between 20-year-old accounting software and DawaiFlow.
          </p>
        </ScrollReveal>

        {/* Side-by-Side Comparison Bento Grid */}
        <ScrollReveal yOffset={20}>
          <div className="grid grid-cols-1 lg:grid-cols-12 rounded-3xl bg-[#FFFFFF] border border-[#DCDDD5] shadow-xs overflow-hidden">
            {/* Left Column: Traditional Legacy Software */}
            <div className="lg:col-span-6 p-6 sm:p-10 border-b lg:border-b-0 lg:border-r border-[#DCDDD5] bg-[#FAF9F5]/60">
              <div className="flex items-center gap-2.5 mb-6">
                <span className="w-2.5 h-2.5 rounded-full bg-[#D97706]" />
                <span className="font-mono text-xs uppercase tracking-wider text-[#78716C] font-semibold">
                  Traditional Pharmacy Software
                </span>
              </div>
              <h3 className="font-display text-xl sm:text-2xl font-bold text-[#202522] mb-6">
                Legacy software built for accountants, not busy pharmacists.
              </h3>

              <div className="space-y-6">
                {comparisonRows.map((row, idx) => (
                  <div key={idx} className="flex items-start gap-3.5 text-left">
                    <div className="w-5 h-5 rounded-full bg-[#FEE2E2] border border-[#FCA5A5] flex items-center justify-center text-[#DC2626] shrink-0 mt-0.5">
                      <X className="w-3.5 h-3.5" />
                    </div>
                    <div>
                      <div className="font-mono text-xs font-semibold text-[#78716C] mb-0.5">
                        {row.feature}
                      </div>
                      <p className="text-xs sm:text-sm text-[#78716C] leading-snug">
                        {row.oldWay}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Right Column: The DawaiFlow Experience */}
            <div className="lg:col-span-6 p-6 sm:p-10 bg-[#FFFFFF] relative overflow-hidden flex flex-col justify-between">
              {/* Subtle ambient corner glow */}
              <div
                className="absolute top-0 right-0 w-72 h-72 bg-[#526B5A]/5 rounded-full blur-3xl pointer-events-none"
                aria-hidden="true"
              />

              <div>
                <div className="flex items-center gap-2.5 mb-6">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#526B5A] animate-pulse" />
                  <span className="font-mono text-xs uppercase tracking-wider text-[#526B5A] font-semibold">
                    The DawaiFlow Way
                  </span>
                </div>
                <h3 className="font-display text-xl sm:text-2xl font-bold text-[#202522] mb-6">
                  Engineered for counter velocity, zero expiry loss, and ease.
                </h3>

                <div className="space-y-6">
                  {comparisonRows.map((row, idx) => (
                    <div key={idx} className="flex items-start gap-3.5 text-left">
                      <div className="w-5 h-5 rounded-full bg-[#EBF7EE] border border-[#526B5A]/30 flex items-center justify-center text-[#526B5A] shrink-0 mt-0.5 shadow-2xs">
                        <Check className="w-3.5 h-3.5" />
                      </div>
                      <div>
                        <div className="font-mono text-xs font-semibold text-[#526B5A] mb-0.5">
                          {row.feature}
                        </div>
                        <p className="text-xs sm:text-sm text-[#202522] font-medium leading-snug">
                          {row.newWay}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Bottom Quick CTA Button inside card */}
              <div className="mt-8 pt-6 border-t border-[#DCDDD5]/60 flex items-center justify-between">
                <span className="text-xs font-mono text-[#5E625D]">Ready to experience the difference?</span>
                <button
                  type="button"
                  onClick={onOpenPilot}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[#526B5A] hover:bg-[#43584a] text-white text-xs font-medium transition-all shadow-xs active:scale-[0.99] cursor-pointer"
                >
                  <span>Request a Pilot</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </div>
        </ScrollReveal>

        {/* Hardware & Compliance Trust Ribbon */}
        <div className="mt-14 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {trustPoints.map((point, idx) => {
            const Icon = point.icon;
            return (
              <ScrollReveal key={point.title} delay={idx * 0.06} yOffset={14}>
                <div className="p-5 rounded-2xl bg-[#FFFFFF] border border-[#DCDDD5] shadow-2xs h-full flex flex-col justify-start text-left hover:border-[#526B5A]/40 transition-colors">
                  <div className="w-8 h-8 rounded-lg bg-[#EDECE6] border border-[#DCDDD5] flex items-center justify-center text-[#526B5A] mb-3 shrink-0">
                    <Icon className="w-4 h-4" />
                  </div>
                  <h4 className="font-display text-sm font-bold text-[#202522] mb-1">
                    {point.title}
                  </h4>
                  <p className="text-xs text-[#5E625D] leading-relaxed">
                    {point.desc}
                  </p>
                </div>
              </ScrollReveal>
            );
          })}
        </div>
      </div>
    </section>
  );
};
