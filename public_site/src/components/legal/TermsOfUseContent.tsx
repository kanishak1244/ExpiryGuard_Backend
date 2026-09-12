import React from 'react';
import { APP_CONFIG } from '../../config/appConfig';
import { FileText, ShieldAlert, Scale, CheckCircle2, AlertTriangle } from 'lucide-react';

export const TermsOfUseContent: React.FC = () => {
  return (
    <article className="space-y-8 text-[#202522] leading-relaxed text-[15px]">
      {/* Header Banner */}
      <div className="p-4 sm:p-5 rounded-xl bg-[#EDECE6] border border-[#DCDDD5] space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-[#526B5A]">
            Terms of Service & User Agreement
          </span>
          <span className="text-xs text-[#5E625D]">
            Last Updated: September 2026
          </span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-[#202522]">
          Terms of Use
        </h1>
        <p className="text-xs sm:text-sm text-[#5E625D]">
          {APP_CONFIG.brandName} • Governed by the Laws of India
        </p>
      </div>

      {/* 1. Acceptance */}
      <section className="space-y-3">
        <h2 className="text-lg sm:text-xl font-semibold text-[#202522] flex items-center gap-2">
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-[#EDECE6] text-[#526B5A]">1</span>
          Acceptance of Terms
        </h2>
        <p>
          By accessing this website, requesting a pilot walkthrough, creating a pharmacist account, or using the DawaiFlow software application (the &quot;Service&quot;), you agree to be bound by these Terms of Use (&quot;Terms&quot;). These Terms constitute a binding legal agreement between you (&quot;User&quot;, &quot;Pharmacist&quot;, or &quot;Pharmacy&quot;) and {APP_CONFIG.founderAndOfficer}, trading under the product brand &quot;{APP_CONFIG.brandName}&quot; (&quot;we&quot;, &quot;us&quot;, &quot;our&quot;).
        </p>
        <p className="text-sm text-[#5E625D]">
          If you do not agree to these Terms, you must not access or use the DawaiFlow website or application.
        </p>
      </section>

      {/* 2. Description & Not an Online Pharmacy */}
      <section className="space-y-3">
        <h2 className="text-lg sm:text-xl font-semibold text-[#202522] flex items-center gap-2">
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-[#EDECE6] text-[#526B5A]">2</span>
          Description of Service & Non-E-Commerce Status
        </h2>
        <p>
          DawaiFlow is business-to-business (B2B) counter workflow, inventory tracking, and billing automation software designed specifically for physical, licensed retail pharmacies and chemists in India.
        </p>
        <div className="p-4 rounded-xl bg-[#FAF9F5] border border-[#DCDDD5] space-y-2">
          <h3 className="text-sm font-semibold text-[#202522] flex items-center gap-1.5">
            <AlertTriangle className="w-4 h-4 text-[#526B5A]" />
            Explicit Declaration: DawaiFlow is NOT an Online Pharmacy
          </h3>
          <p className="text-xs sm:text-sm text-[#5E625D]">
            DawaiFlow does not sell medicines, does not facilitate online medicine purchases for patients, does not offer medicine home deliveries, and does not operate as an e-pharmacy or consumer marketplace. All billing and medicine dispensing facilitated through DawaiFlow occurs physically over the retail counter of an independently licensed pharmacy.
          </p>
        </div>
      </section>

      {/* 3. Eligibility */}
      <section className="space-y-3">
        <h2 className="text-lg sm:text-xl font-semibold text-[#202522] flex items-center gap-2">
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-[#EDECE6] text-[#526B5A]">3</span>
          Eligibility & Licensed Pharmacist Restrictions
        </h2>
        <p>
          Access to DawaiFlow is restricted to individuals who:
        </p>
        <ul className="list-disc pl-5 space-y-1 text-sm text-[#5E625D]">
          <li>Are at least 18 years of age and legally competent to enter into a contract under the Indian Contract Act, 1872.</li>
          <li>Are registered pharmacists or authorized representatives of a retail chemist store holding valid retail drug sale licenses issued under the <strong>Drugs and Cosmetics Act, 1940</strong> and the <strong>Drugs and Cosmetics Rules, 1945</strong>.</li>
          <li>Operate their pharmacy in strict accordance with the <strong>Pharmacy Act, 1948</strong> and the Pharmacy Practice Regulations.</li>
        </ul>
      </section>

      {/* 4. Pilot & Beta Status */}
      <section className="space-y-3">
        <h2 className="text-lg sm:text-xl font-semibold text-[#202522] flex items-center gap-2">
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-[#EDECE6] text-[#526B5A]">4</span>
          Pilot / Beta Status Transparency
        </h2>
        <p>
          DawaiFlow is currently operating in an early, invite-only <strong>Free Pilot Phase</strong> for selected pharmacy partners in India.
        </p>
        <ul className="list-disc pl-5 space-y-1.5 text-sm text-[#5E625D]">
          <li><strong>No Fees Charged During Pilot:</strong> There are currently no fees or subscription charges to participate in the early pilot. No payment details are collected through this public website.</li>
          <li><strong>Active Development & Feature Iteration:</strong> Functionality, workflows, and visual interfaces are being actively refined. Certain features may change, undergo temporary downtime, or be modified based on pharmacy partner feedback.</li>
          <li><strong>Future Commercial Terms:</strong> When DawaiFlow transitions to generally available commercial subscription plans, comprehensive pricing schedules, billing frequencies, tax invoices, and cancellation terms will be published and communicated well in advance.</li>
        </ul>
      </section>

      {/* 5. Pharmacist Professional Verification Responsibility */}
      <section className="space-y-3 p-5 rounded-xl bg-[#FAF9F5] border border-[#DCDDD5]">
        <h2 className="text-base sm:text-lg font-semibold text-[#202522] flex items-center gap-2">
          <Scale className="w-5 h-5 text-[#526B5A]" />
          5. Mandatory Pharmacist Professional Responsibility
        </h2>
        <p className="text-sm font-medium text-[#202522]">
          DawaiFlow is an administrative support and calculation tool. It does not replace the professional judgment of a registered pharmacist.
        </p>
        <p className="text-xs sm:text-sm text-[#5E625D] leading-relaxed">
          The dispensing pharmacist remains solely and statutorily responsible for:
        </p>
        <ul className="list-disc pl-5 space-y-1 text-xs sm:text-sm text-[#5E625D]">
          <li>Verifying the physical medicine strip, brand identity, chemical composition, and manufacturer.</li>
          <li>Verifying medicine dosage strength, pack size, and unit quantity.</li>
          <li>Confirming the active batch number and expiration date prior to dispensing.</li>
          <li>Mandatory examination and verification of a valid doctor prescription for Schedule H, Schedule H1, Schedule X, and other controlled drugs under Indian law.</li>
          <li>Confirming maximum retail price (MRP), applicable Goods and Services Tax (GST), discounts, and final invoice calculations.</li>
        </ul>
      </section>

      {/* 6. AI Vision & Recognition Limitations */}
      <section className="space-y-3">
        <h2 className="text-lg sm:text-xl font-semibold text-[#202522] flex items-center gap-2">
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-[#EDECE6] text-[#526B5A]">6</span>
          AI Vision Assistance & Recognition Accuracy Limitations
        </h2>
        <p className="text-sm text-[#5E625D]">
          DawaiFlow incorporates camera-based optical character recognition (OCR) and computer vision algorithms to accelerate medicine identification. While engineered for high utility, label recognition accuracy depends on optical variables beyond our control, including camera focus, ambient lighting, packaging glare, folds, regional printing variations, and blister reflections.
        </p>
        <p className="text-sm text-[#5E625D]">
          <em>DawaiFlow does not warrant 100% optical accuracy.</em> The software is designed to present candidate matches for pharmacist confirmation on-screen. Dispensing without pharmacist verification is strictly prohibited.
        </p>
      </section>

      {/* 7. Acceptable & Prohibited Use */}
      <section className="space-y-3">
        <h2 className="text-lg sm:text-xl font-semibold text-[#202522] flex items-center gap-2">
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-[#EDECE6] text-[#526B5A]">7</span>
          Acceptable & Prohibited Use
        </h2>
        <p>You agree to use DawaiFlow strictly for lawful retail pharmacy operations. You agree NOT to:</p>
        <ul className="list-disc pl-5 space-y-1 text-sm text-[#5E625D]">
          <li>Use the software in connection with the illicit distribution or unauthorized sale of prescription-only or habit-forming medicines.</li>
          <li>Upload falsified, manipulated, or counterfeit invoice, batch, or supplier data.</li>
          <li>Attempt to reverse engineer, decompile, disassemble, or extract source code or proprietary image-matching models of DawaiFlow.</li>
          <li>Circumvent, scan, or breach authentication controls or security firewalls of the Service.</li>
          <li>Resell, sublicense, or white-label DawaiFlow without our prior written authorization.</li>
        </ul>
      </section>

      {/* 8. Intellectual Property */}
      <section className="space-y-3">
        <h2 className="text-lg sm:text-xl font-semibold text-[#202522] flex items-center gap-2">
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-[#EDECE6] text-[#526B5A]">8</span>
          Intellectual Property & Ownership
        </h2>
        <p className="text-sm text-[#5E625D]">
          All rights, title, and interest in and to the DawaiFlow software, user interface designs, logos, computer code, vision processing algorithms, and trademarks (&quot;DawaiFlow&quot;, &quot;ExpiryGuard&quot;) belong exclusively to {APP_CONFIG.founderAndOfficer} and contributing engineers.
        </p>
        <p className="text-sm text-[#5E625D]">
          You retain full ownership of your pharmacy operational data, store catalog, supplier logs, and customer invoices. You grant us a limited, non-exclusive license to host and process this data solely to provide and maintain the Service for your store.
        </p>
      </section>

      {/* 9. Disclaimer of Warranties & Limitation of Liability */}
      <section className="space-y-3">
        <h2 className="text-lg sm:text-xl font-semibold text-[#202522] flex items-center gap-2">
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-[#EDECE6] text-[#526B5A]">9</span>
          Disclaimer of Warranties & Limitation of Liability
        </h2>
        <p className="text-sm text-[#5E625D]">
          THE SERVICE IS PROVIDED &quot;AS IS&quot; AND &quot;AS AVAILABLE&quot;, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT.
        </p>
        <p className="text-sm text-[#5E625D]">
          TO THE FULLEST EXTENT PERMITTED BY APPLICABLE INDIAN LAW, IN NO EVENT SHALL {APP_CONFIG.founderAndOfficer.toUpperCase()} OR THE DAWAIFLOW OPERATING TEAM BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, INCLUDING BUT NOT LIMITED TO LOSS OF PROFITS, DATA, BUSINESS INTERRUPTIONS, OR INVENTORY EXPIRY LOSSES, ARISING OUT OF OR IN CONNECTION WITH YOUR USE OR INABILITY TO USE THE SERVICE.
        </p>
      </section>

      {/* 10. Governing Law & Jurisdiction */}
      <section className="space-y-3">
        <h2 className="text-lg sm:text-xl font-semibold text-[#202522] flex items-center gap-2">
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-[#EDECE6] text-[#526B5A]">10</span>
          Governing Law & Dispute Resolution
        </h2>
        <p className="text-sm text-[#5E625D]">
          These Terms shall be governed by and construed in accordance with the substantive laws of the Republic of India, without regard to conflict of law principles.
        </p>
        <p className="text-sm text-[#5E625D]">
          Any dispute, claim, or controversy arising out of or relating to these Terms or the use of DawaiFlow shall be subject to the exclusive jurisdiction of the competent courts situated in <strong>Sonipat, Haryana, India</strong>.
        </p>
      </section>

      {/* 11. Contact Details */}
      <section className="space-y-2 p-4 rounded-lg bg-[#FAF9F5] border border-[#DCDDD5] text-xs sm:text-sm text-[#5E625D]">
        <h3 className="font-semibold text-[#202522]">11. Contact Regarding Terms</h3>
        <p>
          If you have questions regarding these Terms or need support, please contact:
        </p>
        <p className="text-[#202522]">
          <strong>Representative:</strong> {APP_CONFIG.founderAndOfficer} • <strong>Location:</strong> {APP_CONFIG.location}<br />
          <strong>Email:</strong> <a href={`mailto:${APP_CONFIG.supportEmail}`} className="text-[#526B5A] underline">{APP_CONFIG.supportEmail}</a> or <a href={`mailto:${APP_CONFIG.grievanceEmail}`} className="text-[#526B5A] underline">{APP_CONFIG.grievanceEmail}</a><br />
          <strong>Phone:</strong> {APP_CONFIG.supportPhone}
        </p>
      </section>
    </article>
  );
};
