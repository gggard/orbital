import type { NextRequest } from "next/server";
import { forwardToControlPlane } from "@/lib/backend";

type Ctx = { params: Promise<{ path: string[] }> };

async function handler(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return forwardToControlPlane(req, "/webhooks", path);
}

export { handler as POST };
