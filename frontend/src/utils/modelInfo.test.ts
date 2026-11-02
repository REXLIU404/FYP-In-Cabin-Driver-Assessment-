import { describe, expect, it } from "vitest";

import appSource from "../App.tsx?raw";
import { describeVisionModel } from "./modelInfo";

// Task 10A (correction C-5): the page names the vision model the backend actually loaded, read
// from /api/models, so a candidate run never shows a ResNet18 hash under "MobileNetV3".
describe("describeVisionModel: the loaded vision model in words", () => {
  it("the stable model", () => {
    expect(
      describeVisionModel({
        architecture: "mobilenet_v3_large",
        sha256: "b3a4",
        model_id: "stable_mobilenet_v3_large",
        run_id: null,
        source: "stable",
      }),
    ).toBe("mobilenet_v3_large (stable)");
  });

  it("a candidate names its model id", () => {
    expect(
      describeVisionModel({
        architecture: "resnet18",
        sha256: "5e22",
        model_id: "resnet18_search004_seed42",
        run_id: "p5_resnet18_search004_seed42_20261023",
        source: "candidate:p5_resnet18_search004_seed42_20261023",
      }),
    ).toBe("resnet18 · candidate resnet18_search004_seed42");
  });

  it("an older backend without an identity: the architecture alone, no guessed status", () => {
    expect(
      describeVisionModel({
        architecture: "mobilenet_v3_large",
        sha256: "b3a4",
      }),
    ).toBe("mobilenet_v3_large");
  });
});

describe("App shows the loaded vision model (source guard)", () => {
  it("uses describeVisionModel and no hard-coded architecture label", () => {
    expect(appSource).toMatch(/describeVisionModel\(live\.models\.vision\)/);
    expect(appSource).not.toMatch(/MobileNetV3:/);
  });
});
