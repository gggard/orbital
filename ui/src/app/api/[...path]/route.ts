import type { NextRequest } from "next/server";
import { forwardToControlPlane } from "@/lib/backend";

type Ctx = { params: Promise<{ path: string[] }> };

async function handler(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return forwardToControlPlane(req, "/api", path);
}

export {
  handler as GET,
  handler as POST,
  handler as PUT,
  handler as PATCH,
  handler as DELETE,
};
