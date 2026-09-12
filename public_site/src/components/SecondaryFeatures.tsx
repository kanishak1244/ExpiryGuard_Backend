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
  Zap,
  Boxes,
  ClipboardList,
  Lock,
} from 'lucide-react';

interface FeatureGroup {
  num: string;
  category: string;
  icon: React.ElementType;
  tagline: string;
  description: string;
  items: { name: string; icon: React.ElementType }[];
}

export const SecondaryFeatures: React.FC = () => {
  const groups: FeatureGroup[] = [
    {
      num: '01',
      category: 'Counter Speed & Billing',
      icon: Zap,
      tagline: 'High-Velocity Dispensing',
      description: 'Built for peak rush hours. Clear waiting customer lines in seconds with frictionless point-of-sale tools.',
      items: [
        { name: 'Barcode billing', icon: ScanBarcode },
        { name: 'Hold & resume bills', icon: PauseCircle },
        { name: 'Split payments', icon: Split },
        { name: 'UPI QR payments', icon: QrCode },
        { name: 'Thermal 80mm printing', icon: Printer },
      ],
    },
    {
      num: '02',
      category: 'FEFO & Smart Inventory',
      icon: Boxes,
      tagline: 'Zero Expiry Waste',
      description: 'Intelligent batch lifecycle management that automatically dispenses earliest-expiring stock first.',
      items: [
        { name: 'Loose tablet dispensing', icon: Pill },
        { name: 'FEFO batch selection', icon: CalendarDays },
        { name: 'Smart expiry tracking', icon: Hourglass },
        { name: 'Low-stock reorder alerts', icon: AlertCircle },
      ],
    },
    {
      num: '03',
      category: 'Purchases & Suppliers',
      icon: ClipboardList,
      tagline: 'Backroom Accuracy',
      description: 'Seamless supplier invoice recording, credit tracking, and fast batch return workflows.',
      items: [
        { name: 'Purchase management', icon: Truck },
        { name: 'Purchase returns', icon: RotateCcw },
        { name: 'Customer sales returns', icon: Undo2 },
      ],
    },
    {
      num: '04',
      category: 'Compliance, Khata & Security',
      icon: Lock,
      tagline: 'Bulletproof Operations',
      description: 'GST-ready invoicing, trusted customer credit books, and role-based staff permissions.',
      items: [
        { name: 'GST B2B & B2C invoices', icon: FileCheck },
        { name: 'Customer credit Khata', icon: BookOpen },
        { name: 'CA Connect export', icon: FileSpreadsheet },
        { name: 'Staff roles & permissions', icon: Users },
        { name: 'Encrypted backup & restore', icon: ShieldCheck },
      ],
    },
  ];

  return (
    <section id="features" className="py-20 sm:py-28 bg-[#F5F4EF] border-b border-[#DCDDD5] relative overflow-hidden">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <ScrollReveal yOffset={16} className="text-center max-w-2xl mx-auto mb-14 sm:mb-20">
          <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-[#EDECE6] border border-[#DCDDD5] text-xs font-medium text-[#526B5A] mb-3 shadow-2xs">
            <span className="w-1.5 h-1.5 rounded-full bg-[#526B5A] animate-pulse" />
            <span className="font-mono uppercase tracking-wider">Comprehensive Architecture</span>
          </div>
          <h2 className="font-display text-3xl sm:text-4xl lg:text-5xl font-bold text-[#202522] tracking-tight">
            Everything your counter needs.
          </h2>
          <p className="mt-3 text-sm sm:text-base text-[#5E625D] leading-relaxed">
            Essential point-of-sale, batch inventory, and backroom capabilities engineered into one unified system.
          </p>
        </ScrollReveal>

        {/* 4-Card Bento Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {groups.map((grp, idx) => {
            const GroupIcon = grp.icon;
            return (
              <ScrollReveal key={grp.category} delay={idx * 0.08} yOffset={20}>
                <div className="group relative p-7 sm:p-8 rounded-2xl bg-[#FFFFFF] border border-[#DCDDD5] hover:border-[#526B5A]/50 hover:shadow-xs transition-all duration-300 h-full flex flex-col justify-between overflow-hidden shadow-2xs">
                  {/* Watermark Numeral */}
                  <div className="absolute top-2 right-4 font-mono text-7xl font-bold text-[#202522]/5 group-hover:text-[#526B5A]/10 transition-colors select-none pointer-events-none">
                    {grp.num}
                  </div>

                  <div>
                    <div className="flex items-center gap-3 mb-4">
                      <div className="w-10 h-10 rounded-xl bg-[#EDECE6] border border-[#DCDDD5] flex items-center justify-center text-[#526B5A] group-hover:bg-[#EBF7EE] group-hover:border-[#526B5A]/30 transition-colors">
                        <GroupIcon className="w-5 h-5" />
                      </div>
                      <div>
                        <span className="font-mono text-[11px] uppercase tracking-wider text-[#526B5A] font-semibold">
                          {grp.tagline}
                        </span>
                        <h3 className="font-display text-xl sm:text-2xl font-bold text-[#202522]">
                          {grp.category}
                        </h3>
                      </div>
                    </div>

                    <p className="text-xs sm:text-sm text-[#5E625D] leading-relaxed mb-6">
                      {grp.description}
                    </p>
                  </div>

                  {/* Feature Pill Tags */}
                  <div className="pt-4 border-t border-[#DCDDD5]/60 flex flex-wrap gap-2">
                    {grp.items.map((item) => {
                      const Icon = item.icon;
                      return (
                        <div
                          key={item.name}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#FAF9F5] border border-[#DCDDD5] text-xs font-medium text-[#202522] hover:border-[#526B5A]/40 transition-colors"
                        >
                          <Icon className="w-3.5 h-3.5 text-[#526B5A]" />
                          <span>{item.name}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </ScrollReveal>
            );
          })}
        </div>
      </div>
    </section>
  );
};
