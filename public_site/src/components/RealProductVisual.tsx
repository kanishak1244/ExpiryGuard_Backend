import React, { useState } from 'react';
import { ShieldCheck, ArrowRight, Zap, CheckCircle2, Camera } from 'lucide-react';
import { ScrollReveal } from './ui/ScrollReveal';

interface RealProductVisualProps {
  onOpenPilot: () => void;
}

export const RealProductVisual: React.FC<RealProductVisualProps> = ({ onOpenPilot }) => {
  const [activeHotspot, setActiveHotspot] = useState<number | null>(1);

  const hotspots = [
    {
      id: 1,
      label: 'Fast Counter POS',
      tag: 'POS Speed',
      title: 'Sub-3-Second Checkout',
      desc: 'Rapid item entry with automatic GST splits, default discounts, and instant 1-click thermal print.',
    },
    {
      id: 2,
      label: 'FEFO Batch Intelligence',
      tag: 'Zero Waste',
      title: 'Automatic Expiry Shield',
      desc: 'DawaiFlow matches active stock and automatically dispenses nearest-expiring batches first.',
    },
    {
      id: 3,
      label: 'Multi-Strip Mobile Scan',
      tag: 'Mobile AI',
      title: 'AI Strip Camera Recognition',
      desc: 'Point any smartphone camera at multiple strips. Automatically detects medicine names, strengths, and batches.',
    },
  ];

  return (
    <section className="py-20 sm:py-28 bg-[#F5F4EF] border-b border-[#DCDDD5] relative overflow-hidden">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <ScrollReveal yOffset={16} className="text-center max-w-2xl mx-auto mb-8 sm:mb-12">
          <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-[#EDECE6] border border-[#DCDDD5] text-xs font-medium text-[#526B5A] mb-3 shadow-2xs">
            <span className="w-1.5 h-1.5 rounded-full bg-[#526B5A] animate-pulse" />
            <span className="font-mono uppercase tracking-wider">Web &amp; Mobile Synchronized</span>
          </div>
          <h2 className="font-display text-3xl sm:text-4xl lg:text-5xl font-bold text-[#202522] tracking-tight">
            Your pharmacy, wherever you work.
          </h2>
          <p className="mt-3 text-sm sm:text-base text-[#5E625D] leading-relaxed">
            Use DawaiFlow across desktop browsers and smartphones with zero operational friction.
          </p>
        </ScrollReveal>

        {/* Hotspot Interactive Switcher Bar */}
        <div className="flex flex-wrap items-center justify-center gap-2 sm:gap-3 mb-8 sm:mb-12">
          {hotspots.map((spot) => {
            const isActive = activeHotspot === spot.id;
            return (
              <button
                key={spot.id}
                type="button"
                onClick={() => setActiveHotspot(isActive ? null : spot.id)}
                className={`px-3.5 py-1.5 rounded-full text-xs font-medium transition-all flex items-center gap-2 cursor-pointer shadow-2xs ${
                  isActive
                    ? 'bg-[#526B5A] text-white border border-[#526B5A]'
                    : 'bg-[#FFFFFF] text-[#5E625D] border border-[#DCDDD5] hover:border-[#526B5A]/40 hover:text-[#202522]'
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    isActive ? 'bg-white animate-pulse' : 'bg-[#526B5A]'
                  }`}
                />
                <span>{spot.label}</span>
              </button>
            );
          })}
        </div>

        {/* Product Showcase Composition: Laptop / Web App + Phone / Mobile App */}
        {/* DESKTOP LAYOUT (1024px+) */}
        <div className="hidden lg:block relative max-w-5xl mx-auto">
          <div className="grid grid-cols-12 gap-6 items-end">
            {/* Laptop / Web App - Primary Visual (Col span 8) */}
            <div className="col-span-8 relative">
              <div className="rounded-2xl bg-[#FFFFFF] border border-[#DCDDD5] shadow-sm overflow-hidden relative">
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
                  <div className="text-xs font-mono text-[#526B5A] font-semibold">
                    Web App
                  </div>
                </div>

                {/* Real Web App Screenshot */}
                <div className="bg-[#FFFFFF] overflow-hidden relative">
                  <img
                    src="/assets/dawaiflow-web-app.png"
                    alt="Real DawaiFlow Web Pharmacy Management Application"
                    className="w-full h-auto block object-cover select-none"
                    loading="lazy"
                  />

                  {/* Hotspot 1: POS Billing */}
                  <div className="absolute top-[35%] left-[28%] z-20">
                    <button
                      type="button"
                      onClick={() => setActiveHotspot(activeHotspot === 1 ? null : 1)}
                      className="relative flex items-center justify-center w-6 h-6 rounded-full bg-[#526B5A] text-white shadow-md cursor-pointer group"
                      aria-label="Toggle Hotspot 1"
                    >
                      <span className="absolute w-8 h-8 rounded-full bg-[#526B5A]/30 animate-ping" />
                      <span className="text-[10px] font-mono font-bold">1</span>
                    </button>
                    {activeHotspot === 1 && (
                      <div className="absolute left-8 top-1/2 -translate-y-1/2 w-60 p-3.5 rounded-xl bg-white/95 backdrop-blur-md border border-[#DCDDD5] shadow-lg text-left z-30 pointer-events-none">
                        <div className="font-mono text-[10px] uppercase font-semibold text-[#526B5A] mb-0.5">
                          POS Speed
                        </div>
                        <div className="font-display text-xs font-bold text-[#202522] mb-1">
                          Sub-3-Second Billing
                        </div>
                        <p className="text-[11px] text-[#5E625D] leading-snug">
                          Rapid item entry with automatic GST splits, default customer discounts, and thermal print.
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Hotspot 2: FEFO Batch Selection */}
                  <div className="absolute top-[48%] right-[22%] z-20">
                    <button
                      type="button"
                      onClick={() => setActiveHotspot(activeHotspot === 2 ? null : 2)}
                      className="relative flex items-center justify-center w-6 h-6 rounded-full bg-[#526B5A] text-white shadow-md cursor-pointer group"
                      aria-label="Toggle Hotspot 2"
                    >
                      <span className="absolute w-8 h-8 rounded-full bg-[#526B5A]/30 animate-ping" />
                      <span className="text-[10px] font-mono font-bold">2</span>
                    </button>
                    {activeHotspot === 2 && (
                      <div className="absolute right-8 top-1/2 -translate-y-1/2 w-60 p-3.5 rounded-xl bg-white/95 backdrop-blur-md border border-[#DCDDD5] shadow-lg text-left z-30 pointer-events-none">
                        <div className="font-mono text-[10px] uppercase font-semibold text-[#526B5A] mb-0.5">
                          Zero Waste
                        </div>
                        <div className="font-display text-xs font-bold text-[#202522] mb-1">
                          FEFO Expiry Shield
                        </div>
                        <p className="text-[11px] text-[#5E625D] leading-snug">
                          DawaiFlow automatically suggests and dispenses the nearest-expiring medicine batch first.
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
              <div className="mt-3 text-xs text-[#5E625D] text-center font-mono">
                Counter billing, purchase entry, and GST reports on desktop
              </div>
            </div>

            {/* Phone / Mobile App - Sits naturally beside it (Col span 4) */}
            <div className="col-span-4 relative">
              <div className="w-full max-w-[270px] mx-auto rounded-[32px] border-[5px] border-[#26352C] bg-[#26352C] shadow-md overflow-hidden relative">
                {/* Phone Notch */}
                <div className="bg-[#26352C] pt-2 pb-1 flex justify-center items-center">
                  <div className="w-14 h-2 bg-[#1A261F] rounded-full flex items-center justify-center">
                    <div className="w-1.5 h-1.5 rounded-full bg-[#26352C]" />
                  </div>
                </div>

                {/* Real Mobile App Screenshot */}
                <div className="bg-[#FFFFFF] overflow-hidden relative">
                  <img
                    src="/assets/dawaiflow-mobile-app.jpg"
                    alt="Real DawaiFlow Mobile App Interface"
                    className="w-full h-auto block object-contain select-none"
                    loading="lazy"
                  />

                  {/* Hotspot 3: Mobile Camera Scan */}
                  <div className="absolute top-[38%] left-1/2 -translate-x-1/2 z-20">
                    <button
                      type="button"
                      onClick={() => setActiveHotspot(activeHotspot === 3 ? null : 3)}
                      className="relative flex items-center justify-center w-6 h-6 rounded-full bg-[#526B5A] text-white shadow-md cursor-pointer group"
                      aria-label="Toggle Hotspot 3"
                    >
                      <span className="absolute w-8 h-8 rounded-full bg-[#526B5A]/30 animate-ping" />
                      <span className="text-[10px] font-mono font-bold">3</span>
                    </button>
                    {activeHotspot === 3 && (
                      <div className="absolute left-1/2 -translate-x-1/2 top-8 w-52 p-3 rounded-xl bg-white/95 backdrop-blur-md border border-[#DCDDD5] shadow-lg text-left z-30 pointer-events-none">
                        <div className="font-mono text-[10px] uppercase font-semibold text-[#526B5A] mb-0.5">
                          Mobile AI
                        </div>
                        <div className="font-display text-xs font-bold text-[#202522] mb-1">
                          Multi-Strip Scan
                        </div>
                        <p className="text-[11px] text-[#5E625D] leading-snug">
                          Photograph multiple strips in one click to identify medicine names and batches.
                        </p>
                      </div>
                    )}
                  </div>
                </div>

                {/* Bottom Home Bar */}
                <div className="bg-[#26352C] py-1 flex justify-center">
                  <div className="w-16 h-1 bg-[#3A4E40] rounded-full" />
                </div>
              </div>
              <div className="mt-3 text-xs text-[#5E625D] text-center font-mono">
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
            <p className="mt-2 text-center text-xs text-[#5E625D] font-mono">
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
            <p className="mt-2 text-center text-xs text-[#5E625D] font-mono">
              Mobile: Strip camera scan &amp; quick lookup
            </p>
          </div>
        </div>

        {/* Request Pilot Call to Action */}
        <ScrollReveal delay={0.15} yOffset={16} className="mt-12 text-center">
          <button
            type="button"
            onClick={onOpenPilot}
            className="group inline-flex items-center gap-2 px-6 py-2.5 bg-[#526B5A] hover:bg-[#43584a] text-white rounded-lg text-sm font-medium transition-all shadow-xs cursor-pointer active:scale-[0.99]"
          >
            <span>Request a Pilot Demo</span>
            <ArrowRight className="w-4 h-4 transition-transform duration-200 group-hover:translate-x-1" />
          </button>
        </ScrollReveal>
      </div>
    </section>
  );
};
