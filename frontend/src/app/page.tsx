import sceneAnalysis from "@/data/scene-analysis.example.json";
import { PawSpectiveShell } from "./PawSpectiveShell";
import type { SceneEvent } from "./types/sceneAnalysis";

export default function Home() {
  return (
    <PawSpectiveShell
      initialEvents={sceneAnalysis.events as SceneEvent[]}
    />
  );
}
