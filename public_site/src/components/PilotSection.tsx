import React from 'react';
import { Check, ArrowRight, MessageCircle } from 'lucide-react';
import { getWhatsAppInquiryUrl } from '../config/appConfig';
import { ScrollReveal } from './ui/ScrollReveal';
import { MagneticButton } from './ui/MagneticButton';

interface PilotSectionProps {
  onOpenPilot: () => void;
}

export const PilotSection: React.FC<PilotSectionProps> = ({ onOpenPilot }) => {
  const pilotBenefits = [
    'Free data import from any software or Excel',
    'On-site or video counter onboarding for your staff',
    'Full access to mobile scanner + counter billing',
    'Zero disruption to your daily counter operations',
    'Dedicated WhatsApp support line',
  ];

  return (
    <section id="pilot" className="relative py-20 sm:py-28 bg-[#F5F4EF] border-b border-[#DCDDD5] overflow-hidden">
      {/* Ambient lighting backdrop */}
      <div
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[450px] bg-[#526B5A]/5 rounded-full blur-[120px] pointer-events-none z-0"
        aria-hidden="true"
      />

      <div className="relative z-10 max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Call to Action Card inspired by template Pricing/CTA cards */}
        <ScrollReveal yOffset={20}>
          <div className="p-8 sm:p-12 rounded-3xl bg-[#FFFFFF] border border-[#DCDDD5] shadow-xs relative overflow-hidden">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-center">
              <div className="lg:col-span-7 flex flex-col items-start text-left">
                <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-[#EDECE6] border border-[#DCDDD5] text-xs font-medium text-[#526B5A] mb-5 shadow-2xs">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#526B5A] animate-pulse" />
                  <span className="font-mono uppercase tracking-wider">Limited Pharmacy Onboarding</span>
                </div>

                <h2 className="font-display text-3xl sm:text-4xl lg:text-[42px] font-bold text-[#202522] tracking-tight leading-tight">
                  See DawaiFlow in your pharmacy.
                </h2>

                <p className="mt-4 text-[15px] sm:text-base text-[#5E625D] leading-relaxed">
                  Join our select pilot program. We'll set up DawaiFlow on your retail counter, import your medicines, and train your team at no cost.
                </p>

                <div className="mt-8 flex flex-col sm:flex-row items-stretch sm:items-center gap-3.5 w-full sm:w-auto">
                  <MagneticButton
                    id="pilot-request-btn"
                    onClick={onOpenPilot}
                    className="group w-full sm:w-auto px-8 py-3.5 bg-[#526B5A] hover:bg-[#43584a] text-white rounded-lg text-base font-medium transition-colors flex items-center justify-center gap-2 cursor-pointer shadow-xs active:scale-[0.99]"
                  >
                    <span>Request a Pilot</span>
                    <ArrowRight className="w-4 h-4 transition-transform duration-200 group-hover:translate-x-1" />
                  </MagneticButton>

                  <a
                    id="pilot-whatsapp-btn"
                    href={getWhatsAppInquiryUrl()}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="w-full sm:w-auto px-6 py-3.5 bg-white/80 hover:bg-[#EDECE6] text-[#202522] border border-[#DCDDD5] hover:border-[#C4C5BC] rounded-lg text-base font-medium transition-colors flex items-center justify-center gap-2.5 cursor-pointer shadow-2xs active:scale-[0.99]"
                  >
                    <MessageCircle className="w-4 h-4 text-[#25D366]" />
                    <span>Chat on WhatsApp</span>
                  </a>
                </div>
              </div>

              {/* Pilot Benefits Box */}
              <div className="lg:col-span-5 bg-[#EDECE6]/50 border border-[#DCDDD5] rounded-2xl p-6 sm:p-8 space-y-4 text-left">
                <div className="font-display text-base font-semibold text-[#202522] mb-2">
                  What's included in your pilot:
                </div>
                {pilotBenefits.map((benefit, i) => (
                  <div key={i} className="flex items-start gap-3">
                    <div className="w-5 h-5 rounded-full bg-[#EBF7EE] border border-[#526B5A]/30 flex items-center justify-center text-[#526B5A] shrink-0 mt-0.5">
                      <Check className="w-3.5 h-3.5" />
                    </div>
                    <span className="text-xs sm:text-sm text-[#5E625D] leading-snug">
                      {benefit}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </ScrollReveal>
      </div>
    </section>
  );
};
