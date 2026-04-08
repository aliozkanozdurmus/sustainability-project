import type { Metadata } from "next";

import { DEFAULT_BRAND_SOCIAL_CARD_PATH } from "@/lib/brand";
import { webEnv } from "@/lib/env/web-env";

const APP_TITLE = "Veni AI Sustainability Cockpit";
const APP_DESCRIPTION = "Zero-hallucination ESG reporting cockpit for TSRS and CSRD workflows.";

export function buildAppMetadata(
  appBaseUrl: string = webEnv.NEXT_PUBLIC_APP_BASE_URL ?? "http://127.0.0.1:3000",
): Metadata {
  return {
    metadataBase: new URL(appBaseUrl),
    title: APP_TITLE,
    description: APP_DESCRIPTION,
    icons: {
      icon: [
        { url: "/favicon.ico" },
        { url: "/icon.png", type: "image/png", sizes: "512x512" },
      ],
      shortcut: ["/favicon.ico"],
      apple: [{ url: "/apple-icon.png", type: "image/png", sizes: "180x180" }],
    },
    openGraph: {
      title: APP_TITLE,
      description: APP_DESCRIPTION,
      type: "website",
      images: [
        {
          url: DEFAULT_BRAND_SOCIAL_CARD_PATH,
          width: 1200,
          height: 630,
          alt: "Veni AI Sustainability Cockpit orbit-leaf brand card",
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: APP_TITLE,
      description: APP_DESCRIPTION,
      images: [DEFAULT_BRAND_SOCIAL_CARD_PATH],
    },
  };
}

export const appMetadata = buildAppMetadata();
