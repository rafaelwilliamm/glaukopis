"use client";

import dynamic from 'next/dynamic';

const MonteCarloClient = dynamic(() => import('@/app/components/MonteCarloClient'), {
  ssr: false,
});

export default function MonteCarloPage() {
  return <MonteCarloClient />;
}
