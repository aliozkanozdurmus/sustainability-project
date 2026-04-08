export type GoogleFontOption = {
  family: string;
  category: string;
};

export const GOOGLE_FONT_OPTIONS: GoogleFontOption[] = [
  { family: "Inter", category: "Sans / Editorial" },
  { family: "Manrope", category: "Sans / Editorial" },
  { family: "DM Sans", category: "Sans / Editorial" },
  { family: "Outfit", category: "Sans / Modern" },
  { family: "Plus Jakarta Sans", category: "Sans / Modern" },
  { family: "Space Grotesk", category: "Sans / Modern" },
  { family: "Urbanist", category: "Sans / Modern" },
  { family: "Source Sans 3", category: "Sans / Humanist" },
  { family: "Work Sans", category: "Sans / Humanist" },
  { family: "Public Sans", category: "Sans / Humanist" },
  { family: "Nunito Sans", category: "Sans / Humanist" },
  { family: "Montserrat", category: "Sans / Modern" },
  { family: "Poppins", category: "Sans / Modern" },
  { family: "Raleway", category: "Sans / Modern" },
  { family: "Rubik", category: "Sans / Humanist" },
  { family: "Lato", category: "Sans / Humanist" },
  { family: "Figtree", category: "Sans / Editorial" },
  { family: "Sora", category: "Sans / Modern" },
  { family: "Archivo", category: "Sans / Technical" },
  { family: "Barlow", category: "Sans / Technical" },
  { family: "Barlow Semi Condensed", category: "Sans / Technical" },
  { family: "Jost", category: "Sans / Modern" },
  { family: "Mulish", category: "Sans / Humanist" },
  { family: "Karla", category: "Sans / Humanist" },
  { family: "Cabin", category: "Sans / Humanist" },
  { family: "Assistant", category: "Sans / Humanist" },
  { family: "Overpass", category: "Sans / Technical" },
  { family: "IBM Plex Sans", category: "Sans / Technical" },
  { family: "Noto Sans", category: "Sans / Humanist" },
  { family: "Exo 2", category: "Sans / Technical" },
  { family: "Red Hat Display", category: "Sans / Editorial" },
  { family: "Be Vietnam Pro", category: "Sans / Modern" },
  { family: "Epilogue", category: "Sans / Editorial" },
  { family: "Onest", category: "Sans / Editorial" },
  { family: "Hanken Grotesk", category: "Sans / Editorial" },
  { family: "Libre Franklin", category: "Sans / Humanist" },
  { family: "Roboto Flex", category: "Sans / Technical" },
  { family: "M PLUS 1", category: "Sans / Modern" },
  { family: "Heebo", category: "Sans / Technical" },
  { family: "Lexend", category: "Sans / Humanist" },
  { family: "Alegreya Sans", category: "Sans / Humanist" },
  { family: "Merriweather", category: "Serif / Editorial" },
  { family: "Lora", category: "Serif / Editorial" },
  { family: "Playfair Display", category: "Serif / Display" },
  { family: "Cormorant Garamond", category: "Serif / Display" },
  { family: "Libre Baskerville", category: "Serif / Classic" },
  { family: "Bitter", category: "Serif / Executive" },
  { family: "Domine", category: "Serif / Executive" },
  { family: "Source Serif 4", category: "Serif / Editorial" },
  { family: "Spectral", category: "Serif / Editorial" },
  { family: "EB Garamond", category: "Serif / Classic" },
  { family: "Crimson Pro", category: "Serif / Classic" },
  { family: "PT Serif", category: "Serif / Classic" },
  { family: "Cardo", category: "Serif / Classic" },
  { family: "Fraunces", category: "Serif / Display" },
  { family: "Newsreader", category: "Serif / Editorial" },
  { family: "Noto Serif", category: "Serif / Executive" },
  { family: "Alegreya", category: "Serif / Editorial" },
  { family: "Literata", category: "Serif / Editorial" },
  { family: "Vollkorn", category: "Serif / Classic" },
  { family: "Libre Caslon Text", category: "Serif / Classic" },
  { family: "Arvo", category: "Serif / Executive" },
];

export const GOOGLE_FONT_FAMILY_SET = new Set(GOOGLE_FONT_OPTIONS.map((option) => option.family));

export type BrandFontPreset = {
  name: string;
  mood: string;
  heading: string;
  body: string;
};

export const BRAND_FONT_PRESETS: BrandFontPreset[] = [
  {
    name: "Board Clarity",
    mood: "Clean, corporate, investor-ready",
    heading: "Inter",
    body: "Source Sans 3",
  },
  {
    name: "Editorial Earth",
    mood: "Refined, warm, narrative-led",
    heading: "Playfair Display",
    body: "Source Serif 4",
  },
  {
    name: "Industrial Modern",
    mood: "Sharp, technical, precise",
    heading: "Space Grotesk",
    body: "IBM Plex Sans",
  },
  {
    name: "Human Impact",
    mood: "Accessible, credible, calm",
    heading: "Manrope",
    body: "Public Sans",
  },
  {
    name: "Nordic Report",
    mood: "Airy, contemporary, premium",
    heading: "Outfit",
    body: "Inter",
  },
  {
    name: "Strategy Review",
    mood: "Executive, timeless, formal",
    heading: "Fraunces",
    body: "Lora",
  },
];

export type BrandPalettePreset = {
  name: string;
  mood: string;
  primary: string;
  secondary: string;
  accent: string;
};

export const BRAND_PALETTE_PRESETS: BrandPalettePreset[] = [
  {
    name: "Bosphorus Mineral",
    mood: "Fresh, board-ready, coastal",
    primary: "#0f9d7a",
    secondary: "#16324f",
    accent: "#e0b941",
  },
  {
    name: "Pine and Clay",
    mood: "Grounded, warm, resilient",
    primary: "#1d6b50",
    secondary: "#253441",
    accent: "#e58d3b",
  },
  {
    name: "Nordic Current",
    mood: "Clean, data-forward, calm",
    primary: "#1b89b3",
    secondary: "#10263c",
    accent: "#8ac556",
  },
  {
    name: "Solar Quarry",
    mood: "Energetic, industrial, premium",
    primary: "#d66a1f",
    secondary: "#292825",
    accent: "#b4c84c",
  },
  {
    name: "Deep Moss",
    mood: "Natural, executive, assured",
    primary: "#4d7040",
    secondary: "#132921",
    accent: "#efbf4d",
  },
  {
    name: "Graphite Bloom",
    mood: "Measured, modern, strategic",
    primary: "#5d6d86",
    secondary: "#1d2430",
    accent: "#d7a14f",
  },
];

export function isSupportedGoogleFontFamily(value: string): boolean {
  return GOOGLE_FONT_FAMILY_SET.has(value.trim());
}

export function buildGoogleFontsStylesheetUrl(families: string[]): string | null {
  const uniqueFamilies = Array.from(
    new Set(
      families
        .map((family) => family.trim())
        .filter((family) => family.length > 0 && isSupportedGoogleFontFamily(family)),
    ),
  );

  if (uniqueFamilies.length === 0) {
    return null;
  }

  const query = uniqueFamilies
    .map(
      (family) =>
        `family=${encodeURIComponent(family).replaceAll("%20", "+")}:wght@400;500;600;700`,
    )
    .join("&");

  return `https://fonts.googleapis.com/css2?${query}&display=swap`;
}

export function isValidHexColor(value: string): boolean {
  return /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(value.trim());
}

export function normalizeHexColor(value: string, fallback: string): string {
  const normalized = value.trim();
  if (!isValidHexColor(normalized)) {
    return fallback;
  }

  if (normalized.length === 4) {
    const [, r, g, b] = normalized;
    return `#${r}${r}${g}${g}${b}${b}`.toLowerCase();
  }

  return normalized.toLowerCase();
}

type RgbColor = {
  r: number;
  g: number;
  b: number;
};

export type HslColor = {
  h: number;
  s: number;
  l: number;
};

function parseHexToRgb(value: string): RgbColor | null {
  const normalized = normalizeHexColor(value, "");
  if (!isValidHexColor(normalized)) {
    return null;
  }

  const raw = normalized.slice(1);
  return {
    r: Number.parseInt(raw.slice(0, 2), 16),
    g: Number.parseInt(raw.slice(2, 4), 16),
    b: Number.parseInt(raw.slice(4, 6), 16),
  };
}

function formatRgbToHex(color: RgbColor): string {
  return `#${[color.r, color.g, color.b]
    .map((channel) =>
      Math.max(0, Math.min(255, Math.round(channel)))
        .toString(16)
        .padStart(2, "0"),
    )
    .join("")}`;
}

export function hexToRgb(value: string, fallback = "#f07f13"): RgbColor {
  return parseHexToRgb(value) ?? parseHexToRgb(fallback) ?? { r: 240, g: 127, b: 19 };
}

export function hexToHsl(value: string, fallback = "#f07f13"): HslColor {
  const { r, g, b } = hexToRgb(value, fallback);
  const red = r / 255;
  const green = g / 255;
  const blue = b / 255;

  const max = Math.max(red, green, blue);
  const min = Math.min(red, green, blue);
  const delta = max - min;
  const lightness = (max + min) / 2;

  let hue = 0;
  let saturation = 0;

  if (delta !== 0) {
    saturation = delta / (1 - Math.abs(2 * lightness - 1));

    switch (max) {
      case red:
        hue = ((green - blue) / delta) % 6;
        break;
      case green:
        hue = (blue - red) / delta + 2;
        break;
      default:
        hue = (red - green) / delta + 4;
        break;
    }
  }

  return {
    h: Math.round((hue * 60 + 360) % 360),
    s: Math.round(saturation * 100),
    l: Math.round(lightness * 100),
  };
}

function channelToLuminance(channel: number): number {
  const value = channel / 255;
  if (value <= 0.03928) {
    return value / 12.92;
  }
  return ((value + 0.055) / 1.055) ** 2.4;
}

export function getRelativeLuminance(value: string, fallback = "#f07f13"): number {
  const { r, g, b } = hexToRgb(value, fallback);
  return (
    0.2126 * channelToLuminance(r) + 0.7152 * channelToLuminance(g) + 0.0722 * channelToLuminance(b)
  );
}

export function getContrastRatio(first: string, second: string): number {
  const luminanceA = getRelativeLuminance(first);
  const luminanceB = getRelativeLuminance(second);
  const lighter = Math.max(luminanceA, luminanceB);
  const darker = Math.min(luminanceA, luminanceB);
  return Number(((lighter + 0.05) / (darker + 0.05)).toFixed(2));
}

export function pickReadableTextColor(
  background: string,
  dark = "#10263c",
  light = "#ffffff",
): string {
  return getContrastRatio(background, dark) >= getContrastRatio(background, light) ? dark : light;
}

export function mixHexColors(from: string, to: string, amount: number): string {
  const start = hexToRgb(from);
  const end = hexToRgb(to);
  const clamped = Math.max(0, Math.min(1, amount));

  return formatRgbToHex({
    r: start.r + (end.r - start.r) * clamped,
    g: start.g + (end.g - start.g) * clamped,
    b: start.b + (end.b - start.b) * clamped,
  });
}

export function buildColorScale(value: string): string[] {
  const normalized = normalizeHexColor(value, "#f07f13");

  return [
    mixHexColors(normalized, "#ffffff", 0.72),
    mixHexColors(normalized, "#ffffff", 0.42),
    normalized,
    mixHexColors(normalized, "#10263c", 0.2),
    mixHexColors(normalized, "#0b1520", 0.45),
  ];
}
