import React from 'react';
import { ScrollReveal } from './ui/ScrollReveal';

export const ProblemSection: React.FC = () => {
  return (
    <section className="py-20 sm:py-28 bg-[#F5F4EF] border-t border-b border-[#DCDDD5] relative overflow-hidden">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        
        {/* Top Centered Philosophy Pill */}
        <ScrollReveal yOffset={16} className="flex justify-center mb-12 sm:mb-16">
          <div className="inline-flex items-center gap-2.5 px-4 py-1.5 rounded-full bg-[#EDECE6] border border-[#DCDDD5] text-xs font-mono text-[#526B5A] uppercase tracking-wider font-semibold shadow-2xs">
            <span className="w-1.5 h-1.5 rounded-full bg-[#526B5A] animate-pulse" />
            <span>Time-Saving &gt; Software Complexity</span>
          </div>
        </ScrollReveal>

        {/* 2-Column Editorial Story Chapter Cards inspired by template StorySection */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 lg:gap-8 items-stretch">
          {/* Chapter 01: The Problem */}
          <ScrollReveal delay={0.1} yOffset={24} className="h-full">
            <div className="group relative p-8 sm:p-10 rounded-2xl bg-[#FFFFFF] border border-[#DCDDD5] hover:border-[#DCDDD5]/80 hover:shadow-xs transition-all duration-300 h-full flex flex-col justify-between shadow-2xs overflow-hidden">
              {/* Background Large Number */}
              <div className="absolute top-4 right-6 font-mono text-6xl sm:text-7xl font-bold text-[#202522]/5 select-none pointer-events-none">
                01
              </div>

              <div className="relative z-10">
                <span className="font-mono text-xs text-[#8A8F88] uppercase tracking-widest block mb-3">
                  The Everyday Reality
                </span>
                <h2 className="font-display text-2xl sm:text-3xl font-semibold text-[#202522] tracking-tight leading-snug mb-4">
                  Pharmacy work is already busy.
                </h2>
                <p className="text-[15px] text-[#5E625D] leading-relaxed mb-4">
                  Between dealing with impatient queues, verifying strips, tracking distributor bills, and updating credit khatas, traditional pharmacy software demands too many clicks, keystrokes, and dialogs.
                </p>
                <p className="text-[14px] text-[#5E625D]/90 leading-relaxed font-medium">
                  Your energy belongs with your customers and your inventory — not fighting tedious screens.
                </p>
              </div>

              <div className="mt-8 pt-4 border-t border-[#DCDDD5]/60 flex items-center gap-2 text-xs font-mono text-[#8C4A3E]">
                <span>●</span>
                <span>Friction points at the retail counter</span>
              </div>
            </div>
          </ScrollReveal>

          {/* Chapter 02: The DawaiFlow Approach */}
          <ScrollReveal delay={0.2} yOffset={24} className="h-full">
            <div className="group relative p-8 sm:p-10 rounded-2xl bg-[#EDECE6]/70 border border-[#526B5A]/30 hover:border-[#526B5A]/60 hover:shadow-xs transition-all duration-300 h-full flex flex-col justify-between shadow-2xs overflow-hidden">
              {/* Background Large Number */}
              <div className="absolute top-4 right-6 font-mono text-6xl sm:text-7xl font-bold text-[#526B5A]/10 select-none pointer-events-none">
                02
              </div>

              <div className="relative z-10">
                <span className="font-mono text-xs text-[#526B5A] uppercase tracking-widest block mb-3 font-semibold">
                  The DawaiFlow Purpose
                </span>
                <h3 className="font-display text-2xl sm:text-3xl font-semibold text-[#202522] tracking-tight leading-snug mb-4">
                  Built to save your time.
                </h3>
                <p className="text-[15px] text-[#5E625D] leading-relaxed mb-4">
                  DawaiFlow is designed from the counter backward. Multi-strip camera recognition, auto-inventory matching, instant loose-tablet math, and one-tap invoice printing reduce everyday transactions to mere seconds.
                </p>
                <p className="text-[14px] text-[#202522] leading-relaxed font-medium">
                  Take repetitive work off your hands, so everyday pharmacy operations require fewer steps.
                </p>
              </div>

              <div className="mt-8 pt-4 border-t border-[#526B5A]/20 flex items-center gap-2 text-xs font-mono text-[#526B5A] font-semibold">
                <span>✓</span>
                <span>Automated workflow speed</span>
              </div>
            </div>
          </ScrollReveal>
        </div>

      </div>
    </section>
  );
};
