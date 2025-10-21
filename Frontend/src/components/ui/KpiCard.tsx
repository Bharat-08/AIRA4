// src/components/ui/KpiCard.tsx
import { FolderOpen, Users, Star } from 'lucide-react'; // <-- REMOVED LucideProps
import React from 'react';

const iconMap: { [key: string]: React.ElementType } = { // <-- REMOVED LucideProps type
  'folder-open': FolderOpen, 'users': Users, 'star': Star,
};

interface KpiCardProps {
  icon: string; value: number; label: string;
}

export function KpiCard({ icon, value, label }: KpiCardProps) {
  const IconComponent = iconMap[icon];
  return (
    <div className="flex items-center gap-4 p-6 bg-white rounded-lg shadow-sm border">
      <div className="p-3 bg-gray-100 rounded-full">
        {IconComponent && <IconComponent className="text-gray-600" size={24} />}
      </div>
      <div>
        <p className="text-3xl font-bold text-gray-800">{value}</p>
        <p className="text-sm text-gray-500">{label}</p>
      </div>
    </div>
  );
}