import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { basename, resolve } from "node:path";

const apiBase = process.env.PAWSPECTIVE_E2E_API_URL ?? "http://localhost:8000";
const fullJourneyEnabled = process.env.PAWSPECTIVE_E2E_FULL_JOURNEY === "1";
const fixturePath = process.env.PAWSPECTIVE_E2E_VIDEO_PATH;

test.describe("built production containers", () => {
  test("serves the frontend and reaches backend readiness through browser CORS", async ({ page }) => {
    const response = await page.goto("/");
    expect(response?.ok()).toBe(true);
    await expect(
      page.getByRole("heading", {
        name: /Meet the world from a slightly more dog-shaped perspective/i,
      }),
    ).toBeVisible();

    const result = await page.evaluate(async (origin) => {
      const ready = await fetch(`${origin}/api/v1/health/ready`);
      return {
        readyStatus: ready.status,
        readyBody: await ready.json(),
      };
    }, apiBase);

    expect(result.readyStatus).toBe(200);
    expect(result.readyBody.status).toBe("ready");
  });

  test("reports a representative invalid upload without exposing server paths", async ({ page }) => {
    await page.goto("/");
    const result = await page.evaluate(async (origin) => {
      const form = new FormData();
      form.append("file", new File(["not video"], "invalid.txt", { type: "text/plain" }));
      const response = await fetch(`${origin}/api/v1/analyze-video`, { method: "POST", body: form });
      return { status: response.status, body: await response.text() };
    }, apiBase);
    expect(result.status).toBe(415);
    expect(result.body).toContain("Unsupported video type");
    expect(result.body).not.toMatch(/(?:[A-Za-z]:\\|\/app\/|\/tmp\/)/);
  });

  test("full upload-to-download release journey scaffold", async ({ page }) => {
    test.skip(
      !fullJourneyEnabled || !fixturePath,
      "Set PAWSPECTIVE_E2E_FULL_JOURNEY=1 and PAWSPECTIVE_E2E_VIDEO_PATH to a declared 5–15 second fixture with media-bound analysis.",
    );

    const absoluteFixture = resolve(fixturePath!);
    const fixtureBytes = readFileSync(absoluteFixture).toString("base64");
    const fixtureName = basename(absoluteFixture);
    await page.goto("/");

    const result = await page.evaluate(
      async ({ origin, bytes, name }) => {
        const binary = Uint8Array.from(atob(bytes), (character) => character.charCodeAt(0));
        const file = new File([binary], name, { type: "video/mp4" });
        const postFile = async (path: string, payload?: unknown) => {
          const form = new FormData();
          form.append("file", file, file.name);
          if (payload !== undefined) form.append("payload", JSON.stringify(payload));
          const response = await fetch(`${origin}${path}`, { method: "POST", body: form });
          if (!response.ok) throw new Error(`${path} returned ${response.status}: ${await response.text()}`);
          return response.json();
        };

        const analysis = await postFile("/api/v1/analyze-video") as {
          source: "gemini" | "demo" | "controlled_demo";
          analysis: { events: Array<Record<string, unknown> & { event_id: string; object_label: string }> };
        };
        if (analysis.source === "demo") {
          throw new Error("The full release journey requires media-bound gemini or controlled_demo analysis, not generic fallback data.");
        }
        if (analysis.analysis.events.length === 0) throw new Error("The fixture produced no visible events.");

        const correctedEvents = analysis.analysis.events.map((event, index) =>
          index === 0 ? { ...event, object_label: event.object_label.trim() } : event,
        );
        const visibility = await postFile("/api/v1/score-visibility", {
          analysis_source: analysis.source,
          events: correctedEvents,
          favorite_interest: "Toys",
        }) as { scores: Array<Record<string, unknown> & { event_id: string }> };
        if (visibility.scores.length === 0) throw new Error("Visibility scoring produced no scores.");

        const color = await postFile("/api/v1/simulate-object-colors", {
          analysis_source: analysis.source,
          event: correctedEvents[0],
        }) as { options: unknown[] };
        if (color.options.length !== 6) throw new Error("Color simulation did not return the fixed six-color palette.");

        const created = await postFile("/api/v1/story-jobs", {
          analysis_source: analysis.source,
          style: "nature_documentary",
          variation_id: "e2e-original",
          animation_seed: 0,
          profile: {
            owner_name: "E2E Owner",
            dog_name: "E2E Dog",
            breed: "Test mix",
            age: "Adult",
            size: "Medium",
            personality_tags: ["Curious"],
            favorite_interest: "Toys",
          },
          events: correctedEvents,
          scores: visibility.scores,
          featured_event_id: visibility.scores[0].event_id,
        }) as { status_url: string };

        let status: { status: string; error: string | null; download_url: string | null } | undefined;
        for (let attempt = 0; attempt < 120; attempt += 1) {
          const response = await fetch(`${origin}${created.status_url}`, { cache: "no-store" });
          if (!response.ok) throw new Error(`Story status returned ${response.status}`);
          status = await response.json();
          if (["completed", "failed", "cancelled", "expired"].includes(status!.status)) break;
          await new Promise((resolveDelay) => setTimeout(resolveDelay, 1_000));
        }
        if (status?.status !== "completed" || !status.download_url) {
          throw new Error(`Story did not complete: ${status?.status ?? "poll timeout"}: ${status?.error ?? "no detail"}`);
        }
        const download = await fetch(`${origin}${status.download_url}`, { cache: "no-store" });
        if (!download.ok) throw new Error(`Story download returned ${download.status}`);
        const artifact = await download.blob();
        return {
          analysisSource: analysis.source,
          eventCount: correctedEvents.length,
          scoreCount: visibility.scores.length,
          colorCount: color.options.length,
          storyStatus: status.status,
          artifactType: artifact.type,
          artifactBytes: artifact.size,
        };
      },
      { origin: apiBase, bytes: fixtureBytes, name: fixtureName },
    );

    expect(result.eventCount).toBeGreaterThan(0);
    expect(result.scoreCount).toBeGreaterThan(0);
    expect(result.colorCount).toBe(6);
    expect(result.storyStatus).toBe("completed");
    expect(result.artifactType).toContain("video/mp4");
    expect(result.artifactBytes).toBeGreaterThan(0);
  });

  test("deliberate failure retains screenshot, trace, and video", async ({ page }, testInfo) => {
    test.skip(process.env.PAWSPECTIVE_E2E_ARTIFACT_SMOKE !== "1", "Opt-in proof for failure artifact handling.");
    await page.goto("/");
    await page.screenshot({ path: testInfo.outputPath("before-deliberate-failure.png"), fullPage: true });
    await expect(page.getByRole("heading", { name: "INTENTIONAL E2E FAILURE" })).toBeVisible();
  });
});
