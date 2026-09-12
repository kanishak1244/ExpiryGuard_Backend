import React, { useState, useEffect, useRef } from 'react';
import {
  Camera,
  CheckCircle2,
  Receipt,
  Check,
  Layers,
  Monitor,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

interface StepData {
  id: number;
  label: string;
  tagline: string;
  shortDesc: string;
}

const STEPS: StepData[] = [
  {
    id: 1,
    label: 'Scan',
    tagline: '01 — SCAN',
    shortDesc: 'Scan multiple medicine strips.',
  },
  {
    id: 2,
    label: 'Identify',
    tagline: '02 — IDENTIFY',
    shortDesc: 'DawaiFlow identifies and matches the medicines.',
  },
  {
    id: 3,
    label: 'Bill',
    tagline: '03 — BILL',
    shortDesc: 'The items move into the billing workflow.',
  },
  {
    id: 4,
    label: 'Confirm',
    tagline: '04 — CONFIRM',
    shortDesc: 'Review and confirm.',
  },
  {
    id: 5,
    label: 'Done',
    tagline: '05 — DONE',
    shortDesc: 'Get back to your customer.',
  },
];

export const ScrollWorkflowSection: React.FC = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [activeStep, setActiveStep] = useState(1);
  const [scrollProgress, setScrollProgress] = useState(0);

  useEffect(() => {
    const handleScroll = () => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const totalScrollableDistance = containerRef.current.offsetHeight - window.innerHeight;

      if (totalScrollableDistance <= 0) return;

      const currentScroll = -rect.top;
      const progress = Math.max(0, Math.min(1, currentScroll / totalScrollableDistance));
      setScrollProgress(progress);

      if (progress < 0.2) {
        setActiveStep(1);
      } else if (progress < 0.4) {
        setActiveStep(2);
      } else if (progress < 0.6) {
        setActiveStep(3);
      } else if (progress < 0.8) {
        setActiveStep(4);
      } else {
        setActiveStep(5);
      }
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    handleScroll();

    return () => {
      window.removeEventListener('scroll', handleScroll);
    };
  }, []);

  const handleStepClick = (stepId: number) => {
    setActiveStep(stepId);
    if (!containerRef.current) return;
    const containerTop = containerRef.current.offsetTop;
    const totalScrollableDistance = containerRef.current.offsetHeight - window.innerHeight;
    const targetProgress = (stepId - 0.5) / STEPS.length;
    window.scrollTo({
      top: containerTop + targetProgress * totalScrollableDistance,
      behavior: 'smooth',
    });
  };

  const handlePrev = () => {
    if (activeStep > 1) handleStepClick(activeStep - 1);
  };

  const handleNext = () => {
    if (activeStep < STEPS.length) handleStepClick(activeStep + 1);
  };

  const current = STEPS[activeStep - 1] || STEPS[0];

  return (
    <section
      id="workflow-demo"
      ref={containerRef}
      className="relative bg-[#F5F4EF] text-[#202522] border-b border-[#DCDDD5] min-h-[220vh] sm:min-h-[260vh] lg:min-h-[300vh]"
    >
      {/* Sticky presentation viewport */}
      <div className="sticky top-16 h-[calc(100vh-4rem)] max-h-[840px] flex flex-col justify-between py-6 sm:py-8 overflow-hidden">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 w-full flex-1 flex flex-col justify-between">
          {/* Section Header: 32-40px desktop, 26-32px mobile */}
          <div className="text-center max-w-2xl mx-auto mb-4 sm:mb-6 shrink-0">
            <h2 className="text-2xl sm:text-3xl lg:text-[36px] font-semibold text-[#202522] tracking-tight leading-tight">
              Less manual work.{' '}
              <span className="text-[#526B5A] block sm:inline">More time for your pharmacy.</span>
            </h2>

            <p className="mt-2 text-xs sm:text-sm text-[#5E625D]">
              See how a few simple steps can replace repetitive work behind the counter.
            </p>
          </div>

          {/* Step Navigation Pill Bar */}
          <div className="shrink-0 mb-4 sm:mb-6">
            <div className="flex items-center justify-between max-w-md mx-auto bg-[#EDECE6] p-1 rounded-lg border border-[#DCDDD5]">
              {STEPS.map((step) => {
                const isActive = step.id === activeStep;
                const isPassed = step.id < activeStep;
                return (
                  <button
                    key={step.id}
                    type="button"
                    onClick={() => handleStepClick(step.id)}
                    className={`flex-1 flex items-center justify-center gap-1 sm:gap-1.5 py-1.5 px-1 rounded-md text-xs transition-colors cursor-pointer ${
                      isActive
                        ? 'bg-[#526B5A] text-white font-medium shadow-xs'
                        : isPassed
                        ? 'text-[#526B5A] hover:bg-[#F5F4EF]'
                        : 'text-[#5E625D] hover:text-[#202522] hover:bg-[#F5F4EF]'
                    }`}
                    aria-label={`Step ${step.id}: ${step.label}`}
                  >
                    <span
                      className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-medium ${
                        isActive
                          ? 'bg-white text-[#526B5A]'
                          : isPassed
                          ? 'bg-[#526B5A]/15 text-[#526B5A]'
                          : 'bg-[#DCDDD5] text-[#5E625D]'
                      }`}
                    >
                      {isPassed ? '✓' : step.id}
                    </span>
                    <span className="text-[11px] sm:text-xs truncate">{step.label}</span>
                  </button>
                );
              })}
            </div>

            {/* Scroll Progress Line */}
            <div className="max-w-md mx-auto mt-2 h-1 bg-[#DCDDD5] rounded-full overflow-hidden">
              <div
                className="h-full bg-[#526B5A] transition-all duration-150"
                style={{ width: `${Math.round(scrollProgress * 100)}%` }}
              />
            </div>
          </div>

          {/* Main Visual Stage: Desktop Side-by-Side / Mobile Stacked */}
          <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-12 gap-5 lg:gap-8 items-center">
            {/* Left Column: Short step description */}
            <div className="lg:col-span-5 space-y-2 sm:space-y-3 text-center lg:text-left">
              <div className="text-xs font-mono font-medium text-[#526B5A] uppercase tracking-wider">
                {current.tagline}
              </div>

              <h3 className="text-xl sm:text-2xl font-semibold text-[#202522] tracking-tight">
                {current.label}
              </h3>

              <p className="text-[15px] sm:text-base text-[#5E625D] leading-relaxed max-w-md mx-auto lg:mx-0">
                {current.shortDesc}
              </p>

              {/* Navigation Controls */}
              <div className="flex items-center justify-center lg:justify-start gap-2 pt-2">
                <button
                  type="button"
                  onClick={handlePrev}
                  disabled={activeStep === 1}
                  className="px-2.5 py-1 rounded-md bg-[#EDECE6] border border-[#DCDDD5] text-xs text-[#5E625D] hover:text-[#202522] disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1 cursor-pointer transition-colors"
                  aria-label="Previous step"
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Prev</span>
                </button>
                <button
                  type="button"
                  onClick={handleNext}
                  disabled={activeStep === STEPS.length}
                  className="px-2.5 py-1 rounded-md bg-[#EDECE6] border border-[#DCDDD5] text-xs text-[#5E625D] hover:text-[#202522] disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1 cursor-pointer transition-colors"
                  aria-label="Next step"
                >
                  <span className="hidden sm:inline">Next</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
                <span className="text-[11px] font-mono text-[#5E625D] ml-2">
                  Step {activeStep} of 5
                </span>
              </div>
            </div>

            {/* Right Column: Visual Stage */}
            <div className="lg:col-span-7 h-full flex items-center justify-center">
              <div className="w-full max-w-lg bg-[#FFFFFF] border border-[#DCDDD5] rounded-xl p-4 sm:p-5 shadow-xs relative overflow-hidden transition-all duration-300">
                {/* STEP 1: SCAN */}
                {activeStep === 1 && (
                  <div className="space-y-3 py-1">
                    <div className="flex items-center justify-between text-xs text-[#5E625D] border-b border-[#DCDDD5] pb-2 font-mono">
                      <span className="flex items-center gap-1.5 text-[#526B5A] font-medium">
                        <Camera className="w-3.5 h-3.5" /> Counter Strip Scanner
                      </span>
                      <span>Target: 3 Medicine Strips</span>
                    </div>

                    <div className="relative rounded-lg bg-[#F5F4EF] border border-[#DCDDD5] p-3 sm:p-4 overflow-hidden min-h-[190px] sm:min-h-[210px] flex flex-col justify-between">
                      <div className="flex items-center justify-between text-[11px] font-mono text-[#5E625D]">
                        <span>Camera Active</span>
                        <span className="text-[#526B5A] font-medium">● Detecting</span>
                      </div>

                      {/* 3 Strips on Counter */}
                      <div className="grid grid-cols-3 gap-2 my-2">
                        <div className="relative p-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-md text-center">
                          <span className="absolute -top-2 left-1 bg-[#526B5A] text-[9px] font-mono text-white px-1 rounded">
                            STRIP 1
                          </span>
                          <div className="text-[11px] font-semibold text-[#202522] mt-1 truncate">Augmentin</div>
                          <div className="text-[9px] text-[#5E625D]">625 DUO</div>
                          <div className="mt-1 flex justify-center gap-0.5">
                            {[...Array(6)].map((_, i) => (
                              <span key={i} className="w-1.5 h-2 bg-[#DCDDD5] rounded-xs" />
                            ))}
                          </div>
                        </div>

                        <div className="relative p-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-md text-center">
                          <span className="absolute -top-2 left-1 bg-[#526B5A] text-[9px] font-mono text-white px-1 rounded">
                            STRIP 2
                          </span>
                          <div className="text-[11px] font-semibold text-[#202522] mt-1 truncate">Pan 40</div>
                          <div className="text-[9px] text-[#5E625D]">Pantoprazole</div>
                          <div className="mt-1 flex justify-center gap-0.5">
                            {[...Array(5)].map((_, i) => (
                              <span key={i} className="w-1.5 h-2 bg-[#DCDDD5] rounded-xs" />
                            ))}
                          </div>
                        </div>

                        <div className="relative p-2 bg-[#FFFFFF] border border-[#DCDDD5] rounded-md text-center">
                          <span className="absolute -top-2 left-1 bg-[#526B5A] text-[9px] font-mono text-white px-1 rounded">
                            STRIP 3
                          </span>
                          <div className="text-[11px] font-semibold text-[#202522] mt-1 truncate">Dolo 650</div>
                          <div className="text-[9px] text-[#5E625D]">Paracetamol</div>
                          <div className="mt-1 flex justify-center gap-0.5">
                            {[...Array(6)].map((_, i) => (
                              <span key={i} className="w-1.5 h-2 bg-[#DCDDD5] rounded-xs" />
                            ))}
                          </div>
                        </div>
                      </div>

                      <div className="text-center text-[10px] text-[#5E625D] font-mono">
                        Hold camera steadily over counter strips
                      </div>
                    </div>
                  </div>
                )}

                {/* STEP 2: IDENTIFY */}
                {activeStep === 2 && (
                  <div className="space-y-2.5 sm:space-y-3 py-1">
                    <div className="flex items-center justify-between text-xs text-[#5E625D] border-b border-[#DCDDD5] pb-2 font-mono">
                      <span className="flex items-center gap-1.5 text-[#526B5A] font-medium">
                        <CheckCircle2 className="w-3.5 h-3.5" /> Matched In Store Inventory
                      </span>
                      <span className="text-[#526B5A] font-medium text-[11px]">3 Matched</span>
                    </div>

                    <div className="space-y-1.5 sm:space-y-2 font-mono text-xs">
                      <div className="p-2 sm:p-2.5 bg-[#F5F4EF] border border-[#DCDDD5] rounded-md flex items-center justify-between">
                        <div>
                          <div className="font-semibold text-[#202522] text-xs">Augmentin 625 Duo</div>
                          <div className="text-[10px] text-[#5E625D]">Batch AG-942 • Exp 08/26</div>
                        </div>
                        <span className="text-[#526B5A] font-medium bg-[#EDECE6] px-2 py-0.5 rounded text-[10px]">
                          Matched
                        </span>
                      </div>

                      <div className="p-2 sm:p-2.5 bg-[#F5F4EF] border border-[#DCDDD5] rounded-md flex items-center justify-between">
                        <div>
                          <div className="font-semibold text-[#202522] text-xs">Pan 40 Tablet</div>
                          <div className="text-[10px] text-[#5E625D]">Batch PN-108 • Exp 11/26</div>
                        </div>
                        <span className="text-[#526B5A] font-medium bg-[#EDECE6] px-2 py-0.5 rounded text-[10px]">
                          Matched
                        </span>
                      </div>

                      <div className="p-2 sm:p-2.5 bg-[#F5F4EF] border border-[#DCDDD5] rounded-md flex items-center justify-between">
                        <div>
                          <div className="font-semibold text-[#202522] text-xs">Dolo 650mg</div>
                          <div className="text-[10px] text-[#5E625D]">Batch DL-331 • Exp 05/27</div>
                        </div>
                        <span className="text-[#526B5A] font-medium bg-[#EDECE6] px-2 py-0.5 rounded text-[10px]">
                          Matched
                        </span>
                      </div>
                    </div>

                    <div className="text-[11px] text-[#5E625D] text-center font-mono">
                      FEFO batch automatically selected based on nearest expiry
                    </div>
                  </div>
                )}

                {/* STEP 3: BILL */}
                {activeStep === 3 && (
                  <div className="space-y-2.5 sm:space-y-3 py-1">
                    <div className="flex items-center justify-between text-xs text-[#5E625D] border-b border-[#DCDDD5] pb-2 font-mono">
                      <span className="flex items-center gap-1.5 text-[#526B5A] font-medium">
                        <Monitor className="w-3.5 h-3.5" /> Counter Billing Screen
                      </span>
                      <span className="text-[#5E625D] text-[11px]">Bill #2841</span>
                    </div>

                    <div className="rounded-md bg-[#F5F4EF] border border-[#DCDDD5] overflow-hidden text-[11px] font-mono">
                      <div className="grid grid-cols-12 bg-[#EDECE6] p-1.5 sm:p-2 text-[#5E625D] font-medium border-b border-[#DCDDD5]">
                        <span className="col-span-6">Medicine</span>
                        <span className="col-span-3 text-center">Batch</span>
                        <span className="col-span-3 text-right">Price</span>
                      </div>

                      <div className="divide-y divide-[#DCDDD5]">
                        <div className="grid grid-cols-12 p-1.5 sm:p-2 text-[#202522] bg-[#FFFFFF]">
                          <span className="col-span-6 truncate font-medium">Augmentin 625</span>
                          <span className="col-span-3 text-center text-[#5E625D]">AG-942</span>
                          <span className="col-span-3 text-right text-[#526B5A] font-medium">₹204.00</span>
                        </div>
                        <div className="grid grid-cols-12 p-1.5 sm:p-2 text-[#202522] bg-[#FFFFFF]">
                          <span className="col-span-6 truncate font-medium">Pan 40 Tablet</span>
                          <span className="col-span-3 text-center text-[#5E625D]">PN-108</span>
                          <span className="col-span-3 text-right text-[#526B5A] font-medium">₹148.00</span>
                        </div>
                        <div className="grid grid-cols-12 p-1.5 sm:p-2 text-[#202522] bg-[#FFFFFF]">
                          <span className="col-span-6 truncate font-medium">Dolo 650mg</span>
                          <span className="col-span-3 text-center text-[#5E625D]">DL-331</span>
                          <span className="col-span-3 text-right text-[#526B5A] font-medium">₹34.00</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex justify-between items-center text-xs font-mono px-1">
                      <span className="text-[#5E625D]">3 items populated</span>
                      <span className="text-[#202522] font-semibold">Subtotal: ₹386.00</span>
                    </div>
                  </div>
                )}

                {/* STEP 4: CONFIRM */}
                {activeStep === 4 && (
                  <div className="space-y-2.5 sm:space-y-3 py-1">
                    <div className="flex items-center justify-between text-xs text-[#5E625D] border-b border-[#DCDDD5] pb-2 font-mono">
                      <span className="flex items-center gap-1.5 text-[#526B5A] font-medium">
                        <Receipt className="w-3.5 h-3.5" /> Review &amp; Tender
                      </span>
                      <span className="text-[#526B5A] text-[11px] font-medium">Ready</span>
                    </div>

                    <div className="p-2.5 sm:p-3 bg-[#F5F4EF] border border-[#DCDDD5] rounded-md space-y-1.5 font-mono text-xs">
                      <div className="flex justify-between items-center text-[#202522]">
                        <span>Items:</span>
                        <span className="font-semibold text-[#202522]">3 Strips (40 Tablets)</span>
                      </div>
                      <div className="flex justify-between items-center text-[#202522]">
                        <span>Taxes:</span>
                        <span className="text-[#5E625D]">Included in MRP</span>
                      </div>
                      <div className="flex justify-between items-center pt-1.5 border-t border-[#DCDDD5] text-sm">
                        <span className="font-semibold text-[#202522]">Total:</span>
                        <span className="font-semibold text-[#526B5A] text-base">₹386.00</span>
                      </div>
                    </div>

                    <div className="pt-1">
                      <div className="w-full py-2 bg-[#526B5A] rounded-md text-white font-medium text-xs flex items-center justify-center gap-2">
                        <Check className="w-4 h-4" />
                        <span>Confirmed &amp; Tendered</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* STEP 5: DONE */}
                {activeStep === 5 && (
                  <div className="space-y-2.5 sm:space-y-3 py-1">
                    <div className="flex items-center justify-between text-xs text-[#5E625D] border-b border-[#DCDDD5] pb-2 font-mono">
                      <span className="flex items-center gap-1.5 text-[#526B5A] font-medium">
                        <Layers className="w-3.5 h-3.5" /> Stock Updated &amp; Receipt Printed
                      </span>
                      <span className="text-[#526B5A] font-medium text-[11px]">Completed</span>
                    </div>

                    <div className="space-y-1.5 font-mono text-xs">
                      <div className="p-2 bg-[#F5F4EF] rounded-md border border-[#DCDDD5] flex justify-between items-center">
                        <span className="text-[#202522] truncate">Augmentin 625 (AG-942)</span>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <span className="text-[#5E625D]">48 → 47</span>
                          <span className="text-[#526B5A] font-medium text-[10px] bg-[#EDECE6] px-1.5 py-0.5 rounded">
                            -1
                          </span>
                        </div>
                      </div>

                      <div className="p-2 bg-[#F5F4EF] rounded-md border border-[#DCDDD5] flex justify-between items-center">
                        <span className="text-[#202522] truncate">Pan 40 Tablet (PN-108)</span>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <span className="text-[#5E625D]">120 → 119</span>
                          <span className="text-[#526B5A] font-medium text-[10px] bg-[#EDECE6] px-1.5 py-0.5 rounded">
                            -1
                          </span>
                        </div>
                      </div>

                      <div className="p-2 bg-[#F5F4EF] rounded-md border border-[#DCDDD5] flex justify-between items-center">
                        <span className="text-[#202522] truncate">Dolo 650mg (DL-331)</span>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <span className="text-[#5E625D]">250 → 249</span>
                          <span className="text-[#526B5A] font-medium text-[10px] bg-[#EDECE6] px-1.5 py-0.5 rounded">
                            -1
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="p-2.5 bg-[#EDECE6] border border-[#DCDDD5] rounded-md flex items-center justify-between text-xs font-mono">
                      <span className="text-[#526B5A] font-medium">Receipt Printed &amp; Ledger Synced</span>
                      <span className="text-[#202522] font-semibold">~90s Saved</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
