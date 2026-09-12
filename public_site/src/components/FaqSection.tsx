import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';

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
        <div className="text-center mb-10">
          <h2 className="text-2xl sm:text-3xl lg:text-[36px] font-semibold text-[#202522] tracking-tight">
            Frequently asked questions
          </h2>
          <p className="mt-2 text-xs sm:text-sm text-[#5E625D]">
            Clear answers about DawaiFlow and everyday counter use.
          </p>
        </div>

        <div className="space-y-2.5">
          {faqs.map((faq, index) => {
            const isOpen = openIndex === index;
            return (
              <div
                key={faq.q}
                className="rounded-xl bg-[#FFFFFF] border border-[#DCDDD5] overflow-hidden transition-colors shadow-2xs"
              >
                <button
                  type="button"
                  onClick={() => setOpenIndex(isOpen ? null : index)}
                  className="w-full px-5 py-4 text-left font-medium text-[#202522] flex items-center justify-between gap-4 hover:text-[#526B5A] focus:outline-none transition-colors cursor-pointer"
                  aria-expanded={isOpen}
                >
                  <span className="text-[15px] sm:text-base">{faq.q}</span>
                  <ChevronDown
                    className={`w-4 h-4 text-[#5E625D] shrink-0 transition-transform duration-150 ${
                      isOpen ? 'rotate-180 text-[#526B5A]' : ''
                    }`}
                  />
                </button>

                {isOpen && (
                  <div className="px-5 pb-5 pt-1 text-[14px] sm:text-[15px] text-[#5E625D] leading-relaxed border-t border-[#DCDDD5]/60 bg-[#FAF9F5]">
                    {faq.a}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};
