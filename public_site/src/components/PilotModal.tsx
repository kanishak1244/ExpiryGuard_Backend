import React, { useState } from 'react';
import { X, CheckCircle2, Send, MessageCircle, AlertCircle, Loader2 } from 'lucide-react';
import { PilotApplication } from '../types';
import { getWhatsAppInquiryUrl, getPilotWhatsAppUrl } from '../config/appConfig';

interface PilotModalProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenLegal?: (doc: 'privacy' | 'terms') => void;
}

export const PilotModal: React.FC<PilotModalProps> = ({ isOpen, onClose, onOpenLegal }) => {
  const [formData, setFormData] = useState<PilotApplication>({
    pharmacyName: '',
    contactPerson: '',
    phone: '',
    email: '',
    city: '',
    currentBillingMethod: 'Any Existing Software',
    estimatedDailyBills: '50–100',
    numPharmacies: '1 Outlet',
    notes: '',
  });

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    // Client-side validation
    const cleanPhone = formData.phone.replace(/[^\d+]/g, '');
    if (cleanPhone.length < 10) {
      setErrorMessage('Please enter a valid phone number (at least 10 digits).');
      return;
    }

    setIsSubmitting(true);

    try {
      // Directly open WhatsApp click-to-chat with pre-filled pilot message
      const whatsappUrl = getPilotWhatsAppUrl();
      window.location.href = whatsappUrl;
      setIsSubmitted(true);
    } catch (err: any) {
      console.error('WhatsApp redirect error:', err);
      setErrorMessage(
        'Could not open WhatsApp automatically. Please click the WhatsApp button below to connect directly.'
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs overflow-y-auto">
      <div
        className="relative w-full max-w-lg rounded-xl bg-[#F5F4EF] border border-[#DCDDD5] shadow-lg p-6 sm:p-7 text-[#202522] my-8 max-h-[90vh] overflow-y-auto"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pilot-modal-title"
      >
        {/* Close Button */}
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 p-1.5 text-[#5E625D] hover:text-[#202522] rounded-md hover:bg-[#EDECE6] transition-colors cursor-pointer"
          aria-label="Close dialog"
        >
          <X className="w-4 h-4" />
        </button>

        {isSubmitted ? (
          <div className="text-center py-6 space-y-4">
            <div className="w-12 h-12 rounded-xl bg-[#EDECE6] border border-[#DCDDD5] text-[#526B5A] flex items-center justify-center mx-auto">
              <CheckCircle2 className="w-6 h-6 text-[#526B5A]" />
            </div>

            <h3 className="text-xl font-semibold text-[#202522]">Opening WhatsApp...</h3>

            <p className="text-sm text-[#5E625D] max-w-md mx-auto leading-relaxed">
              Redirecting to WhatsApp to send your pilot inquiry for{' '}
              <strong className="text-[#202522]">{formData.pharmacyName}</strong>. If WhatsApp did not open automatically, click the button below.
            </p>

            <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-3">
              <a
                href={getPilotWhatsAppUrl()}
                className="w-full sm:w-auto px-5 py-2.5 bg-[#526B5A] hover:bg-[#43584a] text-white font-medium rounded-lg text-sm flex items-center justify-center gap-2 transition-colors cursor-pointer"
              >
                <MessageCircle className="w-4 h-4 text-[#25D366]" />
                <span>Open WhatsApp</span>
              </a>

              <button
                type="button"
                onClick={() => {
                  setIsSubmitted(false);
                  onClose();
                }}
                className="w-full sm:w-auto px-6 py-2.5 bg-transparent hover:bg-[#EDECE6] text-[#202522] border border-[#DCDDD5] font-medium rounded-lg text-sm transition-colors cursor-pointer"
              >
                Done
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <h3 id="pilot-modal-title" className="text-xl font-semibold text-[#202522]">
                Request a DawaiFlow Pilot
              </h3>
              <p className="text-xs sm:text-sm text-[#5E625D] mt-1">
                Tell us about your pharmacy. We&apos;ll get in touch to walk you through the pilot.
              </p>
            </div>

            {errorMessage && (
              <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-start gap-2">
                <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <div className="flex-1">
                  <span>{errorMessage}</span>
                  <div className="mt-1">
                    <a
                      href={getPilotWhatsAppUrl()}
                      className="underline font-medium hover:text-red-900 inline-flex items-center gap-1"
                    >
                      <MessageCircle className="w-3 h-3 text-[#25D366]" />
                      <span>Or connect directly on WhatsApp</span>
                    </a>
                  </div>
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 pt-1">
              <div className="space-y-1">
                <label className="text-xs font-medium text-[#5E625D]">Full Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Ramesh Kumar"
                  value={formData.contactPerson}
                  onChange={(e) => setFormData({ ...formData, contactPerson: e.target.value })}
                  className="w-full px-3 py-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-lg text-sm text-[#202522] placeholder-[#5E625D]/60 focus:outline-none focus:border-[#526B5A]"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-[#5E625D]">Pharmacy Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Sanjeevani Medicos"
                  value={formData.pharmacyName}
                  onChange={(e) => setFormData({ ...formData, pharmacyName: e.target.value })}
                  className="w-full px-3 py-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-lg text-sm text-[#202522] placeholder-[#5E625D]/60 focus:outline-none focus:border-[#526B5A]"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-[#5E625D]">City / Town *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Sonipat, Ahmedabad, Jaipur"
                  value={formData.city}
                  onChange={(e) => setFormData({ ...formData, city: e.target.value })}
                  className="w-full px-3 py-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-lg text-sm text-[#202522] placeholder-[#5E625D]/60 focus:outline-none focus:border-[#526B5A]"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-[#5E625D]">Phone (WhatsApp) *</label>
                <input
                  type="tel"
                  required
                  placeholder="e.g. 9817066533"
                  value={formData.phone}
                  onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                  className="w-full px-3 py-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-lg text-sm text-[#202522] font-mono placeholder-[#5E625D]/60 focus:outline-none focus:border-[#526B5A]"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-[#5E625D]">Current Billing Software *</label>
                <select
                  value={formData.currentBillingMethod}
                  onChange={(e) => setFormData({ ...formData, currentBillingMethod: e.target.value })}
                  className="w-full px-3 py-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-lg text-sm text-[#202522] focus:outline-none focus:border-[#526B5A]"
                >
                  <option value="Any Existing Software">Any Existing Software</option>
                  <option value="Paper / Manual">Paper / Manual Billing</option>
                  <option value="Other">Other Software</option>
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-[#5E625D]">Approximate Bills Per Day *</label>
                <select
                  value={formData.estimatedDailyBills}
                  onChange={(e) => setFormData({ ...formData, estimatedDailyBills: e.target.value })}
                  className="w-full px-3 py-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-lg text-sm text-[#202522] focus:outline-none focus:border-[#526B5A]"
                >
                  <option value="Under 50">Under 50 bills / day</option>
                  <option value="50–100">50–100 bills / day</option>
                  <option value="100–200">100–200 bills / day</option>
                  <option value="200+">200+ bills / day</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
              <div className="space-y-1">
                <label className="text-xs font-medium text-[#5E625D]">Number of Pharmacies</label>
                <select
                  value={formData.numPharmacies}
                  onChange={(e) => setFormData({ ...formData, numPharmacies: e.target.value })}
                  className="w-full px-3 py-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-lg text-sm text-[#202522] focus:outline-none focus:border-[#526B5A]"
                >
                  <option value="1 Outlet">1 Outlet</option>
                  <option value="2-5 Outlets">2-5 Outlets</option>
                  <option value="5+ Outlets">5+ Outlets</option>
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-[#5E625D]">Email Address (Optional)</label>
                <input
                  type="email"
                  placeholder="e.g. pharmacy@gmail.com"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="w-full px-3 py-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-lg text-sm text-[#202522] placeholder-[#5E625D]/60 focus:outline-none focus:border-[#526B5A]"
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-[#5E625D]">
                What is the biggest problem with your current workflow? (Optional)
              </label>
              <textarea
                rows={2}
                placeholder="e.g. Entering bills after rush hours takes 2 hours every evening..."
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                className="w-full px-3 py-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-lg text-sm text-[#202522] placeholder-[#5E625D]/60 focus:outline-none focus:border-[#526B5A]"
              />
            </div>

            <div className="pt-2 space-y-2.5">
              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full py-2.5 bg-[#526B5A] hover:bg-[#43584a] disabled:opacity-50 text-white font-medium rounded-lg text-sm flex items-center justify-center gap-2 transition-colors cursor-pointer shadow-xs active:scale-[0.99]"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Submitting Request...</span>
                  </>
                ) : (
                  <>
                    <span>Submit Pilot Request</span>
                    <Send className="w-3.5 h-3.5" />
                  </>
                )}
              </button>

              <div className="flex items-center justify-between pt-1 border-t border-[#DCDDD5] text-xs text-[#5E625D]">
                <span>Prefer to chat directly?</span>
                <a
                  href={getWhatsAppInquiryUrl(formData.contactPerson)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-[#526B5A] hover:underline font-medium"
                >
                  <MessageCircle className="w-3.5 h-3.5 text-[#25D366]" />
                  <span>Chat on WhatsApp</span>
                </a>
              </div>

              <p className="text-[11px] text-[#5E625D] text-center leading-normal">
                By submitting, you agree to our{' '}
                {onOpenLegal ? (
                  <button
                    type="button"
                    onClick={() => onOpenLegal('terms')}
                    className="underline text-[#202522] hover:text-[#526B5A] cursor-pointer"
                  >
                    Terms
                  </button>
                ) : (
                  <span className="underline">Terms</span>
                )}{' '}
                and{' '}
                {onOpenLegal ? (
                  <button
                    type="button"
                    onClick={() => onOpenLegal('privacy')}
                    className="underline text-[#202522] hover:text-[#526B5A] cursor-pointer"
                  >
                    Privacy Policy
                  </button>
                ) : (
                  <span className="underline">Privacy Policy</span>
                )}
                . Details are used solely for pilot coordination.
              </p>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
