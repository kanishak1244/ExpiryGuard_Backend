import React, { useState, useEffect } from 'react';
import { Menu, X, ArrowRight } from 'lucide-react';

interface NavbarProps {
  onOpenPilot: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ onOpenPilot }) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isScrolled, setIsScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 15);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const navLinks = [
    { label: 'Product', href: '#product' },
    { label: 'Workflow', href: '#workflow-demo' },
    { label: 'Features', href: '#features' },
    { label: 'Pilot', href: '#pilot' },
  ];

  const handleNavClick = (e: React.MouseEvent<HTMLAnchorElement>, href: string) => {
    e.preventDefault();
    setIsMobileMenuOpen(false);
    const element = document.querySelector(href);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <header
      id="main-navbar"
      className={`sticky top-0 z-50 w-full transition-colors duration-150 ${
        isScrolled
          ? 'bg-[#F5F4EF]/95 backdrop-blur-xs border-b border-[#DCDDD5] shadow-xs'
          : 'bg-[#F5F4EF] border-b border-[#DCDDD5]/70'
      }`}
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand Logo */}
          <a
            href="#product"
            onClick={(e) => handleNavClick(e, '#product')}
            className="flex items-center gap-2.5 group focus:outline-none rounded-md"
          >
            <div className="w-7 h-7 rounded-md bg-[#526B5A] flex items-center justify-center text-white">
              <div className="w-3 h-3 relative">
                <span className="absolute inset-x-0.5 inset-y-0 bg-white rounded-xs" />
                <span className="absolute inset-y-0.5 inset-x-0 bg-white rounded-xs" />
              </div>
            </div>
            <span className="text-base font-semibold tracking-tight text-[#202522]">
              DawaiFlow
            </span>
          </a>

          {/* Desktop Navigation Links */}
          <nav className="hidden md:flex items-center gap-7" aria-label="Main Navigation">
            {navLinks.map((link) => (
              <a
                key={link.label}
                href={link.href}
                onClick={(e) => handleNavClick(e, link.href)}
                className="text-sm font-medium text-[#5E625D] hover:text-[#202522] transition-colors py-1 focus:outline-none"
              >
                {link.label}
              </a>
            ))}
          </nav>

          {/* Desktop Primary CTA */}
          <div className="hidden md:flex items-center gap-3">
            <button
              id="nav-get-started-btn"
              type="button"
              onClick={onOpenPilot}
              className="px-4 py-2 text-sm font-medium text-white bg-[#526B5A] hover:bg-[#43584a] rounded-lg transition-colors flex items-center gap-1.5 cursor-pointer shadow-xs active:scale-[0.99]"
            >
              <span>Get Started</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Mobile Menu Icon */}
          <div className="flex md:hidden items-center">
            <button
              id="mobile-menu-toggle"
              type="button"
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="p-2 text-[#5E625D] hover:text-[#202522] focus:outline-none rounded-md"
              aria-label={isMobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}
              aria-expanded={isMobileMenuOpen}
            >
              {isMobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Navigation Drawer */}
      {isMobileMenuOpen && (
        <div
          id="mobile-nav-panel"
          className="md:hidden border-b border-[#DCDDD5] bg-[#F5F4EF] px-5 py-4 space-y-3"
        >
          <div className="space-y-1">
            {navLinks.map((link) => (
              <a
                key={link.label}
                href={link.href}
                onClick={(e) => handleNavClick(e, link.href)}
                className="block px-3 py-2 text-sm font-medium text-[#202522] hover:bg-[#EDECE6] rounded-md transition-colors"
              >
                {link.label}
              </a>
            ))}
          </div>

          <div className="pt-2 border-t border-[#DCDDD5]">
            <button
              type="button"
              onClick={() => {
                setIsMobileMenuOpen(false);
                onOpenPilot();
              }}
              className="w-full py-2.5 text-sm font-medium text-white bg-[#526B5A] hover:bg-[#43584a] rounded-lg flex items-center justify-center gap-1.5 transition-colors"
            >
              <span>Get Started</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </header>
  );
};
