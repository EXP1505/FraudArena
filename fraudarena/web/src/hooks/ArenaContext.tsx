import { createContext, useContext, type ReactNode } from "react";
import { useArena, type ArenaData } from "./useArena";

const Ctx = createContext<ArenaData | null>(null);

export function ArenaProvider({ children }: { children: ReactNode }) {
  const data = useArena(2000);
  return <Ctx.Provider value={data}>{children}</Ctx.Provider>;
}

export function useArenaData(): ArenaData {
  const v = useContext(Ctx);
  if (!v) throw new Error("useArenaData must be used inside <ArenaProvider>");
  return v;
}
