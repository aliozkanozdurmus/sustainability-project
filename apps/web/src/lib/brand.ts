export const DEFAULT_BRAND_LOGO_PATH = "/brand/veni-logo-clean-orbit-emblem.png";
export const DEFAULT_BRAND_SOCIAL_CARD_PATH = "/brand/veni-social-card.png";

export function resolveBrandLogoUri(logoUri?: string | null): string {
  const normalized = logoUri?.trim();
  return normalized && normalized.length > 0 ? normalized : DEFAULT_BRAND_LOGO_PATH;
}
