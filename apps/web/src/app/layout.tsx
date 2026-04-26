// Bu layout, uygulamanin ortak kabugunu ve global sarmalayicilarini kurar.

import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { Providers } from "@/components/providers";
import { appMetadata } from "@/lib/app-metadata";
import { cn } from "@/lib/utils";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  ...appMetadata,
} satisfies Metadata;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="tr-TR" suppressHydrationWarning data-theme="factory-light">
      <body
        className={cn(
          "bg-canvas overflow-x-hidden overscroll-none font-sans antialiased",
          inter.variable,
        )}
      >
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
