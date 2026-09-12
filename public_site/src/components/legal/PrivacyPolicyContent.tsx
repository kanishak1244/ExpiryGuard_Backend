import React from 'react';
import { APP_CONFIG } from '../../config/appConfig';
import { Shield, Mail, Phone, Lock, FileText, CheckCircle2 } from 'lucide-react';

export const PrivacyPolicyContent: React.FC = () => {
  return (
    <article className="space-y-8 text-[#202522] leading-relaxed text-[15px]">
      {/* Header Banner */}
      <div className="p-4 sm:p-5 rounded-xl bg-[#EDECE6] border border-[#DCDDD5] space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-[#526B5A]">
            Official Compliance Document
          </span>
          <span className="text-xs text-[#5E625D]">
            Last Updated & Effective Date: September 2026
          </span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-[#202522]">
          Privacy Policy
        </h1>
        <p className="text-xs sm:text-sm text-[#5E625D]">
          {APP_CONFIG.brandName} • Operational Location: {APP_CONFIG.location}
        </p>
      </div>

      {/* General Statement & Identity */}
      <section className="space-y-3">
        <h2 className="text-lg sm:text-xl font-semibold text-[#202522] flex items-center gap-2">
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-[#EDECE6] text-[#526B5A]">1</span>
          Who We Are & Scope of this Policy
        </h2>
        <p>
          DawaiFlow (&quot;we&quot;, &quot;us&quot;, &quot;our&quot;) is a specialized pharmacy operations, billing, and inventory management software platform developed for retail pharmacies and licensed chemists in India. DawaiFlow is operated by {APP_CONFIG.founderAndOfficer} under the brand name &quot;{APP_CONFIG.brandName}&quot;.
        </p>
        <div className="p-3.5 rounded-lg bg-[#FAF9F5] border border-[#DCDDD5] text-xs text-[#5E625D] space-y-1">
          <p><strong>Corporate / Legal Identification:</strong> {APP_CONFIG.legalEntityPlaceholder}</p>
          <p><strong>Operating Address:</strong> {APP_CONFIG.registeredOfficePlaceholder}</p>
          <p><strong>Contact / Grievance Redressal:</strong> {APP_CONFIG.grievanceEmail} • {APP_CONFIG.supportPhone}</p>
        </div>
        <p className="text-sm text-[#5E625D]">
          This Privacy Policy explains what personal and business operational data we collect, why we collect it, how it is processed and protected, and your statutory rights under the <strong>Digital Personal Data Protection Act, 2023 (DPDP Act, 2023)</strong> and applicable rules under the Information Technology Act, 2000.
        </p>
      </section>

      {/* Information We Collect */}
      <section className="space-y-4">
        <h2 className="text-lg sm:text-xl font-semibold text-[#202522] flex items-center gap-2">
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-[#EDECE6] text-[#526B5A]">2</span>
          Information We Collect & Why It Is Collected
        </h2>
        <p>
          We only collect data strictly necessary to facilitate your pharmacy counter workflow, account security, and pilot coordination.
        </p>

        <div className="space-y-3">
          <div className="p-4 rounded-lg bg-[#FFFFFF] border border-[#DCDDD5] space-y-2">
            <h3 className="font-semibold text-sm text-[#202522] flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-[#526B5A]" />
              A. Pilot & Contact Form Information (Necessary for Onboarding)
            </h3>
            <p className="text-sm text-[#5E625D]">
              <strong>Data items:</strong> Pharmacy name, contact person name, mobile / WhatsApp number, email address, city / state, pharmacy operating type, and optional notes on your counter billing challenges.
            </p>
            <p className="text-sm text-[#5E625D]">
              <strong>Purpose:</strong> To verify retail eligibility, coordinate your scheduled product walkthrough, communicate pilot updates, and provide operational customer support. Providing this information is necessary if you wish to participate in the DawaiFlow pilot.
            </p>
          </div>

          <div className="p-4 rounded-lg bg-[#FFFFFF] border border-[#DCDDD5] space-y-2">
            <h3 className="font-semibold text-sm text-[#202522] flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-[#526B5A]" />
              B. Pharmacist Account & Authentication Data (Necessary for Portal Access)
            </h3>
            <p className="text-sm text-[#5E625D]">
              <strong>Data items:</strong> Pharmacist username, registered email address, and encrypted account password (stored using one-way bcrypt cryptographic hashing).
            </p>
            <p className="text-sm text-[#5E625D]">
              <strong>Purpose:</strong> To authenticate authorized staff access to your pharmacy account, protect your counter data from unauthorized access, and maintain secure sessions.
            </p>
          </div>

          <div className="p-4 rounded-lg bg-[#FFFFFF] border border-[#DCDDD5] space-y-2">
            <h3 className="font-semibold text-sm text-[#202522] flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-[#526B5A]" />
              C. Pharmacy Business & Operational Data (Necessary for System Functionality)
            </h3>
            <p className="text-sm text-[#5E625D]">
              <strong>Data items:</strong> Medicine names, batch numbers, manufacturer details, pack sizes, MRP, purchase rates, shelf locations, supplier logs, active stock counts, invoice records, payment modes, and GST breakdown summaries. Optionally, your store GSTIN for receipt printing.
            </p>
            <p className="text-sm text-[#5E625D]">
              <strong>Purpose:</strong> To calculate retail counter invoices, automate inventory reduction upon sales, power First-Expiry-First-Out (FEFO) dispensing recommendations, and generate financial reports for your store. This data belongs to your pharmacy.
            </p>
          </div>

          <div className="p-4 rounded-lg bg-[#FFFFFF] border border-[#DCDDD5] space-y-2">
            <h3 className="font-semibold text-sm text-[#202522] flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-[#526B5A]" />
              D. Temporary Camera Label Captures (In-Memory Processing Only)
            </h3>
            <p className="text-sm text-[#5E625D]">
              <strong>Data items:</strong> Photos of medicine packaging strips or outer cartons taken using your device camera or uploaded via the billing interface.
            </p>
            <p className="text-sm text-[#5E625D]">
              <strong>Purpose & Handling:</strong> Transmitted through secure TLS encryption to our optical character recognition (OCR) vision service to extract brand name, strength, batch, and expiry dates for fast billing. <em>These images are processed strictly in-memory and are discarded immediately after text extraction.</em> Images are not retained on our permanent servers and are never used for public AI training datasets.
            </p>
          </div>

          <div className="p-4 rounded-lg bg-[#FFFFFF] border border-[#DCDDD5] space-y-2">
            <h3 className="font-semibold text-sm text-[#202522] flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-[#526B5A]" />
              E. Counter Customer Information (Optional on Invoices)
            </h3>
            <p className="text-sm text-[#5E625D]">
              <strong>Data items:</strong> Customer name or contact number voluntarily keyed in by the pharmacist solely to print on a retail tax invoice.
            </p>
            <p className="text-sm text-[#5E625D]">
              <strong>Health Data Notice:</strong> DawaiFlow does not collect, solicit, or maintain patient medical records, clinical case sheets, or diagnostic histories. Entering customer details on counter receipts is completely optional and controlled entirely by the dispensing pharmacist.
            </p>
          </div>

          <div className="p-4 rounded-lg bg-[#FFFFFF] border border-[#DCDDD5] space-y-2">
            <h3 className="font-semibold text-sm text-[#202522] flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-[#526B5A]" />
              F. Technical & Log Information (Necessary for System Integrity)
            </h3>
            <p className="text-sm text-[#5E625D]">
              <strong>Data items:</strong> IP addresses, browser user agent, device operating system, and session tokens.
            </p>
            <p className="text-sm text-[#5E625D]">
              <strong>Purpose:</strong> To protect the system against automated abuse, verify session validity, and diagnose network errors.
            </p>
          </div>
        </div>
      </section>

      {/* Third-Party Service Providers */}
      <section className="space-y-3">
        <h2 className="text-lg sm:text-xl font-semibold text-[#202522] flex items-center gap-2">
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-[#EDECE6] text-[#526B5A]">3</span>
          Third-Party Data Processors & Infrastructure
        </h2>
        <p>
          We do not sell, rent, trade, or monetize your personal or pharmacy data with third-party advertisers or data brokers. We engage only reputable infrastructure providers strictly necessary to deliver the software:
        </p>
        <ul className="list-disc pl-5 space-y-1.5 text-sm text-[#5E625D]">
          <li>
            <strong>Supabase Inc. (Database Hosting):</strong> Secure PostgreSQL cloud database hosting with data encryption at rest and in transit.
          </li>
          <li>
            <strong>Google Firebase Cloud Messaging (FCM):</strong> Delivers real-time browser and device notifications regarding stock depletion and expiry warnings.
          </li>
          <li>
            <strong>DawaiFlow Vision Processing:</strong> Secure image inference endpoints for optical text extraction from medicine packaging labels.
          </li>
        </ul>
        <p className="text-xs text-[#5E625D] italic">
          Note: DawaiFlow currently does not integrate any third-party payment gateways on this public website because all pilot access is provided free of charge. No payment credentials or credit/debit card numbers are ever collected or processed on this website.
        </p>
      </section>

      {/* Security Measures */}
      <section className="space-y-3">
        <h2 className="text-lg sm:text-xl font-semibold text-[#202522] flex items-center gap-2">
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-[#EDECE6] text-[#526B5A]">4</span>
          Technical Security & Protection Standards
        </h2>
        <p>
          We implement industry-standard technical safeguards designed to protect your data:
        </p>
        <ul className="list-disc pl-5 space-y-1 text-sm text-[#5E625D]">
          <li><strong>Encryption in Transit:</strong> All web traffic and API communications are transmitted using modern Transport Layer Security (HTTPS / TLS 1.3).</li>
          <li><strong>Password Hashing:</strong> Passwords are protected using robust one-way bcrypt hashing algorithms and are never stored in plaintext.</li>
          <li><strong>Role-Based Multi-Tenant Isolation:</strong> Logical isolation prevents any pharmacy from accessing another pharmacy&apos;s inventory, customer lists, or sales logs.</li>
        </ul>
        <p className="text-xs text-[#5E625D]">
          <em>Honest Security Notice:</em> While we implement diligent administrative and technical measures, no internet transmission or electronic storage architecture can guarantee absolute immunity from unforeseen hardware faults or sophisticated attacks. We commit to prompt investigation and transparency in the event of any security incident.
        </p>
      </section>

      {/* Retention & Deletion */}
      <section className="space-y-3">
        <h2 className="text-lg sm:text-xl font-semibold text-[#202522] flex items-center gap-2">
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-[#EDECE6] text-[#526B5A]">5</span>
          Data Retention & Erasure Policy
        </h2>
        <p>
          Your account data and pharmacy operational records are maintained for the duration of your active pilot account. You maintain full ownership over your pharmacy records.
        </p>
        <p className="text-sm text-[#5E625D]">
          You may request the permanent deletion of your account and all associated inventory and billing records at any time by emailing our Grievance Officer at <a href={`mailto:${APP_CONFIG.grievanceEmail}`} className="text-[#526B5A] font-medium underline">{APP_CONFIG.grievanceEmail}</a>. Deletion requests are processed and verified within <strong>14 business days</strong>, subject only to any statutory recordkeeping obligations applicable under Indian law (such as tax audit laws).
        </p>
      </section>

      {/* DPDP Act 2023 Rights */}
      <section className="space-y-3">
        <h2 className="text-lg sm:text-xl font-semibold text-[#202522] flex items-center gap-2">
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-[#EDECE6] text-[#526B5A]">6</span>
          Your Rights Under the Digital Personal Data Protection Act, 2023
        </h2>
        <p>
          As a Data Principal under Indian law, you are entitled to the following statutory rights regarding your personal data:
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
          <div className="p-3 rounded-lg bg-[#FAF9F5] border border-[#DCDDD5]">
            <h4 className="font-semibold text-[#202522]">Right to Access Information</h4>
            <p className="text-xs text-[#5E625D] mt-1">Obtain a clear summary of your personal data being processed and the identities of data processors.</p>
          </div>
          <div className="p-3 rounded-lg bg-[#FAF9F5] border border-[#DCDDD5]">
            <h4 className="font-semibold text-[#202522]">Right to Correction & Updating</h4>
            <p className="text-xs text-[#5E625D] mt-1">Request the correction of inaccurate or incomplete personal information associated with your account.</p>
          </div>
          <div className="p-3 rounded-lg bg-[#FAF9F5] border border-[#DCDDD5]">
            <h4 className="font-semibold text-[#202522]">Right to Withdraw Consent</h4>
            <p className="text-xs text-[#5E625D] mt-1">Withdraw consent given for processing personal data at any time, subject to lawful processing limits.</p>
          </div>
          <div className="p-3 rounded-lg bg-[#FAF9F5] border border-[#DCDDD5]">
            <h4 className="font-semibold text-[#202522]">Right to Grievance Redressal</h4>
            <p className="text-xs text-[#5E625D] mt-1">Access an accessible mechanism to resolve data privacy concerns within statutory timeframes.</p>
          </div>
        </div>
        <p className="text-xs text-[#5E625D] italic">
          Statutory Disclosure: DawaiFlow adheres to the obligations of a Data Fiduciary under the DPDP Act, 2023. We make no false or misleading claims of being &quot;DPDP Certified&quot; or &quot;Government Approved&quot;, as Indian law prescribes legal accountability and compliance rather than commercial marketing accreditations.
        </p>
      </section>

      {/* Grievance Redressal */}
      <section className="space-y-3 p-5 rounded-xl bg-[#FAF9F5] border border-[#DCDDD5]">
        <h2 className="text-base sm:text-lg font-semibold text-[#202522] flex items-center gap-2">
          <Shield className="w-5 h-5 text-[#526B5A]" />
          7. Grievance Officer & Contact Information
        </h2>
        <p className="text-sm text-[#5E625D]">
          For questions, privacy concerns, data access requests, or statutory grievances under the DPDP Act, 2023, please contact our designated Grievance Officer:
        </p>
        <div className="space-y-1.5 text-sm text-[#202522]">
          <p><strong>Name / Officer:</strong> {APP_CONFIG.founderAndOfficer}</p>
          <p><strong>Designation:</strong> Data Grievance Officer, DawaiFlow</p>
          <p><strong>Operational Location:</strong> {APP_CONFIG.location}</p>
          <p>
            <strong>Official Email:</strong>{' '}
            <a href={`mailto:${APP_CONFIG.grievanceEmail}`} className="text-[#526B5A] underline">
              {APP_CONFIG.grievanceEmail}
            </a>
          </p>
          <p>
            <strong>Direct Phone / WhatsApp:</strong>{' '}
            <a href={`tel:${APP_CONFIG.supportPhone}`} className="text-[#526B5A] underline">
              {APP_CONFIG.supportPhone}
            </a>
          </p>
        </div>
        <p className="text-xs text-[#5E625D] pt-2">
          All formal grievances received in writing will be acknowledged within 48 business hours and resolved within the statutory period of 30 calendar days.
        </p>
      </section>
    </article>
  );
};
