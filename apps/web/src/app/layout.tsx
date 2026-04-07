// Bu layout, uygulamanin ortak kabugunu ve global sarmalayicilarini kurar.

import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { cn } from "@/lib/utils";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Veni AI Sustainability Cockpit",
  description:
    "Zero-hallucination ESG reporting cockpit for TSRS and CSRD workflows.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning data-theme="factory-light">
      <body
        className={cn(
          "bg-canvas overflow-x-hidden overscroll-none font-sans antialiased",
          inter.variable,
        )}
      >
        {children}
      </body>
    </html>
  );
}
