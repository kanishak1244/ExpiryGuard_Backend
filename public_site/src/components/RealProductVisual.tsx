import React from 'react';
import { ShieldCheck, ArrowRight } from 'lucide-react';

interface RealProductVisualProps {
  onOpenPilot: () => void;
}

export const RealProductVisual: React.FC<RealProductVisualProps> = ({ onOpenPilot }) => {
  return (
    <section className="py-16 sm:py-24 bg-[#F5F4EF] border-b border-[#DCDDD5]">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <div className="text-center max-w-2xl mx-auto mb-10 sm:mb-14">
          <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-[#EDECE6] border border-[#DCDDD5] text-xs font-medium text-[#526B5A] mb-3">
            <span>Web &amp; Mobile Synchronized</span>
          </div>
          <h2 className="text-2xl sm:text-3xl lg:text-[36px] font-semibold text-[#202522] tracking-tight">
            Your pharmacy, wherever you work.
          </h2>
          <p className="mt-2.5 text-[15px] sm:text-base text-[#5E625D] leading-relaxed">
            Use DawaiFlow across web and mobile without changing the way you work.
          </p>
        </div>

        {/* Product Showcase Composition: Laptop / Web App + Phone / Mobile App */}
        {/* DESKTOP LAYOUT (1024px+) */}
        <div className="hidden lg:block relative max-w-5xl mx-auto">
          <div className="grid grid-cols-12 gap-6 items-end">
            {/* Laptop / Web App - Primary Visual (Col span 8) */}
            <div className="col-span-8">
              <div className="rounded-xl bg-[#FFFFFF] border border-[#DCDDD5] shadow-xs overflow-hidden">
                {/* Browser Top Bar */}
                <div className="bg-[#EDECE6] px-4 py-2.5 border-b border-[#DCDDD5] flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-[#DCDDD5] inline-block" />
                    <span className="w-2.5 h-2.5 rounded-full bg-[#DCDDD5] inline-block" />
                    <span className="w-2.5 h-2.5 rounded-full bg-[#DCDDD5] inline-block" />
                  </div>
                  <div className="bg-[#FFFFFF] border border-[#DCDDD5] rounded-md px-3 py-0.5 text-xs font-mono text-[#5E625D] flex items-center gap-2">
                    <ShieldCheck className="w-3.5 h-3.5 text-[#526B5A]" />
                    <span>app.dawaiflow.com</span>
                  </div>
                  <div className="text-xs font-mono text-[#526B5A] font-medium">
                    Web App
                  </div>
                </div>

                {/* Real Web App Screenshot */}
                <div className="bg-[#FFFFFF] overflow-hidden">
                  <img
                    src="/assets/dawaiflow-web-app.png"
                    alt="Real DawaiFlow Web Pharmacy Management Application"
                    className="w-full h-auto block object-cover select-none"
                    loading="lazy"
                  />
                </div>
              </div>
              <div className="mt-2.5 text-xs text-[#5E625D] text-center">
                Fast counter billing, purchase entry, and GST reports on desktop
              </div>
            </div>

            {/* Phone / Mobile App - Sits naturally beside it (Col span 4) */}
            <div className="col-span-4">
              <div className="w-full max-w-[270px] mx-auto rounded-[32px] border-[5px] border-[#26352C] bg-[#26352C] shadow-xs overflow-hidden">
                {/* Phone Notch */}
                <div className="bg-[#26352C] pt-2 pb-1 flex justify-center items-center">
                  <div className="w-14 h-2 bg-[#1A261F] rounded-full flex items-center justify-center">
                    <div className="w-1.5 h-1.5 rounded-full bg-[#26352C]" />
                  </div>
                </div>

                {/* Real Mobile App Screenshot */}
                <div className="bg-[#FFFFFF] overflow-hidden">
                  <img
                    src="/assets/dawaiflow-mobile-app.jpg"
                    alt="Real DawaiFlow Mobile App Interface"
                    className="w-full h-auto block object-contain select-none"
                    loading="lazy"
                  />
                </div>

                {/* Bottom Home Bar */}
                <div className="bg-[#26352C] py-1 flex justify-center">
                  <div className="w-16 h-1 bg-[#3A4E40] rounded-full" />
                </div>
              </div>
              <div className="mt-2.5 text-xs text-[#5E625D] text-center">
                Multi-strip camera scanning on mobile
              </div>
            </div>
          </div>
        </div>

        {/* MOBILE & TABLET LAYOUT (<1024px) */}
        {/* Stacked naturally: Web App ↓ Mobile App */}
        <div className="block lg:hidden space-y-8 max-w-xl mx-auto">
          {/* 1. Web App */}
          <div>
            <div className="rounded-xl bg-[#FFFFFF] border border-[#DCDDD5] shadow-xs overflow-hidden">
              <div className="bg-[#EDECE6] px-3 py-2 border-b border-[#DCDDD5] flex items-center justify-between text-[11px] font-mono">
                <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-[#DCDDD5] inline-block" />
                  <span className="w-2 h-2 rounded-full bg-[#DCDDD5] inline-block" />
                  <span className="w-2 h-2 rounded-full bg-[#DCDDD5] inline-block" />
                </div>
                <span className="text-[#5E625D]">app.dawaiflow.com</span>
                <span className="text-[#526B5A] font-medium">Web</span>
              </div>
              <img
                src="/assets/dawaiflow-web-app.png"
                alt="Real DawaiFlow Web Application"
                className="w-full h-auto block object-cover"
                loading="lazy"
              />
            </div>
            <p className="mt-2 text-center text-xs text-[#5E625D]">
              Desktop: Fast counter billing &amp; inventory control
            </p>
          </div>

          {/* 2. Mobile App */}
          <div>
            <div className="w-full max-w-[250px] mx-auto rounded-[28px] border-[5px] border-[#26352C] bg-[#26352C] shadow-xs overflow-hidden">
              <div className="bg-[#26352C] pt-2 pb-1 flex justify-center items-center">
                <div className="w-12 h-2 bg-[#1A261F] rounded-full" />
              </div>
              <img
                src="/assets/dawaiflow-mobile-app.jpg"
                alt="Real DawaiFlow Mobile App"
                className="w-full h-auto block object-contain"
                loading="lazy"
              />
              <div className="bg-[#26352C] py-1 flex justify-center">
                <div className="w-16 h-0.5 bg-[#3A4E40] rounded-full" />
              </div>
            </div>
            <p className="mt-2 text-center text-xs text-[#5E625D]">
              Mobile: Strip camera scan &amp; quick lookup
            </p>
          </div>
        </div>

        {/* Request Pilot Call to Action */}
        <div className="mt-10 sm:mt-12 text-center">
          <button
            type="button"
            onClick={onOpenPilot}
            className="inline-flex items-center gap-2 px-6 py-2.5 bg-[#526B5A] hover:bg-[#43584a] text-white rounded-lg text-sm font-medium transition-colors shadow-xs cursor-pointer active:scale-[0.99]"
          >
            <span>Request a Pilot Demo</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </section>
  );
};
