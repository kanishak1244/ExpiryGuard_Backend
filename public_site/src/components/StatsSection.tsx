import React from 'react';
import { ScrollReveal } from './ui/ScrollReveal';
import { AnimatedCounter } from './ui/AnimatedCounter';

interface StatItem {
  value: number;
  prefix?: string;
  suffix?: string;
  label: string;
  subtext: string;
}

interface StatsSectionProps {
  onOpenPilot?: () => void;
}

export const StatsSection: React.FC<StatsSectionProps> = () => {
  const stats: StatItem[] = [
    {
      value: 75,
      suffix: '%',
      label: 'Faster Counter Billing',
      subtext: 'Multi-item camera scanning and auto-inventory matching.',
    },
    {
      value: 10,
      prefix: '< ',
      suffix: ' sec',
      label: 'Avg Dispensing Checkout',
      subtext: 'For standard multi-strip customer purchases.',
    },
    {
      value: 100,
      suffix: '%',
      label: 'FIFO / FEFO Compliance',
      subtext: 'Automatic first-expiry batch selection on every bill.',
    },
    {
      value: 0,
      suffix: ' Errors',
      label: 'Precise Loose Tablets',
      subtext: 'Instant fractional per-tablet pricing & stock tracking.',
    },
  ];

  return (
    <section className="py-16 sm:py-20 bg-[#F5F4EF] border-b border-[#DCDDD5] relative overflow-hidden">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 lg:gap-6">
          {stats.map((stat, i) => (
            <ScrollReveal key={stat.label} delay={i * 0.08} yOffset={20}>
              <div className="group p-6 rounded-2xl bg-[#FFFFFF] border border-[#DCDDD5] hover:border-[#526B5A]/50 hover:shadow-xs hover:-translate-y-1 transition-all duration-300 h-full flex flex-col justify-between shadow-2xs">
                <div>
                  <div className="font-display text-5xl sm:text-6xl font-bold text-[#526B5A] tracking-tight mb-2">
                    <AnimatedCounter
                      value={stat.value}
                      prefix={stat.prefix || ''}
                      suffix={stat.suffix || ''}
                      duration={1.8}
                    />
                  </div>
                  <h3 className="font-display text-base sm:text-lg font-semibold text-[#202522] mb-1.5">
                    {stat.label}
                  </h3>
                  <p className="text-xs sm:text-sm text-[#5E625D] leading-relaxed">
                    {stat.subtext}
                  </p>
                </div>
              </div>
            </ScrollReveal>
          ))}
        </div>
      </div>
    </section>
  );
};
