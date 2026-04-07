// Bu API yardimcisi, contracts akisindaki istemci davranisini toplar.

import type { paths } from "@sustainability/shared-types";

export type HealthLiveResponse =
  paths["/health/live"]["get"]["responses"]["200"]["content"]["application/json"];

export type HealthReadyResponse =
  paths["/health/ready"]["get"]["responses"]["200"]["content"]["application/json"];

