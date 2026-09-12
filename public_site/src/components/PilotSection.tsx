import React from 'react';
import { ArrowRight } from 'lucide-react';

interface PilotSectionProps {
  onOpenPilot: () => void;
}

export const PilotSection: React.FC<PilotSectionProps> = ({ onOpenPilot }) => {
  return (
    <section id="pilot" className="py-20 sm:py-24 bg-[#F5F4EF] border-b border-[#DCDDD5] text-center">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8">
        <h2 className="text-2xl sm:text-3xl lg:text-[36px] font-semibold text-[#202522] tracking-tight">
          See DawaiFlow in your pharmacy.
        </h2>

        <p className="mt-3 text-[15px] sm:text-[17px] text-[#5E625D] max-w-lg mx-auto leading-relaxed">
          We&apos;re working with pharmacies to make everyday operations faster and simpler.
        </p>

        <div className="mt-8 flex justify-center">
          <button
            id="pilot-request-btn"
            type="button"
            onClick={onOpenPilot}
            className="px-7 py-3 bg-[#526B5A] hover:bg-[#43584a] text-white rounded-lg text-base font-medium transition-colors flex items-center gap-2 cursor-pointer shadow-xs active:scale-[0.99]"
          >
            <span>Request a Pilot</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </section>
  );
};
