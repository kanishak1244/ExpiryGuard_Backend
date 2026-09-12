import React, { useState, useEffect } from 'react';
import { Navbar } from './components/Navbar';
import { Hero } from './components/Hero';
import { ProblemSection } from './components/ProblemSection';
import { ScrollWorkflowSection } from './components/ScrollWorkflowSection';
import { RealProductVisual } from './components/RealProductVisual';
import { SecondaryFeatures } from './components/SecondaryFeatures';
import { WhoIsItFor } from './components/WhoIsItFor';
import { PilotSection } from './components/PilotSection';
import { FaqSection } from './components/FaqSection';
import { ContactSection } from './components/ContactSection';
import { Footer } from './components/Footer';
import { PilotModal } from './components/PilotModal';
import { LegalModal, LegalDocType } from './components/legal/LegalModal';

export default function App() {
  const [isPilotModalOpen, setIsPilotModalOpen] = useState(false);
  const [isLegalModalOpen, setIsLegalModalOpen] = useState(false);
  const [activeLegalDoc, setActiveLegalDoc] = useState<LegalDocType>('privacy');

  // Handle URL hash changes for legal documents (e.g. #privacy, #terms, #data-policy, #disclaimer, #contact)
  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.toLowerCase().replace('#', '');
      if (hash === 'privacy' || hash === 'privacy-policy') {
        setActiveLegalDoc('privacy');
        setIsLegalModalOpen(true);
      } else if (hash === 'terms' || hash === 'terms-of-use') {
        setActiveLegalDoc('terms');
        setIsLegalModalOpen(true);
      } else if (hash === 'data-policy' || hash === 'data' || hash === 'app-info') {
        setActiveLegalDoc('data-policy');
        setIsLegalModalOpen(true);
      } else if (hash === 'disclaimer' || hash === 'medical-disclaimer') {
        setActiveLegalDoc('disclaimer');
        setIsLegalModalOpen(true);
      } else if (hash === 'contact-grievance' || hash === 'grievance' || hash === 'officer') {
        setActiveLegalDoc('contact-grievance');
        setIsLegalModalOpen(true);
      }
    };

    // Check initial hash
    handleHashChange();

    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const openPilot = () => setIsPilotModalOpen(true);
  const closePilot = () => setIsPilotModalOpen(false);

  const openLegal = (doc: LegalDocType) => {
    setActiveLegalDoc(doc);
    setIsLegalModalOpen(true);
    // Update hash cleanly without jump
    window.history.replaceState(null, '', `#${doc}`);
  };

  const closeLegal = () => {
    setIsLegalModalOpen(false);
    // Clean hash
    if (window.location.hash) {
      window.history.replaceState(null, '', window.location.pathname);
    }
  };

  return (
    <div className="min-h-screen bg-[#F5F4EF] text-[#202522] flex flex-col font-sans selection:bg-[#526B5A] selection:text-white">
      {/* 1. Navbar */}
      <Navbar onOpenPilot={openPilot} />

      {/* Main Narrative Content */}
      <main className="flex-1">
        {/* 2. Hero: "More time for your pharmacy. Less time managing software." */}
        <Hero onOpenPilot={openPilot} />

        {/* 3. "Pharmacy work is already busy." -> "Built to save your time." */}
        <ProblemSection />

        {/* 4. Interactive Scroll-Driven Workflow: SCAN → IDENTIFY → BILL → CONFIRM → DONE */}
        <ScrollWorkflowSection />

        {/* 5. Real Product Visuals: Laptop (Web App) + Phone (Mobile App) */}
        <RealProductVisual onOpenPilot={openPilot} />

        {/* 6. Supporting Features (Compact 17 Essentials) */}
        <SecondaryFeatures />

        {/* 7. Who It's For */}
        <WhoIsItFor />

        {/* 8. Pilot Section CTA */}
        <PilotSection onOpenPilot={openPilot} />

        {/* 9. FAQ */}
        <FaqSection />

        {/* 10. Get in Touch: WhatsApp, Support, Grievances */}
        <ContactSection />
      </main>

      {/* 10. Footer with Full Compliance & Legal Links */}
      <Footer onOpenPilot={openPilot} onOpenLegal={openLegal} />

      {/* Pilot Request Modal */}
      <PilotModal
        isOpen={isPilotModalOpen}
        onClose={closePilot}
        onOpenLegal={(doc) => {
          setIsPilotModalOpen(false);
          openLegal(doc);
        }}
      />

      {/* Legal & Compliance Modal */}
      <LegalModal
        isOpen={isLegalModalOpen}
        activeDoc={activeLegalDoc}
        onClose={closeLegal}
        onSelectDoc={(doc) => {
          setActiveLegalDoc(doc);
          window.history.replaceState(null, '', `#${doc}`);
        }}
      />
    </div>
  );
}
