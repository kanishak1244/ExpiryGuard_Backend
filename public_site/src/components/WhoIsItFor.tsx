import React from 'react';
import { Store, Users, Clock } from 'lucide-react';
import { ScrollReveal } from './ui/ScrollReveal';

export const WhoIsItFor: React.FC = () => {
  const categories = [
    {
      idx: '01',
      icon: Store,
      title: 'Independent Pharmacies',
      description: 'Single or multi-counter pharmacies wanting faster daily billing without software friction.',
    },
    {
      idx: '02',
      icon: Users,
      title: 'Growing Chemist Stores',
      description: 'Medical stores where multiple staff members dispense, verify, and stock simultaneously.',
    },
    {
      idx: '03',
      icon: Clock,
      title: 'Busy High-Volume Counters',
      description: 'Pharmacies serving long customer queues that need every second saved during peak hours.',
    },
  ];

  return (
    <section className="py-20 sm:py-28 bg-[#F5F4EF] border-b border-[#DCDDD5]">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <ScrollReveal yOffset={16}>
          <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-[#EDECE6] border border-[#DCDDD5] text-xs font-medium text-[#526B5A] mb-3 shadow-2xs">
            <span className="w-1.5 h-1.5 rounded-full bg-[#526B5A] animate-pulse" />
            <span className="font-mono uppercase tracking-wider">Audience & Fit</span>
          </div>
          <h2 className="font-display text-3xl sm:text-4xl lg:text-5xl font-bold text-[#202522] tracking-tight">
            Made for pharmacies that value their time.
          </h2>
          <p className="mt-3 text-sm sm:text-base text-[#5E625D] max-w-lg mx-auto">
            Whether you run a trusted neighborhood chemist or a high-footfall counter.
          </p>
        </ScrollReveal>

        <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6 text-left">
          {categories.map((cat, i) => {
            const Icon = cat.icon;
            return (
              <ScrollReveal key={cat.title} delay={i * 0.08} yOffset={20}>
                <div
                  className="group relative p-6 sm:p-7 rounded-2xl bg-[#FFFFFF] border border-[#DCDDD5] hover:border-[#526B5A]/50 flex flex-col justify-between shadow-2xs hover:shadow-xs hover:-translate-y-1.5 transition-all duration-300 h-full overflow-hidden"
                >
                  <div className="absolute top-2 right-3 font-mono text-6xl font-bold text-[#202522]/5 group-hover:text-[#526B5A]/10 transition-colors select-none pointer-events-none">
                    {cat.idx}
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-5">
                      <div className="w-10 h-10 rounded-xl bg-[#EDECE6] border border-[#DCDDD5] group-hover:bg-[#EBF7EE] group-hover:border-[#526B5A]/30 flex items-center justify-center text-[#526B5A] transition-colors">
                        <Icon className="w-5 h-5 transition-transform duration-200 group-hover:scale-105" />
                      </div>
                      <span className="font-mono text-xs font-semibold text-[#526B5A] bg-[#EDECE6] px-2.5 py-0.5 rounded border border-[#DCDDD5]">
                        {cat.idx}
                      </span>
                    </div>
                    <h3 className="font-display text-lg sm:text-xl font-bold text-[#202522] mb-2 group-hover:text-[#526B5A] transition-colors">
                      {cat.title}
                    </h3>
                    <p className="text-xs sm:text-sm text-[#5E625D] leading-relaxed">
                      {cat.description}
                    </p>
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
