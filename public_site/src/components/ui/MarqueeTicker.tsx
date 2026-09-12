import React from 'react';

interface MarqueeTickerProps {
  items: string[];
  direction?: 'forward' | 'reverse';
}

export const MarqueeTicker: React.FC<MarqueeTickerProps> = ({
  items,
  direction = 'forward',
}) => {
  const animClass = direction === 'reverse' ? 'animate-marquee-reverse' : 'animate-marquee';


  return (
    <div className="relative w-full overflow-hidden py-3.5 bg-[#EDECE6]/60 border-y border-[#DCDDD5]/80 select-none">
      <div className="absolute top-0 bottom-0 left-0 w-16 sm:w-28 bg-gradient-to-r from-[#F5F4EF] to-transparent z-10 pointer-events-none" />
      <div className="absolute top-0 bottom-0 right-0 w-16 sm:w-28 bg-gradient-to-l from-[#F5F4EF] to-transparent z-10 pointer-events-none" />

      <div className={animClass}>
        {[...items, ...items, ...items, ...items].map((item, idx) => (
          <div key={`${item}-${idx}`} className="flex items-center mx-6 sm:mx-9 shrink-0">
            <span className="text-xs sm:text-sm font-mono tracking-widest text-[#5E625D] uppercase font-medium">
              {item}
            </span>
            <span className="ml-6 sm:ml-9 text-[#526B5E] text-xs font-mono opacity-70">+</span>
          </div>
        ))}
      </div>
    </div>
  );
};
