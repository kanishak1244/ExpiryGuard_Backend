import React from 'react';
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
        <div className="text-center mb-8 sm:mb-11">
          <h3 className="text-xl sm:text-2xl font-semibold text-[#202522]">
            Everything else you need, without the clutter.
          </h3>
          <p className="mt-2 text-xs sm:text-sm text-[#5E625D]">
            Essential counter and backroom capabilities built right into your daily flow.
          </p>
        </div>

        {/* Compact Grid: 1 or 2 columns on mobile, 4 on desktop */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2.5 sm:gap-3">
          {supportingCapabilities.map((item) => {
            const Icon = item.icon;
            return (
              <div
                key={item.name}
                className="p-2.5 sm:p-3 rounded-lg bg-[#FFFFFF] border border-[#DCDDD5] flex items-center gap-2.5 hover:border-[#C4C5BC] transition-colors min-w-0 shadow-2xs"
              >
                <div className="w-7 h-7 rounded-md bg-[#EDECE6] border border-[#DCDDD5] flex items-center justify-center text-[#526B5A] shrink-0">
                  <Icon className="w-3.5 h-3.5" />
                </div>
                <span className="text-xs font-medium text-[#202522] truncate">{item.name}</span>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};
