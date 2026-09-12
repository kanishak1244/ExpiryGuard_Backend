import React from 'react';
import { ScrollReveal } from './ui/ScrollReveal';
import {
  ScanBarcode,
  Pill,
  CalendarDays,
  PauseCircle,
  Split,
  QrCode,
  FileCheck,
  Printer,
  Truck,
  RotateCcw,
  Undo2,
  Hourglass,
  AlertCircle,
  BookOpen,
  FileSpreadsheet,
  Users,
  ShieldCheck,
} from 'lucide-react';

export const SecondaryFeatures: React.FC = () => {
  const supportingCapabilities = [
    { name: 'Barcode billing', icon: ScanBarcode },
    { name: 'Loose tablet dispensing', icon: Pill },
    { name: 'FEFO batch selection', icon: CalendarDays },
    { name: 'Hold & resume bills', icon: PauseCircle },
    { name: 'Split payments', icon: Split },
    { name: 'UPI QR payments', icon: QrCode },
    { name: 'GST invoices', icon: FileCheck },
    { name: 'Thermal printing', icon: Printer },
    { name: 'Purchase management', icon: Truck },
    { name: 'Purchase returns', icon: RotateCcw },
    { name: 'Sales returns', icon: Undo2 },
    { name: 'Smart expiry tracking', icon: Hourglass },
    { name: 'Low-stock alerts', icon: AlertCircle },
    { name: 'Customer Khata', icon: BookOpen },
    { name: 'CA Connect', icon: FileSpreadsheet },
    { name: 'Staff roles & permissions', icon: Users },
    { name: 'Encrypted backup & restore', icon: ShieldCheck },
  ];

  return (
    <section id="features" className="py-16 sm:py-20 bg-[#F5F4EF] border-b border-[#DCDDD5]">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <ScrollReveal yOffset={16} className="text-center mb-8 sm:mb-11">
          <h3 className="text-xl sm:text-2xl font-semibold text-[#202522]">
            Everything else you need, without the clutter.
          </h3>
          <p className="mt-2 text-xs sm:text-sm text-[#5E625D]">
            Essential counter and backroom capabilities built right into your daily flow.
          </p>
        </ScrollReveal>

        {/* Compact Grid: 1 or 2 columns on mobile, 4 on desktop */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2.5 sm:gap-3">
          {supportingCapabilities.map((item, idx) => {
            const Icon = item.icon;
            return (
              <ScrollReveal key={item.name} delay={Math.min(idx * 0.025, 0.35)} yOffset={12}>
                <div
                  className="group p-2.5 sm:p-3 rounded-lg bg-[#FFFFFF] border border-[#DCDDD5] flex items-center gap-2.5 hover:border-[#526B5A]/40 hover:-translate-y-0.5 hover:shadow-xs transition-all duration-200 min-w-0 shadow-2xs cursor-default"
                >
                  <div className="w-7 h-7 rounded-md bg-[#EDECE6] border border-[#DCDDD5] group-hover:bg-[#EBF7EE] group-hover:border-[#526B5A]/30 flex items-center justify-center text-[#526B5A] shrink-0 transition-colors">
                    <Icon className="w-3.5 h-3.5 transition-transform duration-200 group-hover:scale-110" />
                  </div>
                  <span className="text-xs font-medium text-[#202522] group-hover:text-[#202522] truncate transition-colors">
                    {item.name}
                  </span>
                </div>
              </ScrollReveal>
            );
          })}
        </div>
      </div>
    </section>
  );
};
