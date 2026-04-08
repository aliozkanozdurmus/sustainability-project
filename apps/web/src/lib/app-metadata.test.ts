import { describe, expect, it } from "vitest";

import { buildAppMetadata } from "./app-metadata";

describe("buildAppMetadata", () => {
  it("exposes the expected icon and share-image references", () => {
    const metadata = buildAppMetadata("http://127.0.0.1:3000");

    expect(metadata.metadataBase?.toString()).toBe("http://127.0.0.1:3000/");
    expect(metadata.icons).toMatchObject({
      icon: [
        { url: "/favicon.ico" },
        { url: "/icon.png", type: "image/png", sizes: "512x512" },
      ],
      apple: [{ url: "/apple-icon.png", type: "image/png", sizes: "180x180" }],
    });
    expect(metadata.openGraph).toMatchObject({
      images: [
        {
          url: "/brand/veni-social-card.png",
          width: 1200,
          height: 630,
        },
      ],
    });
    expect(metadata.twitter).toMatchObject({
      card: "summary_large_image",
      images: ["/brand/veni-social-card.png"],
    });
  });
});
