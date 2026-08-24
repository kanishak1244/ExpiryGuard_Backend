/* ==========================================================================
   EXPIRYGUARD WEB APP — MULTI-LANGUAGE TRANSLATION ENGINE (i18n)
   Supports English & Hindi out of the box with extensible dictionary architecture.
   ========================================================================== */

const TRANSLATIONS = {
  en: {
    // Navigation
    dashboard: "Dashboard",
    aiBilling: "AI Billing",
    inventory: "Inventory",
    salesHistory: "Bills & Documents",
    returns: "Sale Returns",
    reports: "Reports & Analytics",
    settings: "Settings",
    logout: "Logout",

    // Dashboard & Overview
    overview: "Overview",
    totalSales: "Total Sales",
    totalMedicines: "Total Medicines",
    expiringSoon: "Expiring Soon",
    expired: "Expired",
    quickActions: "Quick Actions",
    newSale: "New Sale",
    addInventory: "Add Inventory",
    scanMedicine: "Scan Medicine",

    // Bills & Documents
    billsTitle: "Bills & Documents",
    billsSubtitle: "Manage, search, preview, print, download, and audit generated GST tax invoices.",
    invoiceNo: "Invoice No.",
    date: "Date & Time",
    customer: "Customer",
    items: "Items",
    gstAmount: "GST",
    grandTotal: "Grand Total",
    paymentMethod: "Payment",
    status: "Status",
    actions: "Actions",
    viewBill: "View Invoice",
    downloadPdf: "Download PDF",
    printBill: "Print",
    shareBill: "Share",
    deleteBill: "Delete",
    noBills: "No bills generated yet",
    createBillNow: "Create New Bill",

    // Settings
    settingsTitle: "Settings & System Management",
    accountSecurity: "Account & Security",
    pharmacyInfo: "Pharmacy Information",
    billingPrefs: "Billing Preferences",
    appearance: "Appearance",
    language: "Language",
    notifications: "Notifications",
    dataManagement: "Data & Backup",
    about: "About ExpiryGuard",

    // Common Buttons & Labels
    saveChanges: "Save Changes",
    cancel: "Cancel",
    confirmDelete: "Are you sure you want to delete this bill? Inventory stock will be restored.",
    lightMode: "Light Mode",
    darkMode: "Dark Mode",
    systemDefault: "System Default",
    english: "English",
    hindi: "Hindi (हिंदी)"
  },
  hi: {
    // Navigation
    dashboard: "डैशबोर्ड",
    aiBilling: "AI बिलिंग",
    inventory: "इन्वेंटरी (स्टॉक)",
    salesHistory: "बिल एवं दस्तावेज़",
    returns: "बिक्री वापसी",
    reports: "रिपोर्ट और विश्लेषण",
    settings: "सेटिंग्स",
    logout: "लॉग आउट",

    // Dashboard & Overview
    overview: "अवलोकन",
    totalSales: "कुल बिक्री",
    totalMedicines: "कुल दवाइयाँ",
    expiringSoon: "जल्द एक्सपायर होने वाली",
    expired: "एक्सपायर हो चुकी",
    quickActions: "त्वरित कार्य",
    newSale: "नई बिक्री",
    addInventory: "दवाई जोड़ें",
    scanMedicine: "दवाई स्कैन करें",

    // Bills & Documents
    billsTitle: "बिल एवं दस्तावेज़",
    billsSubtitle: "उत्पन्न GST टैक्स इनवॉइस प्रबंधित करें, खोजें, प्रिंट करें और डाउनलोड करें।",
    invoiceNo: "इनवॉइस नं.",
    date: "दिनांक एवं समय",
    customer: "ग्राहक का नाम",
    items: "मदें (आइटम)",
    gstAmount: "GST टैक्स",
    grandTotal: "कुल योग",
    paymentMethod: "भुगतान प्रकार",
    status: "स्थिति",
    actions: "कार्रवाई",
    viewBill: "इनवॉइस देखें",
    downloadPdf: "PDF डाउनलोड",
    printBill: "प्रिंट",
    shareBill: "शेयर करें",
    deleteBill: "हटाएं",
    noBills: "अभी तक कोई बिल नहीं बना है",
    createBillNow: "नया बिल बनाएं",

    // Settings
    settingsTitle: "सेटिंग्स एवं सिस्टम प्रबंधन",
    accountSecurity: "खाता और सुरक्षा",
    pharmacyInfo: "मेडिकल स्टोर / फार्मेसी विवरण",
    billingPrefs: "बिलिंग प्राथमिकताएं",
    appearance: "दिखावट (थीम)",
    language: "भाषा",
    notifications: "सूचनाएं एवं अलर्ट",
    dataManagement: "डेटा बैकअप एवं निर्यात",
    about: "ExpiryGuard के बारे में",

    // Common Buttons & Labels
    saveChanges: "बदलाव सहेजें",
    cancel: "रद्द करें",
    confirmDelete: "क्या आप वाकई इस बिल को हटाना चाहते हैं? इन्वेंटरी स्टॉक वापस जोड़ दिया जाएगा।",
    lightMode: "लाइट मोड",
    darkMode: "डार्क मोड",
    systemDefault: "सिस्टम डिफ़ॉल्ट",
    english: "English",
    hindi: "Hindi (हिंदी)"
  }
};

class LanguageEngine {
  constructor() {
    this.currentLang = localStorage.getItem('expiryguard_lang') || 'en';
  }

  setLanguage(lang) {
    if (TRANSLATIONS[lang]) {
      this.currentLang = lang;
      localStorage.setItem('expiryguard_lang', lang);
      this.applyTranslations();
    }
  }

  t(key) {
    return (TRANSLATIONS[this.currentLang] && TRANSLATIONS[this.currentLang][key]) || 
           (TRANSLATIONS['en'] && TRANSLATIONS['en'][key]) || 
           key;
  }

  applyTranslations() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      if (key) {
        el.textContent = this.t(key);
      }
    });

    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      if (key) {
        el.placeholder = this.t(key);
      }
    });
  }
}

const i18n = new LanguageEngine();
document.addEventListener('DOMContentLoaded', () => i18n.applyTranslations());
