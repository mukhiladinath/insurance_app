import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    resolveAlias: {
      // Force the browser UMD build — the default resolves to jspdf.node.min.js
      // which pulls in fflate/lib/node.cjs (uses Node.js Worker) and breaks Turbopack.
      jspdf: 'jspdf/dist/jspdf.umd.min.js',
    },
  },
};

export default nextConfig;
