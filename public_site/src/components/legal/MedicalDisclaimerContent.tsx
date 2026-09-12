import React from 'react';
import { APP_CONFIG } from '../../config/appConfig';
import { AlertCircle, CheckCircle2, Stethoscope, ShieldCheck, FileCheck } from 'lucide-react';

export const MedicalDisclaimerContent: React.FC = () => {
  return (
    <article className="space-y-8 text-[#202522] leading-relaxed text-[15px]">
      {/* Header */}
      <div className="p-4 sm:p-5 rounded-xl bg-[#EDECE6] border border-[#DCDDD5] space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-[#526B5A]">
            Professional & Regulatory Disclosure
          </span>
          <span className="text-xs text-[#5E625D]">
            Effective: September 2026
          </span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-[#202522]">
          Pharmacy & Medical Disclaimer
        </h1>
        <p className="text-xs sm:text-sm text-[#5E625D]">
          Important information regarding the scope of DawaiFlow software and pharmacist dispensing responsibilities.
        </p>
      </div>

      {/* Primary Scope Notice */}
      <section className="p-5 rounded-xl bg-[#FAF9F5] border border-[#DCDDD5] space-y-3">
        <div className="flex items-center gap-2 text-[#202522]">
          <Stethoscope className="w-5 h-5 text-[#526B5A]" />
          <h2 className="text-base sm:text-lg font-semibold">
            DawaiFlow is Pharmacy Management & Billing Software
          </h2>
        </div>
        <p className="text-sm text-[#5E625D] leading-relaxed">
          DawaiFlow is an operational productivity and inventory management software platform built to help licensed retail pharmacies streamline fast counter billing, stock batch tracking, FEFO dispensing, and store calculations.
        </p>
        <div className="p-3.5 rounded-lg bg-[#FFFFFF] border border-[#DCDDD5] text-xs sm:text-sm space-y-1.5 text-[#202522]">
          <p className="font-semibold">DawaiFlow is explicitly NOT:</p>
          <ul className="list-disc pl-5 space-y-1 text-[#5E625D]">
            <li>A licensed physician, doctor, or medical clinical practitioner.</li>
            <li>A medical diagnosis, clinical decision support, or triage system.</li>
            <li>A substitute for professional medical advice, consultation, or clinical care.</li>
            <li>A medicine prescribing or treatment recommendation engine.</li>
            <li>A substitute for the professional statutory judgment and duties of a registered pharmacist.</li>
          </ul>
        </div>
      </section>

      {/* AI Vision Role */}
      <section className="space-y-3">
        <h2 className="text-lg sm:text-xl font-semibold text-[#202522] flex items-center gap-2">
          <FileCheck className="w-5 h-5 text-[#526B5A]" />
          Role of AI-Assisted Medicine Vision
        </h2>
        <p className="text-sm text-[#5E625D]">
          DawaiFlow incorporates camera-based optical character recognition (OCR) to assist pharmacists by automatically reading printed text from packaging labels (brand name, strength, batch number, MRP, and expiry dates) to eliminate tedious manual typing at the billing counter.
        </p>
        <p className="text-sm text-[#5E625D]">
          This feature functions strictly as an <strong>administrative transcription assistant</strong>. It does not certify the pharmacological appropriateness, bioequivalence, or therapeutic safety of any medicine for any individual customer or patient.
        </p>
      </section>

      {/* Mandatory Pharmacist Verification */}
      <section className="space-y-3">
        <h2 className="text-lg sm:text-xl font-semibold text-[#202522] flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-[#526B5A]" />
          Pharmacist Responsibility & Mandatory Checks
        </h2>
        <p className="text-sm text-[#5E625D]">
          Under the <strong>Drugs and Cosmetics Act, 1940</strong>, the <strong>Drugs and Cosmetics Rules, 1945</strong>, and the <strong>Pharmacy Practice Regulations</strong>, the registered pharmacist on duty at the licensed counter remains solely responsible for verifying:
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
          <div className="p-3 rounded-lg bg-[#FFFFFF] border border-[#DCDDD5] space-y-1">
            <h4 className="font-semibold text-[#202522] flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-[#526B5A]" />
              Medicine Identity & Strength
            </h4>
            <p className="text-xs text-[#5E625D]">Checking the chemical formulation, brand identity, and correct dosage strength against the customer order.</p>
          </div>
          <div className="p-3 rounded-lg bg-[#FFFFFF] border border-[#DCDDD5] space-y-1">
            <h4 className="font-semibold text-[#202522] flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-[#526B5A]" />
              Batch & Expiration Verification
            </h4>
            <p className="text-xs text-[#5E625D]">Ensuring the physical blister or bottle corresponds to an unexpired batch prior to handing it to the customer.</p>
          </div>
          <div className="p-3 rounded-lg bg-[#FFFFFF] border border-[#DCDDD5] space-y-1">
            <h4 className="font-semibold text-[#202522] flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-[#526B5A]" />
              Valid Doctor Prescriptions
            </h4>
            <p className="text-xs text-[#5E625D]">Ensuring Schedule H, H1, X, and other controlled medicines are dispensed only against an authentic medical prescription.</p>
          </div>
          <div className="p-3 rounded-lg bg-[#FFFFFF] border border-[#DCDDD5] space-y-1">
            <h4 className="font-semibold text-[#202522] flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-[#526B5A]" />
              Final Invoice & Pricing
            </h4>
            <p className="text-xs text-[#5E625D]">Confirming maximum retail prices (MRP), applicable GST slab rates, and final printed invoice numbers.</p>
          </div>
        </div>
      </section>

      {/* Non-E-Commerce Reaffirmation */}
      <section className="p-4 rounded-xl bg-[#EDECE6] border border-[#DCDDD5] text-xs sm:text-sm text-[#5E625D] space-y-1.5">
        <h3 className="font-semibold text-[#202522]">No Consumer Medicine Sales or Online Deliveries</h3>
        <p>
          DawaiFlow does not provide e-commerce delivery of medicines to the general public. Any medication dispensed using DawaiFlow invoices is dispensed directly over the physical counter of the independent licensed retail pharmacy.
        </p>
      </section>
    </article>
  );
};
