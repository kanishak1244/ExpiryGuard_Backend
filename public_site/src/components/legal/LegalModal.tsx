import React, { useEffect } from 'react';
import { X, Printer, Shield, FileText, HardDrive, Stethoscope, Mail } from 'lucide-react';
import { PrivacyPolicyContent } from './PrivacyPolicyContent';
import { TermsOfUseContent } from './TermsOfUseContent';
import { DataPolicyContent } from './DataPolicyContent';
import { MedicalDisclaimerContent } from './MedicalDisclaimerContent';
import { ContactGrievanceContent } from './ContactGrievanceContent';

export type LegalDocType = 'privacy' | 'terms' | 'data-policy' | 'disclaimer' | 'contact-grievance';

interface LegalModalProps {
  isOpen: boolean;
  activeDoc: LegalDocType;
  onClose: () => void;
  onSelectDoc: (doc: LegalDocType) => void;
}

export const LegalModal: React.FC<LegalModalProps> = ({
  isOpen,
  activeDoc,
  onClose,
  onSelectDoc,
}) => {
  // Handle ESC key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const tabs: { id: LegalDocType; label: string; icon: React.FC<{ className?: string }> }[] = [
    { id: 'privacy', label: 'Privacy Policy', icon: Shield },
    { id: 'terms', label: 'Terms of Use', icon: FileText },
    { id: 'data-policy', label: 'Data & App Info', icon: HardDrive },
    { id: 'disclaimer', label: 'Pharmacy Disclaimer', icon: Stethoscope },
    { id: 'contact-grievance', label: 'Contact & Grievance', icon: Mail },
  ];

  const handlePrint = () => {
    window.print();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 md:p-6 bg-black/50 backdrop-blur-xs overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-label="Legal and Compliance Documents"
    >
      <div className="relative w-full max-w-4xl max-h-[92vh] flex flex-col rounded-2xl bg-[#F5F4EF] border border-[#DCDDD5] shadow-2xl overflow-hidden my-auto text-[#202522]">
        {/* Top Header Bar */}
        <div className="px-4 sm:px-6 py-3.5 bg-[#EDECE6] border-b border-[#DCDDD5] flex items-center justify-between gap-4 shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-[#526B5A] flex items-center justify-center text-white">
              <div className="w-3 h-3 relative">
                <span className="absolute inset-x-0.5 inset-y-0 bg-white rounded-xs" />
                <span className="absolute inset-y-0.5 inset-x-0 bg-white rounded-xs" />
              </div>
            </div>
            <span className="text-sm sm:text-base font-semibold text-[#202522] tracking-tight">
              DawaiFlow Compliance & Transparency
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handlePrint}
              className="p-1.5 text-[#5E625D] hover:text-[#202522] rounded-md hover:bg-[#DCDDD5]/50 transition-colors cursor-pointer"
              title="Print document"
              aria-label="Print document"
            >
              <Printer className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 text-[#5E625D] hover:text-[#202522] rounded-md hover:bg-[#DCDDD5]/50 transition-colors cursor-pointer"
              aria-label="Close dialog"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="px-4 sm:px-6 bg-[#EDECE6]/50 border-b border-[#DCDDD5] flex items-center gap-1 sm:gap-2 overflow-x-auto no-scrollbar py-2 shrink-0">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeDoc === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => onSelectDoc(tab.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium whitespace-nowrap transition-colors cursor-pointer ${
                  isActive
                    ? 'bg-[#526B5A] text-white shadow-xs'
                    : 'text-[#5E625D] hover:text-[#202522] hover:bg-[#EDECE6]'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Content Area with independent scrolling */}
        <div className="p-4 sm:p-7 overflow-y-auto flex-1 bg-[#F5F4EF]">
          {activeDoc === 'privacy' && <PrivacyPolicyContent />}
          {activeDoc === 'terms' && <TermsOfUseContent />}
          {activeDoc === 'data-policy' && <DataPolicyContent />}
          {activeDoc === 'disclaimer' && <MedicalDisclaimerContent />}
          {activeDoc === 'contact-grievance' && <ContactGrievanceContent />}
        </div>

        {/* Bottom Bar */}
        <div className="px-4 sm:px-6 py-3 bg-[#EDECE6] border-t border-[#DCDDD5] flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-[#5E625D] shrink-0">
          <div>
            © 2026 DawaiFlow. All rights reserved. • Licensed retail pharmacy software.
          </div>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-[#DCDDD5] hover:bg-[#cfd0c6] text-[#202522] font-medium transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
