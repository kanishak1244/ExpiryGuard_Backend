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
  whatsAppNumber: '919817066533',
  whatsAppUrl: 'https://wa.me/919817066533?text=Hi%2C%20my%20name%20is%20____.%20I%20want%20to%20make%20an%20inquiry%20about%20DawaiFlow%20and%20would%20like%20to%20know%20more%20about%20the%20pilot.',

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

/**
 * Generates official WhatsApp click-to-chat URL with pre-filled inquiry message.
 * Formats:
 * With name: "Hi, my name is [Name]. I want to make an inquiry about DawaiFlow and would like to know more about the pilot."
 * Without name: "Hi, my name is ____. I want to make an inquiry about DawaiFlow and would like to know more about the pilot."
 */
export const getWhatsAppInquiryUrl = (name?: string): string => {
  const cleanName = name?.trim();
  const message = cleanName
    ? `Hi, my name is ${cleanName}. I want to make an inquiry about DawaiFlow and would like to know more about the pilot.`
    : `Hi, my name is ____. I want to make an inquiry about DawaiFlow and would like to know more about the pilot.`;
  return `https://wa.me/919817066533?text=${encodeURIComponent(message)}`;
};
