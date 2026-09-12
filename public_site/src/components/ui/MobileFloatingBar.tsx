import React, { useState, useEffect } from 'react';
import { ArrowRight, MessageCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { getWhatsAppInquiryUrl } from '../../config/appConfig';

interface MobileFloatingBarProps {
  onOpenPilot: () => void;
}

export const MobileFloatingBar: React.FC<MobileFloatingBarProps> = ({ onOpenPilot }) => {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      // Show when scrolled past hero (~450px)
      setIsVisible(window.scrollY > 450);
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ y: 80, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 80, opacity: 0 }}
          transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
          className="md:hidden fixed bottom-4 inset-x-4 z-50 pointer-events-none"
        >
          <div className="bg-[#FFFFFF]/95 backdrop-blur-md border border-[#DCDDD5] p-2 rounded-2xl shadow-lg flex items-center gap-2 pointer-events-auto">
            <button
              type="button"
              onClick={onOpenPilot}
              className="flex-1 py-3 px-4 bg-[#526B5A] hover:bg-[#43584a] text-white rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 shadow-xs active:scale-[0.98] cursor-pointer"
            >
              <span>Request a Pilot</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>

            <a
              href={getWhatsAppInquiryUrl()}
              target="_blank"
              rel="noopener noreferrer"
              className="p-3 bg-[#EDECE6] hover:bg-[#E2E0D8] text-[#202522] rounded-xl flex items-center justify-center border border-[#DCDDD5] shadow-2xs active:scale-[0.98] cursor-pointer shrink-0"
              aria-label="Chat with DawaiFlow team on WhatsApp"
            >
              <MessageCircle className="w-4 h-4 text-[#25D366]" />
            </a>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
