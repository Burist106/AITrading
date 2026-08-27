import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  agentRules: false,
  reactStrictMode: true,
  transpilePackages: ["@aurum/contracts", "@aurum/fixtures"],
};

export default nextConfig;
