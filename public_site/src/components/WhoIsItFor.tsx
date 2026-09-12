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
    <section className="py-16 sm:py-20 bg-[#F5F4EF] border-b border-[#DCDDD5]">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <ScrollReveal yOffset={16}>
          <h2 className="text-2xl sm:text-3xl lg:text-[36px] font-semibold text-[#202522] tracking-tight">
            Made for pharmacies that value their time.
          </h2>
          <p className="mt-2 text-xs sm:text-sm text-[#5E625D] max-w-lg mx-auto">
            Whether you run a trusted neighborhood chemist or a high-footfall counter.
          </p>
        </ScrollReveal>

        <div className="mt-10 grid grid-cols-1 md:grid-cols-3 gap-4 text-left">
          {categories.map((cat, i) => {
            const Icon = cat.icon;
            return (
              <ScrollReveal key={cat.title} delay={i * 0.08} yOffset={20}>
                <div
                  className="group relative p-5 sm:p-6 rounded-xl bg-[#FFFFFF] border border-[#DCDDD5] hover:border-[#526B5A]/40 flex flex-col justify-between shadow-2xs hover:shadow-xs hover:-translate-y-1 transition-all duration-300 h-full"
                >
                  <div>
                    <div className="flex items-center justify-between mb-4">
                      <div className="w-9 h-9 rounded-lg bg-[#EDECE6] border border-[#DCDDD5] group-hover:bg-[#EBF7EE] group-hover:border-[#526B5A]/30 flex items-center justify-center text-[#526B5A] transition-colors">
                        <Icon className="w-4 h-4 transition-transform duration-200 group-hover:scale-105" />
                      </div>
                      <span className="font-mono text-xs text-[#8A8F88] font-medium tracking-wider">
                        {cat.idx}
                      </span>
                    </div>
                    <h3 className="text-base font-semibold text-[#202522] mb-1.5 group-hover:text-[#526B5A] transition-colors">
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
