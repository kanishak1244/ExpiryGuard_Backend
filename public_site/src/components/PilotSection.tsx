import React from 'react';
import { ArrowRight, MessageCircle } from 'lucide-react';
import { getWhatsAppInquiryUrl } from '../config/appConfig';
import { ScrollReveal } from './ui/ScrollReveal';

interface PilotSectionProps {
  onOpenPilot: () => void;
}

export const PilotSection: React.FC<PilotSectionProps> = ({ onOpenPilot }) => {
  return (
    <section id="pilot" className="relative py-20 sm:py-24 bg-[#F5F4EF] border-b border-[#DCDDD5] text-center overflow-hidden">
      {/* Subtle ambient lighting inspired by template CTA */}
      <div
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[550px] h-[350px] bg-[#526B5A]/5 rounded-full blur-[100px] pointer-events-none z-0"
        aria-hidden="true"
      />

      <div className="relative z-10 max-w-2xl mx-auto px-4 sm:px-6 lg:px-8">
        <ScrollReveal yOffset={16}>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#EDECE6] border border-[#DCDDD5] text-xs font-medium text-[#526B5A] mb-4 shadow-2xs">
            <span className="w-1.5 h-1.5 rounded-full bg-[#526B5A] animate-pulse" />
            <span>Pilot Onboarding</span>
          </div>

          <h2 className="text-2xl sm:text-3xl lg:text-[36px] font-semibold text-[#202522] tracking-tight">
            See DawaiFlow in your pharmacy.
          </h2>

          <p className="mt-3 text-[15px] sm:text-[17px] text-[#5E625D] max-w-lg mx-auto leading-relaxed">
            We&apos;re working with pharmacies to make everyday operations faster and simpler.
          </p>
        </ScrollReveal>

        <ScrollReveal delay={0.15} yOffset={20}>
          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3.5">
            <button
              id="pilot-request-btn"
              type="button"
              onClick={onOpenPilot}
              className="group w-full sm:w-auto px-7 py-3 bg-[#526B5A] hover:bg-[#43584a] text-white rounded-lg text-base font-medium transition-all flex items-center justify-center gap-2 cursor-pointer shadow-xs active:scale-[0.99]"
            >
              <span>Request a Pilot</span>
              <ArrowRight className="w-4 h-4 transition-transform duration-200 group-hover:translate-x-1" />
            </button>

            <a
              id="pilot-whatsapp-btn"
              href={getWhatsAppInquiryUrl()}
              target="_blank"
              rel="noopener noreferrer"
              className="w-full sm:w-auto px-6 py-3 bg-white/80 hover:bg-[#EDECE6] text-[#202522] border border-[#DCDDD5] hover:border-[#C4C5BC] rounded-lg text-base font-medium transition-colors flex items-center justify-center gap-2 cursor-pointer shadow-2xs active:scale-[0.99]"
            >
              <MessageCircle className="w-4 h-4 text-[#25D366]" />
              <span>Chat on WhatsApp</span>
            </a>
          </div>
        </ScrollReveal>
      </div>
    </section>
  );
};
