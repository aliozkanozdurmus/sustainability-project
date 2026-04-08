// Bu yapilandirma, Next.js derleme ve calisma zamani davranisini ayarlar.

import type { NextConfig } from "next";
import { loadRootEnv } from "./src/lib/load-root-env.mjs";

loadRootEnv();

const nextConfig: NextConfig = {
  /* config options here */
};

export default nextConfig;
