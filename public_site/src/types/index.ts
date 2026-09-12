export interface PilotApplication {
  pharmacyName: string;
  contactPerson: string;
  phone: string;
  email: string;
  city: string;
  pharmacyType: 'independent' | 'growing_team' | 'modern_chemist';
  estimatedDailyBills: string;
  notes?: string;
}

export interface FeatureCard {
  id: string;
  title: string;
  description: string;
  badge?: string;
  workflow?: string[];
}
