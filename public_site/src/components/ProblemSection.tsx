import React from 'react';
import { ScrollReveal } from './ui/ScrollReveal';

export const ProblemSection: React.FC = () => {
  return (
    <section className="py-16 sm:py-20 bg-[#F5F4EF] border-t border-b border-[#DCDDD5]">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        {/* Part 1: Pharmacy work is already busy */}
        <ScrollReveal yOffset={20}>
          <h2 className="text-2xl sm:text-3xl lg:text-[34px] font-semibold text-[#202522] tracking-tight">
            Pharmacy work is already busy.
          </h2>
          <p className="mt-3 text-[15px] sm:text-[17px] text-[#5E625D] leading-relaxed max-w-xl mx-auto">
            Your time should go into your customers and your pharmacy — not repetitive software work.
          </p>
        </ScrollReveal>

        {/* Subtle, restrained divider with the core philosophy badge */}
        <ScrollReveal delay={0.15} yOffset={16} className="my-9 sm:my-11 flex items-center justify-center gap-4">
          <div className="h-px bg-[#DCDDD5] flex-1 max-w-xs" />
          <span className="px-3.5 py-1.5 rounded-full bg-[#EDECE6] border border-[#DCDDD5] text-xs font-mono text-[#526B5A] uppercase tracking-wider font-medium shadow-2xs">
            Time-Saving &gt; Software Complexity
          </span>
          <div className="h-px bg-[#DCDDD5] flex-1 max-w-xs" />
        </ScrollReveal>

        {/* Part 2: Built to save your time */}
        <ScrollReveal delay={0.2} yOffset={20}>
          <h3 className="text-xl sm:text-2xl lg:text-[28px] font-semibold text-[#202522] tracking-tight">
            Built to save your time.
          </h3>
          <p className="mt-2.5 text-[15px] sm:text-[17px] text-[#5E625D] leading-relaxed max-w-xl mx-auto">
            DawaiFlow is designed to take repetitive work off your hands, so everyday pharmacy operations take fewer steps.
          </p>
        </ScrollReveal>
      </div>
    </section>
  );
};
