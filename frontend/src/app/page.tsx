import sceneAnalysis from "@/data/scene-analysis.example.json";
import {
  PawSpectiveShell,
  type SceneEvent,
} from "./PawSpectiveShell";

export default function Home() {
  return (
    <PawSpectiveShell
      initialEvents={sceneAnalysis.events as SceneEvent[]}
    />
  );
}