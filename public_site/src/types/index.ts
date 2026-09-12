export interface PilotApplication {
  pharmacyName: string;
  contactPerson: string;
  phone: string;
  email?: string;
  city: string;
  currentBillingMethod: string;
  estimatedDailyBills: string;
  numPharmacies?: string;
  notes?: string;
}

export interface FeatureCard {
  id: string;
  title: string;
  description: string;
  badge?: string;
  workflow?: string[];
}
