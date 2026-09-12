import React, { useState } from 'react';
import { X, CheckCircle2, Send } from 'lucide-react';
import { PilotApplication } from '../types';

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
    pharmacyType: 'independent',
    estimatedDailyBills: '50-150',
    notes: '',
  });

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    setTimeout(() => {
      try {
        const existing = JSON.parse(localStorage.getItem('dawaiflow_pilot_submissions') || '[]');
        existing.push({
          ...formData,
          submittedAt: new Date().toISOString(),
        });
        localStorage.setItem('dawaiflow_pilot_submissions', JSON.stringify(existing));
      } catch (err) {
        // Safe fallback
      }

      setIsSubmitting(false);
      setIsSubmitted(true);
    }, 500);
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
              <CheckCircle2 className="w-6 h-6" />
            </div>

            <h3 className="text-xl font-semibold text-[#202522]">Pilot Request Received</h3>

            <p className="text-sm text-[#5E625D] max-w-md mx-auto leading-relaxed">
              Thank you for your interest in DawaiFlow for <strong className="text-[#202522]">{formData.pharmacyName}</strong>. Our team will contact you at <span className="font-mono text-[#202522]">{formData.phone}</span> to coordinate your walkthrough.
            </p>

            <button
              type="button"
              onClick={() => {
                setIsSubmitted(false);
                onClose();
              }}
              className="px-6 py-2.5 bg-[#526B5A] hover:bg-[#43584a] text-white font-medium rounded-lg text-sm transition-colors cursor-pointer"
            >
              Done
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <h3 id="pilot-modal-title" className="text-xl font-semibold text-[#202522]">
                Request a DawaiFlow Pilot
              </h3>
              <p className="text-xs sm:text-sm text-[#5E625D] mt-1">
                Tell us about your pharmacy to try DawaiFlow.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 pt-1">
              <div className="space-y-1">
                <label className="text-xs font-medium text-[#5E625D]">Pharmacy / Store Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Apollo Medical Store"
                  value={formData.pharmacyName}
                  onChange={(e) => setFormData({ ...formData, pharmacyName: e.target.value })}
                  className="w-full px-3 py-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-lg text-sm text-[#202522] placeholder-[#5E625D]/60 focus:outline-none focus:border-[#526B5A]"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-[#5E625D]">Contact Person Name *</label>
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
                <label className="text-xs font-medium text-[#5E625D]">Phone / WhatsApp *</label>
                <input
                  type="tel"
                  required
                  placeholder="e.g. +91 98765 43210"
                  value={formData.phone}
                  onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                  className="w-full px-3 py-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-lg text-sm text-[#202522] font-mono placeholder-[#5E625D]/60 focus:outline-none focus:border-[#526B5A]"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-[#5E625D]">Email Address *</label>
                <input
                  type="email"
                  required
                  placeholder="e.g. ramesh@gmail.com"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="w-full px-3 py-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-lg text-sm text-[#202522] placeholder-[#5E625D]/60 focus:outline-none focus:border-[#526B5A]"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-[#5E625D]">City / State *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Jaipur, Rajasthan"
                  value={formData.city}
                  onChange={(e) => setFormData({ ...formData, city: e.target.value })}
                  className="w-full px-3 py-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-lg text-sm text-[#202522] placeholder-[#5E625D]/60 focus:outline-none focus:border-[#526B5A]"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-[#5E625D]">Pharmacy Type *</label>
                <select
                  value={formData.pharmacyType}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      pharmacyType: e.target.value as 'independent' | 'growing_team' | 'modern_chemist',
                    })
                  }
                  className="w-full px-3 py-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-lg text-sm text-[#202522] focus:outline-none focus:border-[#526B5A]"
                >
                  <option value="independent">Independent Pharmacy</option>
                  <option value="growing_team">Growing Pharmacy Team</option>
                  <option value="modern_chemist">Modern Chemist Store</option>
                </select>
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-[#5E625D]">
                Estimated Daily Counter Bills
              </label>
              <select
                value={formData.estimatedDailyBills}
                onChange={(e) => setFormData({ ...formData, estimatedDailyBills: e.target.value })}
                className="w-full px-3 py-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-lg text-sm text-[#202522] focus:outline-none focus:border-[#526B5A]"
              >
                <option value="<50">Under 50 bills / day</option>
                <option value="50-150">50 – 150 bills / day</option>
                <option value="150-400">150 – 400 bills / day</option>
                <option value="400+">400+ bills / day</option>
              </select>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-[#5E625D]">
                Any specific areas you want to improve? (Optional)
              </label>
              <textarea
                rows={2}
                placeholder="e.g. Faster counter billing, expiry tracking, or reducing typing on purchase bills."
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                className="w-full px-3 py-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-lg text-sm text-[#202522] placeholder-[#5E625D]/60 focus:outline-none focus:border-[#526B5A]"
              />
            </div>

            <div className="pt-2 space-y-2">
              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full py-2.5 bg-[#526B5A] hover:bg-[#43584a] disabled:opacity-50 text-white font-medium rounded-lg text-sm flex items-center justify-center gap-2 transition-colors cursor-pointer"
              >
                {isSubmitting ? (
                  <span>Sending Request...</span>
                ) : (
                  <>
                    <span>Submit Pilot Request</span>
                    <Send className="w-3.5 h-3.5" />
                  </>
                )}
              </button>

              <p className="text-[11px] text-[#5E625D] text-center leading-normal">
                By submitting, you agree to our{' '}
                {onOpenLegal ? (
                  <button
                    type="button"
                    onClick={() => onOpenLegal('terms')}
                    className="underline text-[#202522] hover:text-[#526B5A]"
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
                    className="underline text-[#202522] hover:text-[#526B5A]"
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
