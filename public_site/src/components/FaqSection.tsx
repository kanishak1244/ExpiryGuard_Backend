import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { ScrollReveal } from './ui/ScrollReveal';

export const FaqSection: React.FC = () => {
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  const faqs = [
    {
      q: 'What is DawaiFlow?',
      a: 'DawaiFlow is a time-saving system for pharmacies. It reduces repetitive daily work across counter billing, medicine scanning, batch inventory, and customer khata.',
    },
    {
      q: 'Does DawaiFlow work on mobile and web?',
      a: 'Yes. You can use your mobile phone camera for strip and bill scanning, and run counter billing on web and desktop browsers.',
    },
    {
      q: 'Can DawaiFlow scan multiple medicine strips?',
      a: 'Yes. DawaiFlow lets you photograph multiple medicine strips at once, matches them against your active store inventory, and asks for quick pharmacist confirmation before billing.',
    },
    {
      q: 'Can DawaiFlow help manage pharmacy inventory?',
      a: 'Yes. It tracks medicines at the batch level with First-Expiry-First-Out (FEFO) dispensing, alerts you to low stock, and shows approaching expiry with the monetary value at risk.',
    },
    {
      q: 'How can I try DawaiFlow?',
      a: 'Click "Request a Pilot" or "Get Started" to share your pharmacy details. Our team will coordinate your setup and walkthrough.',
    },
  ];

  return (
    <section id="faq" className="py-20 bg-[#F5F4EF] border-b border-[#DCDDD5]">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
        <ScrollReveal yOffset={16} className="text-center mb-10">
          <h2 className="text-2xl sm:text-3xl lg:text-[36px] font-semibold text-[#202522] tracking-tight">
            Frequently asked questions
          </h2>
          <p className="mt-2 text-xs sm:text-sm text-[#5E625D]">
            Clear answers about DawaiFlow and everyday counter use.
          </p>
        </ScrollReveal>

        <div className="space-y-2.5">
          {faqs.map((faq, index) => {
            const isOpen = openIndex === index;
            return (
              <ScrollReveal key={faq.q} delay={index * 0.04} yOffset={12}>
                <div
                  className={`rounded-xl bg-[#FFFFFF] border transition-all duration-200 shadow-2xs overflow-hidden ${
                    isOpen ? 'border-[#526B5A]/50 shadow-xs' : 'border-[#DCDDD5] hover:border-[#C4C5BC]'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => setOpenIndex(isOpen ? null : index)}
                    className="w-full px-5 py-4 text-left font-medium text-[#202522] flex items-center justify-between gap-4 hover:text-[#526B5A] focus:outline-none transition-colors cursor-pointer"
                    aria-expanded={isOpen}
                  >
                    <span className="text-[15px] sm:text-base">{faq.q}</span>
                    <ChevronDown
                      className={`w-4 h-4 text-[#5E625D] shrink-0 transition-transform duration-200 ${
                        isOpen ? 'rotate-180 text-[#526B5A]' : ''
                      }`}
                    />
                  </button>

                  <AnimatePresence initial={false}>
                    {isOpen && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
                        className="overflow-hidden"
                      >
                        <div className="px-5 pb-5 pt-1 text-[14px] sm:text-[15px] text-[#5E625D] leading-relaxed border-t border-[#DCDDD5]/60 bg-[#FAF9F5]">
                          {faq.a}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </ScrollReveal>
            );
          })}
        </div>
      </div>
    </section>
  );
};
