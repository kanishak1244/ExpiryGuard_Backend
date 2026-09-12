import React, { useState } from 'react';
import { Plus, Minus, MessageCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { ScrollReveal } from './ui/ScrollReveal';
import { getWhatsAppInquiryUrl } from '../config/appConfig';

export const FaqSection: React.FC = () => {
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  const faqs = [
    {
      num: '01',
      q: 'What is DawaiFlow?',
      a: 'DawaiFlow is a modern pharmacy management and counter dispensing system. It eliminates slow, error-prone manual workflows across counter billing, multi-strip scanning, batch inventory, and customer credit khata.',
    },
    {
      num: '02',
      q: 'Does DawaiFlow work on mobile and web?',
      a: 'Yes. You can use your mobile phone camera for strip and bill scanning, and run high-speed counter billing on desktop and laptop browsers simultaneously.',
    },
    {
      num: '03',
      q: 'Can DawaiFlow scan multiple medicine strips at once?',
      a: 'Yes. DawaiFlow lets you photograph multiple medicine strips in a single shot. It automatically detects medicine names, strengths, and batches, matches them against your live stock, and populates the bill after pharmacist verification.',
    },
    {
      num: '04',
      q: 'How does First-Expiry First-Out (FEFO) dispensing work?',
      a: 'Every medicine batch is tracked with its expiry date. When an item is billed, DawaiFlow automatically suggests and dispenses the batch closest to expiry, saving thousands of rupees in preventable expired stock losses.',
    },
    {
      num: '05',
      q: 'How can my pharmacy join the pilot program?',
      a: 'Click "Request a Pilot" or reach out on WhatsApp. Our onboarding team will configure DawaiFlow for your store, import your existing inventory from any software, and train your staff at zero cost.',
    },
  ];

  return (
    <section id="faq" className="py-20 sm:py-28 bg-[#F5F4EF] border-b border-[#DCDDD5] relative overflow-hidden">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-16 items-start">
          {/* Left Column: Sticky Editorial Header */}
          <div className="lg:col-span-5 lg:sticky lg:top-28 space-y-6">
            <ScrollReveal yOffset={16}>
              <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-[#EDECE6] border border-[#DCDDD5] text-xs font-medium text-[#526B5A] mb-3 shadow-2xs">
                <span className="w-1.5 h-1.5 rounded-full bg-[#526B5A] animate-pulse" />
                <span className="font-mono uppercase tracking-wider">The Details</span>
              </div>

              <h2 className="font-display text-3xl sm:text-4xl lg:text-5xl font-bold text-[#202522] tracking-tight leading-tight">
                Answers to your questions.
              </h2>

              <p className="mt-3 text-sm sm:text-base text-[#5E625D] leading-relaxed">
                Everything you need to know about everyday counter operations, pilot onboarding, and data security.
              </p>

              <div className="pt-4">
                <a
                  href={getWhatsAppInquiryUrl()}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-white border border-[#DCDDD5] text-xs sm:text-sm font-medium text-[#202522] hover:border-[#526B5A]/50 hover:bg-[#FAF9F5] transition-all shadow-2xs active:scale-[0.99]"
                >
                  <MessageCircle className="w-4 h-4 text-[#25D366]" />
                  <span>Have more questions? Ask on WhatsApp</span>
                </a>
              </div>
            </ScrollReveal>
          </div>

          {/* Right Column: Numbered Accordion List */}
          <div className="lg:col-span-7 space-y-3">
            {faqs.map((faq, index) => {
              const isOpen = openIndex === index;
              return (
                <ScrollReveal key={faq.q} delay={index * 0.05} yOffset={14}>
                  <div
                    className={`rounded-2xl bg-[#FFFFFF] border transition-all duration-300 shadow-2xs overflow-hidden ${
                      isOpen
                        ? 'border-[#526B5A]/60 shadow-xs'
                        : 'border-[#DCDDD5] hover:border-[#526B5A]/30'
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => setOpenIndex(isOpen ? null : index)}
                      className="w-full p-5 sm:p-6 text-left flex items-start justify-between gap-4 focus:outline-none transition-colors cursor-pointer group"
                      aria-expanded={isOpen}
                    >
                      <div className="flex items-start gap-3.5">
                        <span className="font-mono text-xs font-semibold text-[#526B5A] bg-[#EDECE6] px-2 py-0.5 rounded border border-[#DCDDD5] shrink-0 mt-0.5">
                          {faq.num}
                        </span>
                        <span className="font-display text-base sm:text-lg font-bold text-[#202522] group-hover:text-[#526B5A] transition-colors leading-snug">
                          {faq.q}
                        </span>
                      </div>

                      <div
                        className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 transition-colors ${
                          isOpen
                            ? 'bg-[#526B5A] text-white'
                            : 'bg-[#EDECE6] text-[#5E625D] group-hover:bg-[#EBF7EE] group-hover:text-[#526B5A]'
                        }`}
                      >
                        {isOpen ? (
                          <Minus className="w-3.5 h-3.5" />
                        ) : (
                          <Plus className="w-3.5 h-3.5" />
                        )}
                      </div>
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
                          <div className="px-5 pb-6 sm:px-6 pt-1 text-xs sm:text-sm text-[#5E625D] leading-relaxed border-t border-[#DCDDD5]/60 bg-[#FAF9F5]/70 pl-14">
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
      </div>
    </section>
  );
};
