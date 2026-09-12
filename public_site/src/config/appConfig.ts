// Configuration for DawaiFlow compliance, contact, and product details
// Sourced and verified from official project records (https://api.dawaiflow.com/)

export const APP_CONFIG = {
  productName: 'DawaiFlow',
  brandName: 'DawaiFlow (Powered by ExpiryGuard)',
  spelling: 'D-A-W-A-I-F-L-O-W',
  tagline: 'More time for your pharmacy. Less time managing software.',
  description:
    'DawaiFlow reduces repetitive work across billing, inventory, purchases and everyday pharmacy operations — so you can spend less time managing screens and more time serving customers.',

  // Founder & Legal Representative
  founderAndOfficer: 'Kanishak Vashist',

  // Contact Channels
  supportEmail: 'contact@dawaiflow.com',
  grievanceEmail: 'vashistkanishak9@gmail.com',
  supportPhone: '+91 98170 66533',
  supportPhoneFormatted: '+91 98170 66533',
  whatsAppUrl: 'https://wa.me/919817066533?text=Hi%20DawaiFlow%20team%2C%20I%20have%20questions%20about%20the%20pilot',

  // Location & Corporate Details (with explicit placeholders where statutory formal incorporation is pending)
  location: 'Sonipat, Haryana, India',
  legalEntityPlaceholder: '[LEGAL ENTITY NAME: Kanishak Vashist, trading as DawaiFlow / ExpiryGuard]',
  registeredOfficePlaceholder: '[REGISTERED OFFICE ADDRESS: Sonipat, Haryana, India — Street address to be updated upon corporate incorporation]',
  cinPlaceholder: '[CIN: To be updated upon corporate incorporation]',
  gstinPlaceholder: '[GSTIN: To be updated upon tax registration]',

  // Operational State
  pilotStatus: 'Invite-only free pilot for licensed retail pharmacies in India',
  isCommercialPaymentActive: false, // Currently in free pilot testing; no online payments collected
  isOnlineMedicineSeller: false, // B2B counter software only; strictly NOT an online pharmacy or e-pharmacy

  // Technical Infrastructure (Verified)
  infrastructure: {
    database: 'Supabase (PostgreSQL) with encrypted storage',
    transmission: 'Transport Layer Security (HTTPS/TLS)',
    authentication: 'Bcrypt password hashing and secure token-based sessions',
    alerts: 'Firebase Cloud Messaging (FCM) for real-time stock alerts',
    aiVision: 'DawaiFlow in-memory image OCR (images discarded immediately after text extraction)',
    analyticsCookies: 'None (No third-party tracking or advertising cookies)',
  },
};
