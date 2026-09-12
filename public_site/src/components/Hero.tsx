import React from 'react';
import { motion } from 'motion/react';
import { ArrowRight } from 'lucide-react';

interface HeroProps {
  onOpenPilot: () => void;
}

export const Hero: React.FC<HeroProps> = ({ onOpenPilot }) => {
  return (
    <section
      id="product"
      className="relative w-full overflow-hidden bg-[#F8F7F3] border-b border-[#DCDDD5]/60 min-h-[580px] sm:min-h-[620px] md:min-h-[660px] lg:min-h-[700px] xl:min-h-[720px] flex items-center"
    >
      {/* FULL-WIDTH PHARMACY PHOTOGRAPH BACKGROUND */}
      {/* 1. Mobile Background Photo (Dedicated portrait orientation photo) */}
      <div className="md:hidden absolute inset-0 w-full h-full pointer-events-none select-none z-0">
        <img
          src="/assets/dawaiflow-pharmacy-hero-mobile.jpg"
          alt="Pharmacist assisting customers at a modern pharmacy counter using DawaiFlow"
          className="w-full h-full object-cover object-center"
          loading="eager"
          decoding="async"
        />
        {/* Subtle neutral readability overlay on mobile: ensures crisp typography while keeping pharmacy environment visible */}
        <div
          className="absolute inset-0 bg-gradient-to-b from-[#F8F7F3]/92 via-[#F8F7F3]/82 to-[#F8F7F3]/90"
          aria-hidden="true"
        />
      </div>

      {/* 2. Desktop/Laptop Background Photo (Landscape photo) - UNCHANGED FOR LAPTOP/DESKTOP */}
      <div className="hidden md:block absolute inset-0 w-full h-full pointer-events-none select-none z-0">
        <img
          src="/assets/dawaiflow-pharmacy-hero.jpg"
          alt="Pharmacist assisting customers at a modern pharmacy counter using DawaiFlow"
          className="w-full h-full object-cover object-[78%_center] lg:object-[82%_center] xl:object-[84%_center]"
          loading="eager"
          decoding="async"
        />
        {/* Desktop/Tablet natural left-side neutral gradient: ensures 100% text readability over the left 45% while keeping the pharmacist and customers completely visible on the right */}
        <div
          className="absolute inset-0 bg-gradient-to-r from-[#F8F7F3] via-[#F8F7F3]/95 via-35% md:via-42% lg:via-48% to-transparent to-75% lg:to-82%"
          aria-hidden="true"
        />
      </div>

      {/* HERO CONTENT: Layered over the LEFT portion */}
      <div className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 xl:px-12 relative z-10 py-12 sm:py-16 md:py-20 lg:py-24">
        <div className="max-w-xl lg:max-w-[520px] xl:max-w-[560px] flex flex-col justify-center items-start text-left">
          {/* Small Pilot Badge */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
            className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-[#EDECE6] border border-[#DCDDD5] text-xs text-[#5E625D] mb-5 sm:mb-6 shadow-2xs"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-[#526B5A] animate-pulse" />
            <span>Accepting select pharmacies for pilot onboarding</span>
          </motion.div>

          {/* Main Headline */}
          <motion.h1
            initial={{ opacity: 0, y: 22 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
            className="font-display text-[34px] sm:text-[44px] md:text-[50px] lg:text-[56px] xl:text-[62px] font-bold text-[#202522] tracking-tight leading-[1.08] sm:leading-[1.06]"
          >
            More time for your pharmacy.{' '}
            <span className="text-[#526B5A] block mt-1.5 font-bold">Less time managing software.</span>
          </motion.h1>

          {/* Supporting Paragraph */}
          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="mt-4 sm:mt-5 text-[15px] sm:text-[17px] text-[#5E625D] leading-relaxed max-w-lg"
          >
            DawaiFlow reduces repetitive pharmacy work with faster billing, intelligent scanning, and simpler inventory management.
          </motion.p>

          {/* Action Buttons */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.3, ease: [0.22, 1, 0.36, 1] }}
            className="mt-7 sm:mt-8 flex flex-col sm:flex-row items-stretch sm:items-center gap-3 w-full sm:w-auto"
          >
            <button
              id="hero-get-started-btn"
              type="button"
              onClick={onOpenPilot}
              className="group w-full sm:w-auto px-6 py-3.5 bg-[#526B5A] hover:bg-[#43584a] text-white rounded-lg text-[15px] font-medium transition-all flex items-center justify-center gap-2 cursor-pointer shadow-xs active:scale-[0.99]"
            >
              <span>Get Started</span>
              <ArrowRight className="w-4 h-4 transition-transform duration-200 group-hover:translate-x-1" />
            </button>

            <button
              id="hero-request-pilot-btn"
              type="button"
              onClick={onOpenPilot}
              className="w-full sm:w-auto px-6 py-3.5 bg-white/80 hover:bg-[#EDECE6] text-[#202522] border border-[#DCDDD5] hover:border-[#C4C5BC] rounded-lg text-[15px] font-medium transition-colors flex items-center justify-center cursor-pointer shadow-2xs active:scale-[0.99]"
            >
              <span>Request a Pilot</span>
            </button>
          </motion.div>

          {/* Micro Metrics Pill Stream */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.4, ease: [0.22, 1, 0.36, 1] }}
            className="mt-8 pt-6 border-t border-[#DCDDD5]/70 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-[#5E625D]"
          >
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-[#526B5A]" />
              <span className="font-medium text-[#202522]">100% FEFO Auto-Matching</span>
            </div>
            <span className="text-[#DCDDD5] hidden sm:inline">•</span>
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-[#526B5A]" />
              <span className="font-medium text-[#202522]">&lt; 3s Billing Speed</span>
            </div>
            <span className="text-[#DCDDD5] hidden sm:inline">•</span>
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-[#526B5A]" />
              <span className="font-medium text-[#202522]">Zero Data Lock-in</span>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
};
