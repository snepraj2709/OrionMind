import type { Metadata } from 'next';
import { Inter, Lora } from 'next/font/google';
import type { ReactNode } from 'react';

import { APP_DESCRIPTION, APP_NAME } from '@/constants/app';
import { RootProviders } from '@/providers';

import './globals.css';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
});

const lora = Lora({
  subsets: ['latin'],
  variable: '--font-lora',
  display: 'swap',
});

export const metadata: Metadata = {
  title: {
    default: APP_NAME,
    template: `%s | ${APP_NAME}`,
  },
  description: APP_DESCRIPTION,
  applicationName: APP_NAME,
};

interface RootLayoutProps {
  children: ReactNode;
}

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en" className={`${inter.variable} ${lora.variable}`}>
      <body>
        <RootProviders>{children}</RootProviders>
      </body>
    </html>
  );
}
