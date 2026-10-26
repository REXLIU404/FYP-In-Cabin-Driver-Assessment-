import type { ScenarioManifest } from "../../../ai/src/scenarioTimeline";

/**
 * Load every frame of a scenario up front (plan Task 6), in manifest order, and
 * turn each into a data URL indexed by its manifest `n` - the exact table the
 * playback clock reads. One failed frame fails the whole load and names the file,
 * so the player never starts with a hole in the middle of the scenario.
 *
 * `btoa` + `Blob.arrayBuffer()` (not `FileReader`): both the browser and the node
 * test environment have them.
 */
export const preloadFrames = async (
  manifest: ScenarioManifest,
  fetchFrame: (file: string) => Promise<Blob>,
  onProgress: (done: number, total: number) => void,
): Promise<string[]> => {
  const urls: string[] = new Array(manifest.frames.length);
  let done = 0;
  for (const frame of manifest.frames) {
    const blob = await fetchFrame(frame.file).catch((error: unknown) => {
      throw new Error(
        `frame ${frame.file} could not be loaded: ${
          error instanceof Error ? error.message : String(error)
        }`,
      );
    });
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);
    urls[frame.n] = `data:${blob.type || "image/jpeg"};base64,${btoa(binary)}`;
    done += 1;
    onProgress(done, manifest.frames.length);
  }
  return urls;
};
