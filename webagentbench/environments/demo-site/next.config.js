/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  transpilePackages: ["@webagentbench/shared"],
  images: { unoptimized: true },
};

module.exports = nextConfig;
