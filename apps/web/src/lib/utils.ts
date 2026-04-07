// Bu yardimcilar, web tarafinda tekrar eden kucuk araclari tek yerde toplar.

import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
