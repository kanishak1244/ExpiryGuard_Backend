import React from 'react';
import { ArrowUpRight, HelpCircle, ShieldAlert } from 'lucide-react';
import { APP_CONFIG, getDirectWhatsAppUrl } from '../config/appConfig';

/**
 * Authentic WhatsApp Brand Icon SVG
 */
const WhatsAppIcon: React.FC<{ className?: string }> = ({ className = 'w-5 h-5' }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill="currentColor"
    aria-hidden="true"
  >
    <path d="M17.472 14.382c-.301-.15-1.78-.878-2.056-.978-.276-.1-.477-.15-.678.15-.201.3-.777.978-.953 1.179-.175.2-.351.225-.652.075-.301-.15-1.27-.468-2.42-1.493-.895-.798-1.5-1.784-1.676-2.085-.175-.3-.019-.463.132-.613.135-.135.301-.35.452-.525.15-.175.201-.3.301-.5.1-.2.05-.375-.025-.525-.075-.15-.678-1.634-.929-2.239-.245-.589-.494-.509-.678-.518-.175-.009-.376-.011-.577-.011-.201 0-.527.075-.803.375-.276.3-1.054 1.03-1.054 2.511 0 1.482 1.08 2.912 1.23 3.113.15.201 2.124 3.243 5.145 4.548.719.311 1.28.497 1.718.636.722.23 1.378.197 1.897.12.578-.087 1.78-.727 2.031-1.43.251-.703.251-1.305.176-1.43-.075-.125-.276-.2-.577-.35zM12.04 2C6.544 2 2.08 6.46 2.08 11.956c0 1.957.568 3.784 1.554 5.334L2 22l4.862-1.583a9.92 9.92 0 0 0 5.178 1.439h.004c5.495 0 9.959-4.461 9.959-9.957A9.96 9.96 0 0 0 12.04 2z" />
  </svg>
);

export const ContactSection: React.FC = () => {
  const whatsAppHref = getDirectWhatsAppUrl();
  const supportHref = `mailto:${APP_CONFIG.supportEmail}`;
  const grievancesHref = `mailto:${APP_CONFIG.grievanceEmail}?subject=${encodeURIComponent('Dawaiflow Grievance')}`;

  return (
    <section
      id="contact"
      className="py-16 sm:py-20 bg-[#F5F4EF] border-t border-[#DCDDD5]/80 text-[#202522]"
      aria-labelledby="contact-heading"
    >
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <div className="text-center max-w-2xl mx-auto mb-10 sm:mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#EDECE6] border border-[#DCDDD5] text-xs font-medium text-[#5E625D] mb-3">
            <span className="w-1.5 h-1.5 rounded-full bg-[#526B5A]" />
            <span>Support &amp; Inquiries</span>
          </div>
          <h2
            id="contact-heading"
            className="text-2xl sm:text-3xl font-semibold tracking-tight text-[#202522]"
          >
            Get in Touch
          </h2>
          <p className="mt-2 text-sm sm:text-base text-[#5E625D] leading-relaxed">
            Have questions about the pilot, need support with your counter, or want to speak with our team? Choose the channel that suits you best.
          </p>
        </div>

        {/* 3 Clear Contact Options Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 sm:gap-6">
          {/* Option 1: WhatsApp */}
          <a
            id="contact-option-whatsapp"
            href={whatsAppHref}
            target="_blank"
            rel="noopener noreferrer"
            className="group flex flex-col justify-between p-6 bg-[#FFFFFF] rounded-xl border border-[#DCDDD5] hover:border-[#526B5A]/60 hover:shadow-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-[#526B5A] focus-visible:ring-offset-2 transition-all cursor-pointer"
            aria-label="WhatsApp: Chat with our team"
          >
            <div>
              <div className="w-10 h-10 rounded-lg bg-[#EBF7EE] text-[#25D366] flex items-center justify-center mb-4 transition-transform group-hover:scale-105">
                <WhatsAppIcon className="w-5 h-5" />
              </div>
              <h3 className="text-base sm:text-lg font-semibold text-[#202522] tracking-tight">
                WhatsApp
              </h3>
              <p className="mt-1.5 text-xs sm:text-sm text-[#5E625D] leading-relaxed">
                Chat with our team
              </p>
            </div>

            <div className="mt-6 pt-4 border-t border-[#DCDDD5]/60 flex items-center justify-between text-xs font-medium text-[#526B5A]">
              <span className="text-[#5E625D] font-mono text-[11px] sm:text-xs">
                {APP_CONFIG.supportPhoneFormatted}
              </span>
              <span className="inline-flex items-center gap-1 group-hover:underline">
                Chat Now
                <ArrowUpRight className="w-3.5 h-3.5" />
              </span>
            </div>
          </a>

          {/* Option 2: Support */}
          <a
            id="contact-option-support"
            href={supportHref}
            className="group flex flex-col justify-between p-6 bg-[#FFFFFF] rounded-xl border border-[#DCDDD5] hover:border-[#526B5A]/60 hover:shadow-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-[#526B5A] focus-visible:ring-offset-2 transition-all cursor-pointer"
            aria-label="Support: Need help with Dawaiflow? Our team is here to help."
          >
            <div>
              <div className="w-10 h-10 rounded-lg bg-[#EDECE6] text-[#526B5A] flex items-center justify-center mb-4 transition-transform group-hover:scale-105">
                <HelpCircle className="w-5 h-5" />
              </div>
              <h3 className="text-base sm:text-lg font-semibold text-[#202522] tracking-tight">
                Support
              </h3>
              <p className="mt-1.5 text-xs sm:text-sm text-[#5E625D] leading-relaxed">
                Need help with Dawaiflow? Our team is here to help.
              </p>
            </div>

            <div className="mt-6 pt-4 border-t border-[#DCDDD5]/60 flex items-center justify-between text-xs font-medium text-[#526B5A]">
              <span className="text-[#5E625D] font-mono text-[11px] sm:text-xs">
                {APP_CONFIG.supportEmail}
              </span>
              <span className="inline-flex items-center gap-1 group-hover:underline">
                Email Us
                <ArrowUpRight className="w-3.5 h-3.5" />
              </span>
            </div>
          </a>

          {/* Option 3: Grievances */}
          <a
            id="contact-option-grievances"
            href={grievancesHref}
            className="group flex flex-col justify-between p-6 bg-[#FFFFFF] rounded-xl border border-[#DCDDD5] hover:border-[#526B5A]/60 hover:shadow-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-[#526B5A] focus-visible:ring-offset-2 transition-all cursor-pointer"
            aria-label="Grievances: Have a concern or complaint? Let us know."
          >
            <div>
              <div className="w-10 h-10 rounded-lg bg-[#FAF0ED] text-[#8C4A3E] flex items-center justify-center mb-4 transition-transform group-hover:scale-105">
                <ShieldAlert className="w-5 h-5" />
              </div>
              <h3 className="text-base sm:text-lg font-semibold text-[#202522] tracking-tight">
                Grievances
              </h3>
              <p className="mt-1.5 text-xs sm:text-sm text-[#5E625D] leading-relaxed">
                Have a concern or complaint? Let us know.
              </p>
            </div>

            <div className="mt-6 pt-4 border-t border-[#DCDDD5]/60 flex items-center justify-between text-xs font-medium text-[#526B5A]">
              <span className="text-[#5E625D] font-mono text-[11px] sm:text-xs">
                {APP_CONFIG.grievanceEmail}
              </span>
              <span className="inline-flex items-center gap-1 group-hover:underline">
                Email Us
                <ArrowUpRight className="w-3.5 h-3.5" />
              </span>
            </div>
          </a>
        </div>
      </div>
    </section>
  );
};
