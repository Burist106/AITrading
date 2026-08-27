import dynamic from "next/dynamic";

const DevelopmentOnlySimulator =
  process.env.NODE_ENV === "production"
    ? () => null
    : dynamic(() => import("./DevelopmentStateSimulator"));

export function StateSimulatorGate() {
  return <DevelopmentOnlySimulator />;
}
