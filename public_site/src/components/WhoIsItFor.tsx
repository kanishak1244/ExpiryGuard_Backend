import React from 'react';
import { Store, Users, Clock } from 'lucide-react';

export const WhoIsItFor: React.FC = () => {
  const categories = [
    {
      icon: Store,
      title: 'Independent Pharmacies',
      description: 'Single or multi-counter pharmacies wanting faster daily billing without software friction.',
    },
    {
      icon: Users,
      title: 'Growing Chemist Stores',
      description: 'Medical stores where multiple staff members dispense, verify, and stock simultaneously.',
    },
    {
      icon: Clock,
      title: 'Busy High-Volume Counters',
      description: 'Pharmacies serving long customer queues that need every second saved during peak hours.',
    },
  ];

  return (
    <section className="py-16 sm:py-20 bg-[#F5F4EF] border-b border-[#DCDDD5]">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <h2 className="text-2xl sm:text-3xl lg:text-[36px] font-semibold text-[#202522] tracking-tight">
          Made for pharmacies that value their time.
        </h2>
        <p className="mt-2 text-xs sm:text-sm text-[#5E625D] max-w-lg mx-auto">
          Whether you run a trusted neighborhood chemist or a high-footfall counter.
        </p>

        <div className="mt-10 grid grid-cols-1 md:grid-cols-3 gap-4 text-left">
          {categories.map((cat) => {
            const Icon = cat.icon;
            return (
              <div
                key={cat.title}
                className="p-5 sm:p-6 rounded-xl bg-[#FFFFFF] border border-[#DCDDD5] flex flex-col justify-between shadow-2xs"
              >
                <div>
                  <div className="w-9 h-9 rounded-lg bg-[#EDECE6] border border-[#DCDDD5] flex items-center justify-center text-[#526B5A] mb-3.5">
                    <Icon className="w-4 h-4" />
                  </div>
                  <h3 className="text-base font-semibold text-[#202522] mb-1.5">{cat.title}</h3>
                  <p className="text-xs sm:text-sm text-[#5E625D] leading-relaxed">{cat.description}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};
