// src/components/ui/NavCard.tsx
import React from 'react';
import { Search, Briefcase, BarChart3 } from 'lucide-react';

// A map to render icons dynamically
const iconMap: { [key: string]: React.ElementType } = {
  search: Search,
  roles: Briefcase,
  pipeline: BarChart3,
};

interface NavCardProps {
  icon: string;
  title: string;
  description: string;
  href: string;
}

export function NavCard({ icon, title, description, href }: NavCardProps) {
  const IconComponent = iconMap[icon];

  return (
    // The 'group' class allows us to trigger hover effects on child elements
    <a href={href} className="group relative flex items-center gap-4 p-6 bg-white rounded-lg shadow-sm border border-gray-200 transition-all hover:shadow-md hover:border-teal-500">
      {IconComponent && <IconComponent className="text-gray-600 group-hover:text-teal-500 transition-colors" size={24} />}
      <span className="font-semibold text-gray-800">{title}</span>
      
      {/* This description box is hidden by default and appears on hover */}
      <div className="absolute left-full ml-4 w-max p-3 bg-gray-800 text-white text-sm rounded-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
        {description}
      </div>
    </a>
  );
}
