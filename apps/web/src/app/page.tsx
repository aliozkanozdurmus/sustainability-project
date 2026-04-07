// Bu sayfa, urunun ilk karsilama ve yonlendirme deneyimini sunar.

import { redirect } from "next/navigation";

export default function HomePage() {
  redirect("/dashboard");
}
