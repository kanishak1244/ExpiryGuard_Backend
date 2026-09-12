import React from 'react';
import { ScrollReveal } from './ui/ScrollReveal';

interface SequenceStep {
  num: string;
  title: string;
  subtitle: string;
  desc: string;
  badge: string;
}

export const ProcessSequence: React.FC = () => {
  const steps: SequenceStep[] = [
    {
      num: '01',
      title: 'Strip Scanning',
      subtitle: 'One photo, zero keyboard typing',
      desc: 'Simply place multiple strips on your counter. DawaiFlow\'s on-device AI detects names, strengths, and batches instantly.',
      badge: 'Camera AI',
    },
    {
      num: '02',
      title: 'FEFO Batch Matching',
      subtitle: 'Prevent expiry losses automatically',
      desc: 'Every medicine is matched against your live inventory. The earliest-expiring batch is prioritized so you never dispense stale stock.',
      badge: 'Batch Intelligence',
    },
    {
      num: '03',
      title: 'Sub-3-Second Checkout',
      subtitle: 'Faster billing, happier customers',
      desc: 'Items populate your bill automatically with default discounts, GST splits, thermal print, and UPI QR generation in one swift motion.',
      badge: 'Counter Speed',
    },
    {
      num: '04',
      title: 'Loose & Split Flow',
      subtitle: 'Exact fractional tablet tracking',
      desc: 'Dispense 2 or 5 tablets without breaking inventory. DawaiFlow splits strip inventory down to the single tablet with zero math errors.',
      badge: 'Unit Precision',
    },
  ];


  return (
    <section className="py-20 sm:py-28 bg-[#F5F4EF] border-b border-[#DCDDD5] relative overflow-hidden">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <ScrollReveal yOffset={16} className="max-w-2xl mx-auto text-center mb-14 sm:mb-20">
          <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-[#EDECE6] border border-[#DCDDD5] text-xs font-medium text-[#526B5A] mb-3 shadow-2xs">
            <span className="w-1.5 h-1.5 rounded-full bg-[#526B5A] animate-pulse" />
            <span className="font-mono uppercase tracking-wider">How DawaiFlow Works</span>
          </div>
          <h2 className="font-display text-3xl sm:text-4xl lg:text-5xl font-bold text-[#202522] tracking-tight">
            Every step engineered for speed.
          </h2>
          <p className="mt-3 text-sm sm:text-base text-[#5E625D] leading-relaxed">
            Transform slow pharmacy routines into a swift, frictionless flow.
          </p>
        </ScrollReveal>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {steps.map((step, i) => (
            <ScrollReveal key={step.num} delay={Math.min(i * 0.08, 0.3)} yOffset={20}>
              <div className="group relative p-6 rounded-2xl bg-[#FFFFFF] border border-[#DCDDD5] hover:border-[#526B5A]/50 hover:shadow-xs hover:-translate-y-1.5 transition-all duration-300 h-full flex flex-col justify-between shadow-2xs overflow-hidden">
                <div className="absolute -top-2 -right-1 font-mono text-7xl font-bold text-[#202522]/5 group-hover:text-[#526B5A]/10 transition-colors select-none pointer-events-none">
                  {step.num}
                </div>

                <div>
                  <div className="flex items-center justify-between mb-6">
                    <span className="font-mono text-xs font-semibold text-[#526B5A] bg-[#EDECE6] px-2.5 py-1 rounded-md border border-[#DCDDD5]">
                      {step.num}
                    </span>
                    <span className="font-mono text-[11px] text-[#5E625D] border border-[#DCDDD5] rounded-full px-2.5 py-0.5 bg-[#FFFFFF]">
                      {step.badge}
                    </span>
                  </div>

                  <h3 className="font-display text-xl font-semibold text-[#202522] mb-1 group-hover:text-[#526B5A] transition-colors">
                    {step.title}
                  </h3>

                  <p className="text-xs font-mono text-[#526B5A] font-medium mb-3.5">
                    "{step.subtitle}"
                  </p>

                  <p className="text-xs sm:text-sm text-[#5E625D] leading-relaxed">
                    {step.desc}
                  </p>
                </div>

                <div className="mt-6 pt-4 border-t border-[#DCDDD5]/60 flex items-center justify-between text-xs font-mono text-[#5E625D]">
                  <span>Step {step.num} of 04</span>
                  <span className="text-[#526B5A] group-hover:translate-x-1 transition-transform">→</span>
                </div>
              </div>
            </ScrollReveal>
          ))}
        </div>
      </div>
    </section>
  );
};
