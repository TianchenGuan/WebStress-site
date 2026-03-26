/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  transpilePackages: ["@webagentbench/shared", "@webagentbench/gmail"],
  images: { unoptimized: true },
};

module.exports = nextConfig;
