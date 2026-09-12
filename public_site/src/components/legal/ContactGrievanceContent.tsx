import React, { useState } from 'react';
import { APP_CONFIG } from '../../config/appConfig';
import { Shield, Mail, Phone, MapPin, Send, CheckCircle2, MessageSquare, Copy, Check } from 'lucide-react';

export const ContactGrievanceContent: React.FC = () => {
  const [copied, setCopied] = useState(false);
  const [reqSubject, setReqSubject] = useState('Data Access Request');
  const [reqMessage, setReqMessage] = useState('');
  const [reqSent, setReqSent] = useState(false);

  const handleCopyEmail = () => {
    navigator.clipboard.writeText(APP_CONFIG.grievanceEmail);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleQuickRequest = (e: React.FormEvent) => {
    e.preventDefault();
    const mailtoLink = `mailto:${APP_CONFIG.grievanceEmail}?subject=${encodeURIComponent(
      `[DawaiFlow Grievance/Request] ${reqSubject}`
    )}&body=${encodeURIComponent(reqMessage)}`;
    window.location.href = mailtoLink;
    setReqSent(true);
  };

  return (
    <article className="space-y-8 text-[#202522] leading-relaxed text-[15px]">
      {/* Header */}
      <div className="p-4 sm:p-5 rounded-xl bg-[#EDECE6] border border-[#DCDDD5] space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-[#526B5A]">
            Official Support & Grievance Redressal
          </span>
          <span className="text-xs text-[#5E625D]">
            Statutory Channel (DPDP Act, 2023)
          </span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-[#202522]">
          Contact & Grievance Redressal
        </h1>
        <p className="text-xs sm:text-sm text-[#5E625D]">
          Designated channels for technical support, pharmacy partner inquiries, and statutory data protection requests.
        </p>
      </div>

      {/* Official Details Card */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Officer Card */}
        <div className="p-5 rounded-xl bg-[#FFFFFF] border border-[#DCDDD5] space-y-3 shadow-2xs">
          <div className="flex items-center gap-2.5 text-[#202522]">
            <div className="w-8 h-8 rounded-lg bg-[#EDECE6] border border-[#DCDDD5] flex items-center justify-center text-[#526B5A]">
              <Shield className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-base font-semibold">Data Protection & Grievance Officer</h2>
              <p className="text-xs text-[#5E625D]">{APP_CONFIG.founderAndOfficer}</p>
            </div>
          </div>

          <div className="space-y-2 text-xs sm:text-sm text-[#5E625D] pt-2 border-t border-[#DCDDD5]/60">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-[#202522]">Official Email:</span>
              <div className="flex items-center gap-1.5">
                <a href={`mailto:${APP_CONFIG.grievanceEmail}`} className="text-[#526B5A] font-medium underline">
                  {APP_CONFIG.grievanceEmail}
                </a>
                <button
                  type="button"
                  onClick={handleCopyEmail}
                  className="p-1 text-[#5E625D] hover:text-[#202522] rounded transition-colors cursor-pointer"
                  title="Copy email address"
                  aria-label="Copy email address"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-[#526B5A]" /> : <Copy className="w-3.5 h-3.5" />}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-[#202522]">Support Phone:</span>
              <a href={`tel:${APP_CONFIG.supportPhone}`} className="text-[#526B5A] font-medium">
                {APP_CONFIG.supportPhone}
              </a>
            </div>

            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-[#202522]">WhatsApp:</span>
              <a
                href={APP_CONFIG.whatsAppUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[#526B5A] font-medium underline"
              >
                Chat on WhatsApp
              </a>
            </div>

            <div className="flex items-start justify-between gap-2 pt-1">
              <span className="font-medium text-[#202522]">Operating Location:</span>
              <span className="text-right text-[#202522]">{APP_CONFIG.location}</span>
            </div>
          </div>
        </div>

        {/* Corporate Entity Placeholders Card */}
        <div className="p-5 rounded-xl bg-[#FAF9F5] border border-[#DCDDD5] space-y-3">
          <div className="flex items-center gap-2.5 text-[#202522]">
            <div className="w-8 h-8 rounded-lg bg-[#EDECE6] border border-[#DCDDD5] flex items-center justify-center text-[#526B5A]">
              <MapPin className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-base font-semibold">Corporate & Legal Information</h2>
              <p className="text-xs text-[#5E625D]">Statutory business records</p>
            </div>
          </div>

          <div className="space-y-1.5 text-xs text-[#5E625D] pt-2 border-t border-[#DCDDD5]/60">
            <p><strong>Legal Entity:</strong> {APP_CONFIG.legalEntityPlaceholder}</p>
            <p><strong>Registered Office:</strong> {APP_CONFIG.registeredOfficePlaceholder}</p>
            <p><strong>Corporate Identification:</strong> {APP_CONFIG.cinPlaceholder}</p>
            <p><strong>GST Registration:</strong> {APP_CONFIG.gstinPlaceholder}</p>
            <p><strong>General Support:</strong> {APP_CONFIG.supportEmail}</p>
          </div>
        </div>
      </div>

      {/* Grievance Procedure */}
      <section className="space-y-3">
        <h2 className="text-lg sm:text-xl font-semibold text-[#202522]">
          Grievance Handling Procedure & Resolution Timelines
        </h2>
        <p className="text-sm text-[#5E625D]">
          Under the <strong>Digital Personal Data Protection Act, 2023</strong> and the <strong>Information Technology (Intermediary Guidelines and Digital Media Ethics Code) Rules, 2021</strong>, any pharmacy partner or individual may submit a privacy grievance, data access request, or data correction/erasure request:
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
          <div className="p-3.5 rounded-lg bg-[#FFFFFF] border border-[#DCDDD5] space-y-1">
            <span className="text-xs font-mono font-semibold text-[#526B5A]">Step 1: Submission</span>
            <h4 className="font-semibold text-[#202522]">Send Written Request</h4>
            <p className="text-xs text-[#5E625D]">
              Email your concern, registered pharmacy name, and specific request to <strong className="text-[#202522]">{APP_CONFIG.grievanceEmail}</strong>.
            </p>
          </div>

          <div className="p-3.5 rounded-lg bg-[#FFFFFF] border border-[#DCDDD5] space-y-1">
            <span className="text-xs font-mono font-semibold text-[#526B5A]">Step 2: Acknowledgment</span>
            <h4 className="font-semibold text-[#202522]">Within 48 Hours</h4>
            <p className="text-xs text-[#5E625D]">
              Our Grievance Officer will issue a unique ticket reference code and confirm receipt of your grievance.
            </p>
          </div>

          <div className="p-3.5 rounded-lg bg-[#FFFFFF] border border-[#DCDDD5] space-y-1">
            <span className="text-xs font-mono font-semibold text-[#526B5A]">Step 3: Redressal</span>
            <h4 className="font-semibold text-[#202522]">Within 30 Days</h4>
            <p className="text-xs text-[#5E625D]">
              Full resolution, corrective data updates, or complete data erasure completed and confirmed in writing.
            </p>
          </div>
        </div>
      </section>

      {/* Quick Launch Data Request Form */}
      <section className="p-5 rounded-xl bg-[#FFFFFF] border border-[#DCDDD5] space-y-4">
        <div>
          <h3 className="text-base font-semibold text-[#202522]">
            Send a Privacy or Data Request Directly
          </h3>
          <p className="text-xs sm:text-sm text-[#5E625D] mt-0.5">
            Use this quick assistant to draft a formal request directly to our Grievance Officer.
          </p>
        </div>

        <form onSubmit={handleQuickRequest} className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-[#5E625D]">Request Type</label>
              <select
                value={reqSubject}
                onChange={(e) => setReqSubject(e.target.value)}
                className="w-full px-3 py-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-lg text-sm text-[#202522] focus:outline-none focus:border-[#526B5A]"
              >
                <option value="Data Access Request">Data Access Request (DPDP Act)</option>
                <option value="Data Correction Request">Data Correction / Update</option>
                <option value="Account & Data Erasure Request">Account & Data Erasure (Deletion)</option>
                <option value="Consent Withdrawal">Consent Withdrawal</option>
                <option value="General Support Grievance">General Support Grievance</option>
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-[#5E625D]">Direct Recipient</label>
              <input
                type="text"
                disabled
                value={APP_CONFIG.grievanceEmail}
                className="w-full px-3 py-2 bg-[#FAF9F5] border border-[#DCDDD5] rounded-lg text-sm text-[#5E625D] font-mono cursor-not-allowed"
              />
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-[#5E625D]">Details of Your Request</label>
            <textarea
              rows={3}
              required
              placeholder="Describe your pharmacy name, phone number, and specific request or grievance..."
              value={reqMessage}
              onChange={(e) => setReqMessage(e.target.value)}
              className="w-full px-3 py-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-lg text-sm text-[#202522] placeholder-[#5E625D]/60 focus:outline-none focus:border-[#526B5A]"
            />
          </div>

          <button
            type="submit"
            className="px-5 py-2.5 bg-[#526B5A] hover:bg-[#43584a] text-white font-medium rounded-lg text-sm flex items-center gap-2 transition-colors cursor-pointer"
          >
            <span>Open Email to Grievance Officer</span>
            <Send className="w-3.5 h-3.5" />
          </button>
        </form>
      </section>
    </article>
  );
};
