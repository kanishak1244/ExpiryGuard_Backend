import React from 'react';
import { ArrowRight } from 'lucide-react';

interface HeroProps {
  onOpenPilot: () => void;
}

export const Hero: React.FC<HeroProps> = ({ onOpenPilot }) => {
  return (
    <section id="product" className="pt-8 pb-12 sm:pt-12 sm:pb-16 lg:pt-14 lg:pb-20 bg-[#F5F4EF] overflow-hidden">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-10 xl:gap-12 items-center">
          {/* LEFT SIDE: DawaiFlow Hero Content (Full width on mobile, left column on desktop) */}
          <div className="w-full lg:col-span-7 xl:col-span-6 flex flex-col justify-center items-start text-left py-2 lg:py-4">
            {/* Existing badge */}
            <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-[#EDECE6] border border-[#DCDDD5] text-xs text-[#5E625D] mb-5 sm:mb-6">
              <span className="w-1.5 h-1.5 rounded-full bg-[#526B5A]" />
              <span>Accepting select pharmacies for pilot onboarding</span>
            </div>

            {/* Existing headline: Unchanged */}
            <h1 className="text-[32px] sm:text-[42px] lg:text-[44px] xl:text-[50px] font-semibold text-[#202522] tracking-tight leading-[1.18] sm:leading-[1.15]">
              More time for your pharmacy.{' '}
              <span className="text-[#526B5A] block mt-1">Less time managing software.</span>
            </h1>

            {/* Existing supporting paragraph: Unchanged */}
            <p className="mt-4 sm:mt-5 text-[15px] sm:text-[17px] text-[#5E625D] leading-relaxed max-w-xl">
              DawaiFlow reduces repetitive pharmacy work with faster billing, intelligent scanning, and simpler inventory management.
            </p>

            {/* Existing CTA Buttons */}
            <div className="mt-7 sm:mt-8 flex flex-col sm:flex-row items-stretch sm:items-center gap-3 w-full sm:w-auto">
              <button
                id="hero-get-started-btn"
                type="button"
                onClick={onOpenPilot}
                className="w-full sm:w-auto px-6 py-3.5 bg-[#526B5A] hover:bg-[#43584a] text-white rounded-lg text-[15px] font-medium transition-colors flex items-center justify-center gap-2 cursor-pointer shadow-xs active:scale-[0.99]"
              >
                <span>Get Started</span>
                <ArrowRight className="w-4 h-4" />
              </button>

              <button
                id="hero-request-pilot-btn"
                type="button"
                onClick={onOpenPilot}
                className="w-full sm:w-auto px-6 py-3.5 bg-transparent hover:bg-[#EDECE6] text-[#202522] border border-[#DCDDD5] rounded-lg text-[15px] font-medium transition-colors flex items-center justify-center cursor-pointer"
              >
                <span>Request a Pilot</span>
              </button>
            </div>
          </div>

          {/* RIGHT SIDE: LARGE Pharmacy Photograph (HIDDEN ON MOBILE, visible on desktop lg+) */}
          <div className="hidden lg:block lg:col-span-5 xl:col-span-6 w-full">
            <div className="relative w-full rounded-2xl overflow-hidden border border-[#DCDDD5] shadow-sm bg-[#EDECE6]">
              <img
                src="/assets/dawaiflow-pharmacy-hero.jpg"
                alt="Pharmacist assisting customers at a modern pharmacy counter using DawaiFlow"
                className="w-full h-full max-h-[500px] object-cover object-center block rounded-2xl select-none"
                loading="eager"
                decoding="async"
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
