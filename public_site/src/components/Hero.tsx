import React, { useState, useEffect, useRef } from 'react';
import { ArrowRight, Upload, Camera } from 'lucide-react';

interface HeroProps {
  onOpenPilot: () => void;
}

const CANDIDATE_IMAGE_SOURCES = [
  '/assets/hero-pharmacy.jpg',
  '/assets/WhatsApp Image 2026-09-12 at 5.53.19 PM.jpeg',
  '/assets/WhatsApp%20Image%202026-09-12%20at%205.53.19%20PM.jpeg',
  '/assets/pharmacy-hero.jpg',
  '/assets/pharmacy.jpeg',
  '/assets/pharmacy.jpg',
];

const LOCAL_STORAGE_KEY = 'dawaiflow_custom_hero_photo';

export const Hero: React.FC<HeroProps> = ({ onOpenPilot }) => {
  const [sourceIndex, setSourceIndex] = useState(0);
  const [customPhoto, setCustomPhoto] = useState<string | null>(null);
  const [isAllFailed, setIsAllFailed] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(LOCAL_STORAGE_KEY);
      if (saved) {
        setCustomPhoto(saved);
      }
    } catch {
      // Ignore localStorage errors
    }
  }, []);

  const handleImageError = () => {
    if (sourceIndex < CANDIDATE_IMAGE_SOURCES.length - 1) {
      setSourceIndex((prev) => prev + 1);
    } else {
      setIsAllFailed(true);
    }
  };

  const handleFileSelect = (file: File) => {
    if (!file.type.startsWith('image/')) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      const result = e.target?.result as string;
      if (result) {
        setCustomPhoto(result);
        try {
          localStorage.setItem(LOCAL_STORAGE_KEY, result);
        } catch {
          // localStorage might be full for very large images
        }
      }
    };
    reader.readAsDataURL(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const currentSrc = customPhoto || CANDIDATE_IMAGE_SOURCES[sourceIndex];

  return (
    <section id="product" className="pt-8 pb-12 sm:pt-12 sm:pb-16 lg:pt-14 lg:pb-20 bg-[#F5F4EF] overflow-hidden">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-10 xl:gap-12 items-stretch">
          {/* LEFT SIDE: DawaiFlow Hero Content (Full width on mobile, left column on desktop) */}
          <div className="w-full lg:col-span-7 xl:col-span-6 flex flex-col justify-center items-start text-left py-2 lg:py-4">
            {/* Existing badge */}
            <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-[#EDECE6] border border-[#DCDDD5] text-xs text-[#5E625D] mb-5 sm:mb-6">
              <span className="w-1.5 h-1.5 rounded-full bg-[#526B5A]" />
              <span>Accepting select pharmacies for pilot onboarding</span>
            </div>

            {/* Existing headline: Unchanged */}
            <h1 className="text-[32px] sm:text-[42px] lg:text-[44px] xl:text-[50px] font-semibold text-[#202522] tracking-tight leading-[1.18] sm:leading-[1.15]">
              More time for your pharmacy.{' '}
              <span className="text-[#526B5A] block mt-1">Less time managing software.</span>
            </h1>

            {/* Existing supporting paragraph: Unchanged */}
            <p className="mt-4 sm:mt-5 text-[15px] sm:text-[17px] text-[#5E625D] leading-relaxed max-w-xl">
              DawaiFlow reduces repetitive pharmacy work with faster billing, intelligent scanning, and simpler inventory management.
            </p>

            {/* Existing CTA Buttons */}
            <div className="mt-7 sm:mt-8 flex flex-col sm:flex-row items-stretch sm:items-center gap-3 w-full sm:w-auto">
              <button
                id="hero-get-started-btn"
                type="button"
                onClick={onOpenPilot}
                className="w-full sm:w-auto px-6 py-3.5 bg-[#526B5A] hover:bg-[#43584a] text-white rounded-lg text-[15px] font-medium transition-colors flex items-center justify-center gap-2 cursor-pointer shadow-xs active:scale-[0.99]"
              >
                <span>Get Started</span>
                <ArrowRight className="w-4 h-4" />
              </button>

              <button
                id="hero-request-pilot-btn"
                type="button"
                onClick={onOpenPilot}
                className="w-full sm:w-auto px-6 py-3.5 bg-transparent hover:bg-[#EDECE6] text-[#202522] border border-[#DCDDD5] rounded-lg text-[15px] font-medium transition-colors flex items-center justify-center cursor-pointer"
              >
                <span>Request a Pilot</span>
              </button>
            </div>
          </div>

          {/* RIGHT SIDE: LARGE Pharmacy Photograph (HIDDEN ON MOBILE, visible on desktop lg+) */}
          <div className="hidden lg:flex lg:col-span-5 xl:col-span-6 w-full items-stretch">
            <div
              className="relative w-full h-full min-h-[480px] xl:min-h-[520px] rounded-2xl overflow-hidden bg-[#EDECE6] flex items-stretch"
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
            >
              {/* Hidden file input for seamless photo attachment */}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  if (e.target.files && e.target.files[0]) {
                    handleFileSelect(e.target.files[0]);
                  }
                }}
              />

              {!isAllFailed || customPhoto ? (
                <div className="relative w-full h-full group flex items-stretch">
                  <img
                    src={currentSrc}
                    onError={handleImageError}
                    alt="Pharmacist assisting customers at a modern pharmacy counter"
                    className="w-full h-full min-h-[480px] xl:min-h-[520px] object-cover object-[center_32%] block rounded-2xl"
                    loading="eager"
                    decoding="async"
                  />
                  {/* Subtle hover option to update or replace photo */}
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    title="Change attached photograph"
                    className="absolute bottom-3 right-3 px-3 py-1.5 rounded-md bg-black/60 hover:bg-black/80 text-white text-xs font-medium opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1.5 backdrop-blur-xs cursor-pointer"
                  >
                    <Camera className="w-3.5 h-3.5" />
                    <span>Change Photo</span>
                  </button>
                </div>
              ) : (
                /* Fallback frame if file has not yet been placed on disk or selected */
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full h-full min-h-[480px] xl:min-h-[520px] rounded-2xl border-2 border-dashed border-[#DCDDD5] hover:border-[#526B5A] flex flex-col items-center justify-center p-6 text-center cursor-pointer transition-colors"
                >
                  <div className="w-12 h-12 rounded-full bg-[#E2E1DA] flex items-center justify-center text-[#526B5A] mb-3">
                    <Upload className="w-6 h-6" />
                  </div>
                  <p className="text-sm font-medium text-[#202522]">
                    Click to load your attached pharmacy photograph
                  </p>
                  <p className="text-xs text-[#5E625D] mt-1 max-w-xs">
                    Select <span className="font-mono text-[#202522]">WhatsApp Image 2026-09-12 at 5.53.19 PM.jpeg</span> or drag and drop it here.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
