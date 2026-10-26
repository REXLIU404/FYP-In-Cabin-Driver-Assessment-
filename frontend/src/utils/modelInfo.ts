import type { ModelStatus } from "../api/client";

/**
 * The vision model the backend loaded, in words (Task 10A). The backend picks it at start - the
 * stable MobileNetV3 or a manifest-driven candidate - and reports it in /api/models; the page only
 * repeats what it says. An older backend without `source` gets the architecture alone.
 */
export const describeVisionModel = (vision: ModelStatus["vision"]): string => {
  if (vision.source === undefined) return vision.architecture;
  if (vision.source === "stable") return `${vision.architecture} (stable)`;
  return `${vision.architecture} · candidate ${vision.model_id ?? "unknown"}`;
};
