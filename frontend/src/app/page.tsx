"use client";

import dynamic from 'next/dynamic';

const DashboardClient = dynamic(() => import('@/app/components/DashboardClient'), { 
  ssr: false,
});

export default function Home() {
  return <DashboardClient />;
}
