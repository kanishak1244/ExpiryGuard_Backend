import React from 'react';
import { Cloud, FileCheck, Layers, Users, Lock, Database } from 'lucide-react';

export const SecuritySection: React.FC = () => {
  const points = [
    { title: 'Cloud-synchronized', icon: Cloud },
    { title: 'GST-ready billing', icon: FileCheck },
    { title: 'Batch-level inventory', icon: Layers },
    { title: 'Role-based access', icon: Users },
    { title: 'Secure authentication', icon: Lock },
    { title: 'Backup & restore', icon: Database },
  ];

  return (
    <section className="py-16 bg-slate-950 border-t border-slate-800/80">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <h3 className="text-xl sm:text-2xl font-bold text-white text-center mb-8">
          Built for real pharmacy operations.
        </h3>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3.5">
          {points.map((pt) => {
            const Icon = pt.icon;
            return (
              <div
                key={pt.title}
                className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center gap-3"
              >
                <div className="w-8 h-8 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-center text-emerald-400 shrink-0">
                  <Icon className="w-4 h-4" />
                </div>
                <span className="text-xs sm:text-sm font-medium text-slate-200">{pt.title}</span>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};
