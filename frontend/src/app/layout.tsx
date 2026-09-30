import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { Providers } from "./providers";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: { default: "Helpdesk TI", template: "%s · Helpdesk TI" },
  description: "Seguimiento de tickets de trabajo de TI",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-MX" suppressHydrationWarning>
      <body className={`${inter.variable} min-h-dvh font-sans antialiased`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
