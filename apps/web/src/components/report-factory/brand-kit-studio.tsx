"use client";

import {
  type ChangeEvent,
  type Dispatch,
  type SetStateAction,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Check, Loader2, Palette, Search, Type, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { WorkspaceContext } from "@/lib/api/client";
import { uploadBrandKitLogo } from "@/lib/api/catalog";
import type { WorkspaceSetupState } from "@/lib/api/report-factory";
import {
  BRAND_FONT_PRESETS,
  BRAND_PALETTE_PRESETS,
  GOOGLE_FONT_OPTIONS,
  buildColorScale,
  buildGoogleFontsStylesheetUrl,
  getContrastRatio,
  hexToHsl,
  isSupportedGoogleFontFamily,
  isValidHexColor,
  mixHexColors,
  normalizeHexColor,
  pickReadableTextColor,
} from "@/lib/brand-kit";
import { resolveBrandLogoUri } from "@/lib/brand";
import { cn } from "@/lib/utils";

type BrandKitStudioProps = {
  workspace: WorkspaceContext | null;
  value: WorkspaceSetupState;
  onChange: Dispatch<SetStateAction<WorkspaceSetupState>>;
};

type FontOptionView = {
  family: string;
  category: string;
  isCustom: boolean;
};

type ColorFieldProps = {
  description: string;
  label: string;
  suggestedColors: string[];
  value: string;
  onChange: (nextValue: string) => void;
};

function toUiErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function buildFontOptions(searchValue: string, selectedValue: string): FontOptionView[] {
  const normalizedSearch = searchValue.trim().toLowerCase();
  const filtered = GOOGLE_FONT_OPTIONS.filter((option) => {
    if (!normalizedSearch) {
      return true;
    }

    return (
      option.family.toLowerCase().includes(normalizedSearch) ||
      option.category.toLowerCase().includes(normalizedSearch)
    );
  }).map((option) => ({
    family: option.family,
    category: option.category,
    isCustom: false,
  }));

  const normalizedSelected = selectedValue.trim();
  if (
    normalizedSelected &&
    !isSupportedGoogleFontFamily(normalizedSelected) &&
    (!normalizedSearch || normalizedSelected.toLowerCase().includes(normalizedSearch))
  ) {
    return [
      {
        family: normalizedSelected,
        category: "Current / custom",
        isCustom: true,
      },
      ...filtered,
    ];
  }

  return filtered;
}

function FontPickerPanel({
  label,
  description,
  searchValue,
  selectedValue,
  onSearchChange,
  onSelect,
}: {
  label: string;
  description: string;
  searchValue: string;
  selectedValue: string;
  onSearchChange: (nextValue: string) => void;
  onSelect: (nextValue: string) => void;
}) {
  const options = useMemo(
    () => buildFontOptions(searchValue, selectedValue),
    [searchValue, selectedValue],
  );

  return (
    <div className="rounded-[1.5rem] border border-[color:var(--border)] bg-white/80 p-5 shadow-[0_16px_36px_rgba(16,38,60,0.05)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-foreground text-sm font-semibold">{label}</p>
          <p className="text-muted-foreground mt-1 max-w-sm text-xs leading-5">{description}</p>
        </div>
        <span className="bg-background/80 text-muted-foreground rounded-full border border-[color:var(--border)] px-3 py-1 text-[11px] tracking-[0.14em] uppercase">
          {options.length} fonts
        </span>
      </div>

      <label className="bg-background/90 text-muted-foreground mt-4 flex items-center gap-2 rounded-2xl border border-[color:var(--border)] px-3 py-2 text-sm">
        <Search className="h-4 w-4" />
        <input
          aria-label={`${label} font search`}
          className="text-foreground placeholder:text-muted-foreground w-full bg-transparent outline-none"
          placeholder="Search family or mood"
          value={searchValue}
          onChange={(event) => onSearchChange(event.target.value)}
        />
      </label>

      <div className="mt-4 grid max-h-80 gap-2 overflow-y-auto pr-1">
        {options.map((option) => {
          const selected = option.family === selectedValue;
          return (
            <button
              key={`${label}-${option.family}`}
              type="button"
              className={cn(
                "flex items-center justify-between gap-3 rounded-2xl border px-4 py-3 text-left transition-all",
                selected
                  ? "border-transparent bg-[color:rgba(15,157,122,0.12)] shadow-[inset_0_0_0_1px_rgba(15,157,122,0.28)]"
                  : "bg-background/80 border-[color:var(--border)] hover:-translate-y-px hover:border-[rgba(15,157,122,0.3)] hover:bg-white",
              )}
              onClick={() => onSelect(option.family)}
            >
              <div className="min-w-0">
                <p
                  className="text-foreground truncate text-base font-semibold"
                  style={{ fontFamily: `"${option.family}", "Inter", sans-serif` }}
                >
                  {option.family}
                </p>
                <p className="text-muted-foreground mt-1 text-xs">
                  {option.category}
                  {option.isCustom ? " • kept from current workspace" : ""}
                </p>
              </div>
              <div className="shrink-0 text-right">
                <span
                  className={cn(
                    "inline-flex rounded-full px-2.5 py-1 text-[11px] tracking-[0.12em] uppercase",
                    selected
                      ? "bg-[rgba(15,157,122,0.14)] text-[rgb(18,99,76)]"
                      : "text-muted-foreground bg-[rgba(16,38,60,0.06)]",
                  )}
                >
                  {selected ? "Selected" : "Pick"}
                </span>
                <p
                  className="text-muted-foreground mt-2 text-xs"
                  style={{ fontFamily: `"${option.family}", "Inter", sans-serif` }}
                >
                  Aa Bb Cc
                </p>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ColorField({ description, label, suggestedColors, value, onChange }: ColorFieldProps) {
  const normalizedValue = normalizeHexColor(value, "#f07f13");
  const [draftValue, setDraftValue] = useState(normalizedValue);

  useEffect(() => {
    setDraftValue(normalizedValue);
  }, [normalizedValue]);

  const tonalScale = useMemo(() => buildColorScale(normalizedValue), [normalizedValue]);
  const hueDetails = useMemo(() => hexToHsl(normalizedValue), [normalizedValue]);
  const contrastOnDark = useMemo(
    () => getContrastRatio(normalizedValue, "#10263c"),
    [normalizedValue],
  );
  const contrastOnLight = useMemo(
    () => getContrastRatio(normalizedValue, "#ffffff"),
    [normalizedValue],
  );
  const readableText = useMemo(() => pickReadableTextColor(normalizedValue), [normalizedValue]);
  const swatches = useMemo(
    () =>
      Array.from(
        new Set(
          [
            ...suggestedColors.map((item) => normalizeHexColor(item, normalizedValue)),
            ...tonalScale,
          ].filter(Boolean),
        ),
      ).slice(0, 8),
    [normalizedValue, suggestedColors, tonalScale],
  );

  function commit(nextValue: string) {
    const normalized = normalizeHexColor(nextValue, normalizedValue);
    setDraftValue(normalized);
    onChange(normalized);
  }

  return (
    <div className="rounded-[1.5rem] border border-[color:var(--border)] bg-white/84 p-5 shadow-[0_16px_36px_rgba(16,38,60,0.05)]">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div
            className="mt-0.5 h-11 w-11 shrink-0 rounded-2xl border border-white/70 shadow-[inset_0_1px_0_rgba(255,255,255,0.5)]"
            style={{ backgroundColor: normalizedValue }}
          />
          <div>
            <p className="text-foreground text-sm font-semibold">{label}</p>
            <p className="text-muted-foreground mt-1 max-w-xs text-xs leading-5">{description}</p>
          </div>
        </div>
        <div
          className="bg-background/80 rounded-full border border-[color:var(--border)] px-3 py-1 text-[11px] tracking-[0.12em] uppercase"
          style={{
            color: readableText,
          }}
        >
          {normalizedValue}
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_140px]">
        <label className="space-y-1 text-sm">
          <span className="text-muted-foreground">Hex value</span>
          <input
            aria-label={`${label} hex value`}
            className={cn(
              "bg-background/90 text-foreground w-full rounded-2xl border px-3 py-2.5 transition-colors outline-none",
              isValidHexColor(draftValue)
                ? "border-[color:var(--border)] focus:border-[rgba(15,157,122,0.4)]"
                : "border-amber-500/60 focus:border-amber-500",
            )}
            value={draftValue}
            onChange={(event) => {
              const nextValue = event.target.value;
              setDraftValue(nextValue);
              if (isValidHexColor(nextValue)) {
                onChange(normalizeHexColor(nextValue, normalizedValue));
              }
            }}
            onBlur={() => commit(draftValue)}
          />
        </label>
        <label
          className="relative flex min-h-[74px] cursor-pointer flex-col justify-between overflow-hidden rounded-[1.4rem] border border-[color:var(--border)] p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.5)]"
          style={{
            background: `linear-gradient(145deg, ${mixHexColors(normalizedValue, "#ffffff", 0.25)} 0%, ${normalizedValue} 100%)`,
          }}
        >
          <input
            aria-label={`${label} system color picker`}
            className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
            type="color"
            value={normalizedValue}
            onChange={(event) => commit(event.target.value)}
          />
          <div className="flex items-center justify-between text-[11px] tracking-[0.14em] text-white/84 uppercase">
            <span>System picker</span>
            <span>Live</span>
          </div>
          <p className="max-w-[9rem] text-xs text-white/92">Open the OS color selector.</p>
        </label>
      </div>

      <div className="mt-4 space-y-2">
        <p className="text-muted-foreground text-xs tracking-[0.12em] uppercase">Tone rail</p>
        <div className="grid grid-cols-5 gap-2">
          {tonalScale.map((tone) => (
            <button
              key={`${label}-${tone}`}
              type="button"
              aria-label={`${label} tone ${tone}`}
              className="h-10 rounded-2xl border border-white/60 shadow-[inset_0_1px_0_rgba(255,255,255,0.45)] transition-transform hover:-translate-y-px"
              style={{ backgroundColor: tone }}
              onClick={() => commit(tone)}
            />
          ))}
        </div>
      </div>

      <div className="mt-4 space-y-2">
        <p className="text-muted-foreground text-xs tracking-[0.12em] uppercase">
          Suggested swatches
        </p>
        <div className="flex flex-wrap gap-2">
          {swatches.map((swatch) => (
            <button
              key={`${label}-swatch-${swatch}`}
              type="button"
              aria-label={`${label} swatch ${swatch}`}
              className="h-9 w-9 rounded-full border border-white/70 shadow-[inset_0_1px_0_rgba(255,255,255,0.45)] transition-transform hover:-translate-y-px"
              style={{ backgroundColor: swatch }}
              onClick={() => commit(swatch)}
            />
          ))}
        </div>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-3">
        <div className="bg-background/70 rounded-2xl border border-[color:var(--border)] px-3 py-2">
          <p className="text-muted-foreground text-[11px] tracking-[0.12em] uppercase">Hue</p>
          <p className="text-foreground mt-1 text-sm font-semibold">{hueDetails.h}°</p>
        </div>
        <div className="bg-background/70 rounded-2xl border border-[color:var(--border)] px-3 py-2">
          <p className="text-muted-foreground text-[11px] tracking-[0.12em] uppercase">On dark</p>
          <p className="text-foreground mt-1 text-sm font-semibold">{contrastOnDark}:1</p>
        </div>
        <div className="bg-background/70 rounded-2xl border border-[color:var(--border)] px-3 py-2">
          <p className="text-muted-foreground text-[11px] tracking-[0.12em] uppercase">On white</p>
          <p className="text-foreground mt-1 text-sm font-semibold">{contrastOnLight}:1</p>
        </div>
      </div>
    </div>
  );
}

export function BrandKitStudio({ workspace, value, onChange }: BrandKitStudioProps) {
  const [headingSearch, setHeadingSearch] = useState("");
  const [bodySearch, setBodySearch] = useState("");
  const [logoUploadError, setLogoUploadError] = useState<string | null>(null);
  const [logoUploadNotice, setLogoUploadNotice] = useState<string | null>(null);
  const [localLogoPreviewUrl, setLocalLogoPreviewUrl] = useState<string | null>(null);
  const [isUploadingLogo, setIsUploadingLogo] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    return () => {
      if (localLogoPreviewUrl) {
        URL.revokeObjectURL(localLogoPreviewUrl);
      }
    };
  }, [localLogoPreviewUrl]);

  const googleFontsPreviewHref = useMemo(
    () => buildGoogleFontsStylesheetUrl([value.headingFont, value.bodyFont]),
    [value.bodyFont, value.headingFont],
  );

  useEffect(() => {
    const existingLink = document.head.querySelector<HTMLLinkElement>(
      'link[data-brand-kit-font-preview="true"]',
    );

    if (!googleFontsPreviewHref) {
      existingLink?.remove();
      return;
    }

    const link = existingLink ?? document.createElement("link");
    link.rel = "stylesheet";
    link.href = googleFontsPreviewHref;
    link.dataset.brandKitFontPreview = "true";
    if (!existingLink) {
      document.head.appendChild(link);
    }

    return () => {
      link.remove();
    };
  }, [googleFontsPreviewHref]);

  const previewLogoUri = localLogoPreviewUrl ?? resolveBrandLogoUri(value.logoUri);
  const previewBrandName = value.brandName.trim() || "Brand Studio";
  const previewTone = value.toneName.trim() || "executive clarity";
  const previewPrimary = normalizeHexColor(value.primaryColor, "#0f9d7a");
  const previewSecondary = normalizeHexColor(value.secondaryColor, "#16324f");
  const previewAccent = normalizeHexColor(value.accentColor, "#e0b941");
  const previewInk = pickReadableTextColor(previewPrimary, "#10263c", "#ffffff");
  const previewGradient = `linear-gradient(145deg, ${previewSecondary} 0%, ${mixHexColors(previewSecondary, previewPrimary, 0.28)} 48%, ${previewPrimary} 100%)`;
  const primarySuggestions = useMemo(
    () => BRAND_PALETTE_PRESETS.map((preset) => preset.primary),
    [],
  );
  const secondarySuggestions = useMemo(
    () => BRAND_PALETTE_PRESETS.map((preset) => preset.secondary),
    [],
  );
  const accentSuggestions = useMemo(() => BRAND_PALETTE_PRESETS.map((preset) => preset.accent), []);

  async function handleLogoSelection(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file) {
      return;
    }

    setLogoUploadError(null);
    setLogoUploadNotice(null);
    const nextLocalPreview = URL.createObjectURL(file);
    setLocalLogoPreviewUrl((previousValue) => {
      if (previousValue) {
        URL.revokeObjectURL(previousValue);
      }
      return nextLocalPreview;
    });

    setIsUploadingLogo(true);
    try {
      const payload = await uploadBrandKitLogo({
        tenantHeader: workspace?.tenantId ?? "dev-tenant",
        tenantId: workspace?.tenantId,
        projectId: workspace?.projectId,
        file,
      });
      onChange((previousValue) => ({
        ...previousValue,
        logoUri: payload.logo_uri,
      }));
      setLogoUploadNotice(`Logo stored as ${payload.logo_uri}`);
      setLocalLogoPreviewUrl((previousValue) => {
        if (previousValue) {
          URL.revokeObjectURL(previousValue);
        }
        return null;
      });
    } catch (error) {
      setLogoUploadError(toUiErrorMessage(error, "Logo upload failed."));
    } finally {
      setIsUploadingLogo(false);
    }
  }

  return (
    <div className="mt-4 space-y-5">
      <div className="grid gap-4 xl:grid-cols-12">
        <div
          className="relative overflow-hidden rounded-[1.85rem] border border-[rgba(255,255,255,0.18)] p-6 text-white shadow-[0_24px_60px_rgba(16,38,60,0.16)] xl:col-span-8"
          style={{ background: previewGradient }}
        >
          <div
            className="absolute top-0 -right-16 h-48 w-48 rounded-full blur-3xl"
            style={{ backgroundColor: mixHexColors(previewAccent, "#ffffff", 0.28), opacity: 0.48 }}
          />
          <div className="relative flex h-full flex-col gap-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="flex h-16 w-16 items-center justify-center overflow-hidden rounded-[1.35rem] border border-white/16 bg-white/10">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={previewLogoUri}
                    alt={`${previewBrandName} logo preview`}
                    className="h-12 w-12 object-contain"
                  />
                </div>
                <div>
                  <p className="text-[11px] tracking-[0.16em] text-white/70 uppercase">
                    Brand Preview
                  </p>
                  <h3
                    className="mt-1 text-2xl font-semibold tracking-[-0.03em]"
                    style={{ fontFamily: `"${value.headingFont}", "Inter", sans-serif` }}
                  >
                    {previewBrandName}
                  </h3>
                </div>
              </div>
              <span className="rounded-full border border-white/14 bg-white/10 px-3 py-1 text-[11px] tracking-[0.14em] text-white/80 uppercase">
                Tone {previewTone}
              </span>
            </div>

            <div className="max-w-2xl">
              <p className="text-[11px] tracking-[0.18em] text-white/68 uppercase">
                2025 report cover
              </p>
              <h4
                className="mt-3 text-[2rem] leading-[1.04] tracking-[-0.04em] sm:text-[2.35rem]"
                style={{ fontFamily: `"${value.headingFont}", "Inter", sans-serif` }}
              >
                Sustainability reporting identity tuned for board review and clean PDF output.
              </h4>
              <p
                className="mt-4 max-w-xl text-sm leading-7 text-white/88"
                style={{ fontFamily: `"${value.bodyFont}", "Inter", sans-serif` }}
              >
                Logo, palette, and typography choices are previewed in one place so the launchpad
                and the generated report stay visually consistent.
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              {[
                { label: "Heading", value: value.headingFont },
                { label: "Body", value: value.bodyFont },
                { label: "Readable ink", value: previewInk === "#ffffff" ? "White" : "Deep ink" },
              ].map((item) => (
                <div
                  key={item.label}
                  className="rounded-[1.2rem] border border-white/12 bg-black/12 px-4 py-3"
                >
                  <p className="text-[11px] tracking-[0.14em] text-white/62 uppercase">
                    {item.label}
                  </p>
                  <p className="mt-2 text-sm font-semibold text-white">{item.value}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="rounded-[1.85rem] border border-[color:var(--border)] bg-white/82 p-5 shadow-[0_16px_36px_rgba(16,38,60,0.05)] xl:col-span-4">
          <div className="space-y-4">
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Brand Name</span>
              <input
                aria-label="Workspace Brand Name"
                className="bg-background/90 text-foreground w-full rounded-2xl border border-[color:var(--border)] px-3 py-2.5 outline-none focus:border-[rgba(15,157,122,0.4)]"
                value={value.brandName}
                onChange={(event) =>
                  onChange((previousValue) => ({ ...previousValue, brandName: event.target.value }))
                }
              />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Tone / Narrative Style</span>
              <input
                aria-label="Workspace Tone Name"
                className="bg-background/90 text-foreground w-full rounded-2xl border border-[color:var(--border)] px-3 py-2.5 outline-none focus:border-[rgba(15,157,122,0.4)]"
                value={value.toneName}
                onChange={(event) =>
                  onChange((previousValue) => ({ ...previousValue, toneName: event.target.value }))
                }
              />
            </label>

            <div className="bg-background/75 rounded-[1.35rem] border border-[color:var(--border)] p-4">
              <p className="text-muted-foreground text-[11px] tracking-[0.14em] uppercase">
                Active palette
              </p>
              <div className="mt-3 space-y-3">
                {[
                  { label: "Primary", value: previewPrimary },
                  { label: "Secondary", value: previewSecondary },
                  { label: "Accent", value: previewAccent },
                ].map((item) => (
                  <div key={item.label} className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <span
                        className="h-8 w-8 rounded-full border border-white/70"
                        style={{ backgroundColor: item.value }}
                      />
                      <span className="text-foreground text-sm">{item.label}</span>
                    </div>
                    <span className="text-muted-foreground font-mono text-xs">{item.value}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
              <div className="bg-background/75 rounded-[1.2rem] border border-[color:var(--border)] px-4 py-3">
                <p className="text-muted-foreground text-[11px] tracking-[0.14em] uppercase">
                  Primary vs white
                </p>
                <p className="text-foreground mt-2 text-sm font-semibold">
                  {getContrastRatio(previewPrimary, "#ffffff")}:1
                </p>
              </div>
              <div className="bg-background/75 rounded-[1.2rem] border border-[color:var(--border)] px-4 py-3">
                <p className="text-muted-foreground text-[11px] tracking-[0.14em] uppercase">
                  Secondary vs white
                </p>
                <p className="text-foreground mt-2 text-sm font-semibold">
                  {getContrastRatio(previewSecondary, "#ffffff")}:1
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-[1.75rem] border border-[color:var(--border)] bg-white/80 p-4 shadow-[0_20px_48px_rgba(16,38,60,0.06)]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-foreground text-sm font-semibold">Logo Upload</p>
            <p className="text-muted-foreground mt-1 text-xs leading-5">
              Choose a logo directly from your PC. It is stored as a short local asset path so the
              launchpad and PDF renderer can reuse the same file.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploadingLogo}
            >
              {isUploadingLogo ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
              {isUploadingLogo ? "Uploading..." : "Choose Logo"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setLogoUploadError(null);
                setLogoUploadNotice(null);
                setLocalLogoPreviewUrl((previousValue) => {
                  if (previousValue) {
                    URL.revokeObjectURL(previousValue);
                  }
                  return null;
                });
                onChange((previousValue) => ({
                  ...previousValue,
                  logoUri: resolveBrandLogoUri(null),
                }));
              }}
            >
              Use Default Mark
            </Button>
          </div>
        </div>

        <input
          ref={fileInputRef}
          className="hidden"
          accept=".png,.jpg,.jpeg,.webp,.svg,image/png,image/jpeg,image/webp,image/svg+xml"
          type="file"
          onChange={handleLogoSelection}
        />

        <div className="mt-4 grid gap-4 xl:grid-cols-12">
          <div className="xl:col-span-3">
            <div className="flex min-h-[200px] items-center justify-center rounded-[1.6rem] border border-dashed border-[rgba(15,157,122,0.35)] bg-[linear-gradient(180deg,rgba(240,248,245,0.95),rgba(255,255,255,0.9))] p-4">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={previewLogoUri}
                alt={`${previewBrandName} uploaded logo`}
                className="max-h-28 w-full object-contain"
              />
            </div>
          </div>
          <div className="grid gap-3 xl:col-span-9 xl:grid-cols-2">
            <div className="bg-background/85 rounded-[1.3rem] border border-[color:var(--border)] px-4 py-3">
              <p className="text-muted-foreground text-[11px] tracking-[0.14em] uppercase">
                Stored logo path
              </p>
              <p className="text-foreground mt-2 font-mono text-sm break-all">{value.logoUri}</p>
            </div>
            <div className="bg-background/85 rounded-[1.3rem] border border-[color:var(--border)] px-4 py-3">
              <p className="text-muted-foreground text-[11px] tracking-[0.14em] uppercase">
                Usage notes
              </p>
              <ul className="text-muted-foreground mt-2 space-y-1.5 text-sm">
                <li>PNG, JPG, WEBP, or SVG supported</li>
                <li>Files stay under 5 MB</li>
                <li>Uploads use a local public path instead of base64</li>
              </ul>
            </div>
            {logoUploadNotice ? (
              <div className="flex items-start gap-2 rounded-[1.3rem] border border-emerald-500/25 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-700 xl:col-span-2">
                <Check className="mt-0.5 h-4 w-4 shrink-0" />
                <p>{logoUploadNotice}</p>
              </div>
            ) : null}
            {logoUploadError ? (
              <div className="border-destructive/35 bg-destructive/10 text-destructive rounded-[1.3rem] border px-4 py-3 text-sm xl:col-span-2">
                {logoUploadError}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <div className="rounded-[1.75rem] border border-[color:var(--border)] bg-white/80 p-4 shadow-[0_20px_48px_rgba(16,38,60,0.06)]">
        <div className="flex items-start gap-3">
          <Palette className="mt-0.5 h-5 w-5 text-[rgb(15,157,122)]" />
          <div>
            <p className="text-foreground text-sm font-semibold">Palette Studio</p>
            <p className="text-muted-foreground mt-1 text-xs leading-5">
              Start from a curated sustainability palette, then fine-tune primary, secondary, and
              accent colors with a richer control surface.
            </p>
          </div>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {BRAND_PALETTE_PRESETS.map((preset) => (
            <button
              key={preset.name}
              type="button"
              className="bg-background/85 rounded-[1.4rem] border border-[color:var(--border)] p-3 text-left transition-all hover:-translate-y-px hover:border-[rgba(15,157,122,0.3)] hover:bg-white"
              onClick={() =>
                onChange((previousValue) => ({
                  ...previousValue,
                  primaryColor: preset.primary,
                  secondaryColor: preset.secondary,
                  accentColor: preset.accent,
                }))
              }
            >
              <div className="flex items-center gap-2">
                {[preset.primary, preset.secondary, preset.accent].map((swatch) => (
                  <span
                    key={`${preset.name}-${swatch}`}
                    className="h-7 w-7 rounded-full border border-white/60"
                    style={{ backgroundColor: swatch }}
                  />
                ))}
              </div>
              <p className="text-foreground mt-3 text-sm font-semibold">{preset.name}</p>
              <p className="text-muted-foreground mt-1 text-xs leading-5">{preset.mood}</p>
            </button>
          ))}
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-12">
          <div className="xl:col-span-4">
            <ColorField
              label="Primary Color"
              description="Own the hero layer, charts, buttons, and section anchors."
              suggestedColors={primarySuggestions}
              value={value.primaryColor}
              onChange={(nextValue) =>
                onChange((previousValue) => ({ ...previousValue, primaryColor: nextValue }))
              }
            />
          </div>
          <div className="xl:col-span-4">
            <ColorField
              label="Secondary Color"
              description="Carry depth, contrast, and executive reading comfort."
              suggestedColors={secondarySuggestions}
              value={value.secondaryColor}
              onChange={(nextValue) =>
                onChange((previousValue) => ({ ...previousValue, secondaryColor: nextValue }))
              }
            />
          </div>
          <div className="xl:col-span-4">
            <ColorField
              label="Accent Color"
              description="Reserve for highlights, KPI flashes, and proof markers."
              suggestedColors={accentSuggestions}
              value={value.accentColor}
              onChange={(nextValue) =>
                onChange((previousValue) => ({ ...previousValue, accentColor: nextValue }))
              }
            />
          </div>
        </div>
      </div>

      <div className="rounded-[1.75rem] border border-[color:var(--border)] bg-white/80 p-4 shadow-[0_20px_48px_rgba(16,38,60,0.06)]">
        <div className="flex items-start gap-3">
          <Type className="mt-0.5 h-5 w-5 text-[rgb(15,157,122)]" />
          <div>
            <p className="text-foreground text-sm font-semibold">Typography Studio</p>
            <p className="text-muted-foreground mt-1 text-xs leading-5">
              Curated Google Fonts with search, pair presets, and live report preview styling.
            </p>
          </div>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {BRAND_FONT_PRESETS.map((preset) => (
            <button
              key={preset.name}
              type="button"
              className="bg-background/85 rounded-[1.4rem] border border-[color:var(--border)] p-3 text-left transition-all hover:-translate-y-px hover:border-[rgba(15,157,122,0.3)] hover:bg-white"
              onClick={() =>
                onChange((previousValue) => ({
                  ...previousValue,
                  headingFont: preset.heading,
                  bodyFont: preset.body,
                }))
              }
            >
              <p className="text-foreground text-sm font-semibold">{preset.name}</p>
              <p className="text-muted-foreground mt-1 text-xs leading-5">{preset.mood}</p>
              <div className="mt-3 rounded-[1.2rem] border border-[color:var(--border)] bg-white/70 px-3 py-2">
                <p className="text-muted-foreground text-[11px] tracking-[0.12em] uppercase">
                  Pair
                </p>
                <p className="text-foreground mt-1 text-sm">
                  {preset.heading} + {preset.body}
                </p>
              </div>
            </button>
          ))}
        </div>

        <div className="mt-4 rounded-[1.4rem] border border-[color:var(--border)] bg-[linear-gradient(180deg,rgba(242,248,246,0.82),rgba(255,255,255,0.82))] p-4">
          <p className="text-muted-foreground text-[11px] tracking-[0.14em] uppercase">
            Active typography
          </p>
          <p
            className="text-foreground mt-2 text-xl font-semibold tracking-[-0.02em]"
            style={{ fontFamily: `"${value.headingFont}", "Inter", sans-serif` }}
          >
            {value.headingFont} + {value.bodyFont}
          </p>
          <p
            className="text-muted-foreground mt-2 text-sm"
            style={{ fontFamily: `"${value.bodyFont}", "Inter", sans-serif` }}
          >
            {GOOGLE_FONT_OPTIONS.length} Google font choices are available for sustainability
            reports, from board-friendly sans families to more editorial serif sets.
          </p>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-12">
          <div className="xl:col-span-6">
            <FontPickerPanel
              label="Heading Font"
              description="Use a more distinctive face for cover titles, section heads, and chapter markers."
              searchValue={headingSearch}
              selectedValue={value.headingFont}
              onSearchChange={setHeadingSearch}
              onSelect={(nextValue) =>
                onChange((previousValue) => ({ ...previousValue, headingFont: nextValue }))
              }
            />
          </div>
          <div className="xl:col-span-6">
            <FontPickerPanel
              label="Body Font"
              description="Keep long paragraphs comfortable for audit, board, and PDF reading."
              searchValue={bodySearch}
              selectedValue={value.bodyFont}
              onSearchChange={setBodySearch}
              onSelect={(nextValue) =>
                onChange((previousValue) => ({ ...previousValue, bodyFont: nextValue }))
              }
            />
          </div>
        </div>
      </div>
    </div>
  );
}
