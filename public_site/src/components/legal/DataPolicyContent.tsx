import React from 'react';
import { APP_CONFIG } from '../../config/appConfig';
import { Key, Package, CreditCard, Camera, UserCheck, Cookie, HardDrive } from 'lucide-react';

export const DataPolicyContent: React.FC = () => {
  const categories = [
    {
      id: 'account',
      icon: Key,
      title: '1. Pharmacist Account & Credentials',
      what: 'Pharmacist username, registered email address, and encrypted account password (hashed using bcrypt).',
      why: 'To verify staff logins, authenticate billing counters, and secure your store portal against unauthorized access.',
      how: 'Verified against database records during login. Used to sign JWT authorization tokens for counter terminal sessions.',
      shared: 'No. Stored strictly within our secure relational database (Supabase PostgreSQL).',
      deletion: `Emailing a deletion request to ${APP_CONFIG.grievanceEmail} completely purges the account credentials within 14 business days.`,
    },
    {
      id: 'inventory',
      icon: Package,
      title: '2. Pharmacy Inventory & Stock Catalog',
      what: 'Medicine brand names, manufacturer details, active batch numbers, expiry dates, pack sizes, shelf locations, and current quantity counts.',
      why: 'To maintain live counter inventory, power First-Expiry-First-Out (FEFO) dispensing, and calculate stock valuation.',
      how: 'Updated in real-time when customer bills are settled, returns are recorded, or new purchase stock is entered.',
      shared: 'No. Inventory catalogs are completely private to each registered pharmacy account.',
      deletion: 'Can be cleared directly from the pharmacist portal dashboard or purged during account closure.',
    },
    {
      id: 'sales',
      icon: CreditCard,
      title: '3. Sales & Invoice Transcripts',
      what: 'Retail invoice numbers, transaction timestamps, items sold, unit prices, MRP, discounts, GST tax percentages, and payment modes (Cash / UPI / Card).',
      why: 'To generate printable counter receipts (PDF invoices) and compile daily sales summaries for the pharmacy owner.',
      how: 'Aggregated inside your private store dashboard to calculate revenue, gross margin, and tax summaries.',
      shared: 'No. Business sales logs are private to your pharmacy.',
      deletion: 'Associated transaction records are purged upon written account termination request.',
    },
    {
      id: 'camera',
      icon: Camera,
      title: '4. Camera Medicine Package Scans',
      what: 'Temporary photographs of medicine packaging labels and blister strips taken using your device camera or uploaded via the billing interface.',
      why: 'To recognize packaging text (brand name, pack size, batch number, expiry date, MRP) without manual typing.',
      how: 'Processed strictly in-memory by optical text extraction models. Images are discarded immediately following analysis.',
      shared: 'Transmitted securely over encrypted TLS connections to our vision inference service. Photos are never stored on disk or used for public AI training.',
      deletion: 'Not applicable, as camera images are never permanently saved.',
    },
    {
      id: 'customer',
      icon: UserCheck,
      title: '5. Customer & Supplier Contact Details',
      what: 'Optional customer name or phone number entered during checkout to print on a retail tax receipt, and supplier contact entries.',
      why: 'To print customer receipts compliant with retail billing conventions and maintain supplier purchase records.',
      how: 'Appended directly to the specific invoice record and stored in the encrypted database.',
      shared: 'No. Customer databases are strictly private and are never sold or shared with advertisers or marketing networks.',
      deletion: 'Can be modified or deleted directly from your portal sales listings.',
    },
  ];

  return (
    <article className="space-y-8 text-[#202522] leading-relaxed text-[15px]">
      {/* Header */}
      <div className="p-4 sm:p-5 rounded-xl bg-[#EDECE6] border border-[#DCDDD5] space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-[#526B5A]">
            Data Architecture & Transparency
          </span>
          <span className="text-xs text-[#5E625D]">
            Last Updated: September 2026
          </span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-[#202522]">
          Data & App Information
        </h1>
        <p className="text-xs sm:text-sm text-[#5E625D]">
          A clear, transparent breakdown of what information DawaiFlow processes, why it is needed, and how it is protected.
        </p>
      </div>

      <p className="text-sm text-[#5E625D]">
        To keep our pharmacy operations completely transparent, this page provides an itemized breakdown of every data category DawaiFlow handles, our strict no-sale policy, and our local client storage implementation.
      </p>

      {/* Data Categories Grid */}
      <div className="space-y-4">
        {categories.map((cat) => {
          const Icon = cat.icon;
          return (
            <div
              key={cat.id}
              className="rounded-xl bg-[#FFFFFF] border border-[#DCDDD5] p-5 space-y-3.5 shadow-2xs"
            >
              <div className="flex items-center gap-2.5 text-[#202522]">
                <div className="w-8 h-8 rounded-lg bg-[#EDECE6] border border-[#DCDDD5] flex items-center justify-center text-[#526B5A]">
                  <Icon className="w-4 h-4" />
                </div>
                <h2 className="text-base font-semibold">{cat.title}</h2>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 pt-1 text-xs sm:text-sm border-t border-[#DCDDD5]/60">
                <div className="font-semibold text-[#202522] sm:col-span-1">What it is:</div>
                <div className="text-[#5E625D] sm:col-span-3">{cat.what}</div>

                <div className="font-semibold text-[#202522] sm:col-span-1 pt-1">Why needed:</div>
                <div className="text-[#5E625D] sm:col-span-3 pt-1">{cat.why}</div>

                <div className="font-semibold text-[#202522] sm:col-span-1 pt-1">How used:</div>
                <div className="text-[#5E625D] sm:col-span-3 pt-1">{cat.how}</div>

                <div className="font-semibold text-[#202522] sm:col-span-1 pt-1">Shared:</div>
                <div className="text-[#5E625D] sm:col-span-3 pt-1">{cat.shared}</div>

                <div className="font-semibold text-[#202522] sm:col-span-1 pt-1">Deletion:</div>
                <div className="text-[#5E625D] sm:col-span-3 pt-1">{cat.deletion}</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Cookies & Browser Storage Transparency */}
      <section className="p-5 rounded-xl bg-[#FAF9F5] border border-[#DCDDD5] space-y-3">
        <div className="flex items-center gap-2 text-[#202522]">
          <Cookie className="w-5 h-5 text-[#526B5A]" />
          <h2 className="text-base sm:text-lg font-semibold">
            Cookies, Analytics & Local Storage Transparency
          </h2>
        </div>
        <p className="text-xs sm:text-sm text-[#5E625D] leading-relaxed">
          We believe in strict digital hygiene. Here is how our public website and application manage client storage:
        </p>
        <ul className="list-disc pl-5 space-y-1.5 text-xs sm:text-sm text-[#5E625D]">
          <li>
            <strong>Zero Advertising Trackers:</strong> This website does NOT deploy marketing cookies, ad pixels (such as Meta Pixel or Google Ads tags), or cross-site tracking technologies.
          </li>
          <li>
            <strong>No Third-Party Analytics Trackers:</strong> We do not sell or transmit your browsing activity to commercial analytics brokers.
          </li>
          <li>
            <strong>Local Browser Storage (LocalStorage):</strong> We use local browser storage strictly for functional client state, such as caching your draft pilot form responses and remembering UI preference toggles. This data resides solely on your physical device.
          </li>
          <li>
            <strong>Essential Session Cookies:</strong> On the authenticated pharmacy portal, secure HTTP-only cookies are utilized exclusively to authenticate user sessions and prevent cross-site request forgery.
          </li>
        </ul>
      </section>

      {/* Infrastructure Verification */}
      <section className="p-4 rounded-lg bg-[#EDECE6] border border-[#DCDDD5] text-xs text-[#5E625D] space-y-1">
        <p><strong>Cloud Database:</strong> {APP_CONFIG.infrastructure.database}</p>
        <p><strong>Transmission Protocol:</strong> {APP_CONFIG.infrastructure.transmission}</p>
        <p><strong>Authentication Security:</strong> {APP_CONFIG.infrastructure.authentication}</p>
        <p><strong>Pilot Fee Status:</strong> Currently Free / No Payment Details Processed Online</p>
      </section>
    </article>
  );
};
