import type { NextConfig } from "next";

// API/webhook traffic is forwarded to the control plane by src/proxy.ts
// (runtime, per-request), so CONTROL_PLANE_URL can be set on the container.
const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
