import React from 'react';
import { APP_CONFIG } from '../config/appConfig';
import { LegalDocType } from './legal/LegalModal';

interface FooterProps {
  onOpenPilot: () => void;
  onOpenLegal: (doc: LegalDocType) => void;
}

export const Footer: React.FC<FooterProps> = ({ onOpenPilot, onOpenLegal }) => {
  const handleNavClick = (e: React.MouseEvent<HTMLAnchorElement>, href: string) => {
    e.preventDefault();
    const element = document.querySelector(href);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <footer className="py-14 bg-[#F5F4EF] border-t border-[#DCDDD5] text-[#202522]">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 space-y-10">
        {/* Top Tier: Brand, Nav & Legal Links */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-8 items-start">
          {/* Brand Column */}
          <div className="md:col-span-4 space-y-3">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md bg-[#526B5A] flex items-center justify-center text-white">
                <div className="w-3 h-3 relative">
                  <span className="absolute inset-x-0.5 inset-y-0 bg-white rounded-xs" />
                  <span className="absolute inset-y-0.5 inset-x-0 bg-white rounded-xs" />
                </div>
              </div>
              <span className="text-lg font-semibold tracking-tight text-[#202522]">
                DawaiFlow
              </span>
            </div>
            <p className="text-xs sm:text-sm text-[#5E625D] leading-relaxed">
              {APP_CONFIG.tagline}
            </p>
            <div className="pt-1 text-xs text-[#5E625D] space-y-1">
              <p>
                <strong>Support & Grievances:</strong>{' '}
                <a
                  href={`mailto:${APP_CONFIG.grievanceEmail}`}
                  className="text-[#526B5A] hover:underline"
                >
                  {APP_CONFIG.grievanceEmail}
                </a>
              </p>
              <p>
                <strong>Phone / WhatsApp:</strong>{' '}
                <a
                  href={`tel:${APP_CONFIG.supportPhone}`}
                  className="text-[#526B5A] hover:underline"
                >
                  {APP_CONFIG.supportPhone}
                </a>
              </p>
            </div>
          </div>

          {/* Navigation Links */}
          <div className="md:col-span-4 space-y-2.5">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-[#202522]">
              Navigation
            </h4>
            <ul className="space-y-2 text-xs sm:text-sm text-[#5E625D]">
              <li>
                <a
                  href="#product"
                  onClick={(e) => handleNavClick(e, '#product')}
                  className="hover:text-[#202522] transition-colors"
                >
                  Product Overview
                </a>
              </li>
              <li>
                <a
                  href="#workflow-demo"
                  onClick={(e) => handleNavClick(e, '#workflow-demo')}
                  className="hover:text-[#202522] transition-colors"
                >
                  How Counter Workflow Works
                </a>
              </li>
              <li>
                <a
                  href="#features"
                  onClick={(e) => handleNavClick(e, '#features')}
                  className="hover:text-[#202522] transition-colors"
                >
                  Features & Batch Inventory
                </a>
              </li>
              <li>
                <a
                  href="#pilot"
                  onClick={(e) => handleNavClick(e, '#pilot')}
                  className="hover:text-[#202522] transition-colors"
                >
                  Pilot Onboarding Program
                </a>
              </li>
              <li>
                <a
                  href="#contact"
                  onClick={(e) => handleNavClick(e, '#contact')}
                  className="hover:text-[#202522] transition-colors"
                >
                  Get in Touch
                </a>
              </li>
              <li>
                <button
                  type="button"
                  onClick={onOpenPilot}
                  className="hover:text-[#202522] text-[#526B5A] font-medium transition-colors cursor-pointer text-left"
                >
                  Request a Free Pilot →
                </button>
              </li>
            </ul>
          </div>

          {/* Legal & Compliance Column */}
          <div className="md:col-span-4 space-y-2.5">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-[#202522]">
              Legal, Compliance & Data
            </h4>
            <ul className="space-y-2 text-xs sm:text-sm text-[#5E625D]">
              <li>
                <button
                  type="button"
                  onClick={() => onOpenLegal('terms')}
                  className="hover:text-[#202522] transition-colors cursor-pointer text-left"
                >
                  Terms of Use
                </button>
              </li>
              <li>
                <button
                  type="button"
                  onClick={() => onOpenLegal('privacy')}
                  className="hover:text-[#202522] transition-colors cursor-pointer text-left"
                >
                  Privacy Policy (DPDP Act, 2023)
                </button>
              </li>
              <li>
                <button
                  type="button"
                  onClick={() => onOpenLegal('data-policy')}
                  className="hover:text-[#202522] transition-colors cursor-pointer text-left"
                >
                  Data & App Information
                </button>
              </li>
              <li>
                <button
                  type="button"
                  onClick={() => onOpenLegal('disclaimer')}
                  className="hover:text-[#202522] transition-colors cursor-pointer text-left"
                >
                  Pharmacy & Medical Disclaimer
                </button>
              </li>
              <li>
                <button
                  type="button"
                  onClick={() => onOpenLegal('contact-grievance')}
                  className="hover:text-[#202522] transition-colors cursor-pointer text-left"
                >
                  Contact & Grievance Redressal
                </button>
              </li>
            </ul>
          </div>
        </div>

        {/* Middle Notice: Explicit Non-E-Commerce & Pharmacy Scope */}
        <div className="p-4 rounded-xl bg-[#EDECE6]/80 border border-[#DCDDD5] text-xs text-[#5E625D] space-y-1">
          <p className="font-semibold text-[#202522]">
            Pharmacy Operations Platform Notice:
          </p>
          <p>
            DawaiFlow is business management and billing software built for licensed retail pharmacies in India. DawaiFlow is NOT an online pharmacy, does not sell or distribute medicines to consumers, and does not provide medicine delivery services. All prescription verification and dispensing occurs physically by licensed pharmacists at the pharmacy retail counter.
          </p>
        </div>

        {/* Bottom Bar: Copyright & Contact */}
        <div className="pt-4 border-t border-[#DCDDD5] flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-[#5E625D]">
          <div>
            © 2026 DawaiFlow. All rights reserved.
          </div>
          <div className="flex flex-wrap items-center justify-center gap-4 text-xs">
            <span>Location: {APP_CONFIG.location}</span>
            <span>•</span>
            <a href={`tel:${APP_CONFIG.supportPhone}`} className="hover:text-[#202522]">
              {APP_CONFIG.supportPhone}
            </a>
            <span>•</span>
            <a href={`mailto:${APP_CONFIG.grievanceEmail}`} className="hover:text-[#202522]">
              {APP_CONFIG.grievanceEmail}
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
};
