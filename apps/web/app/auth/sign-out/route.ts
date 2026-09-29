import { NextRequest, NextResponse } from "next/server";

import {
  boundedForm,
  cookieOptions,
  csrfCookie,
  sessionCookie,
  validCsrf,
  validRequestOrigin,
  webConfiguration,
} from "../../../lib/supabase-auth";

export async function POST(request: NextRequest) {
  const config = webConfiguration(process.env);
  if (!config || !validRequestOrigin(request, config))
    return new NextResponse("คำขอไม่ถูกต้อง", {
      status: 400,
      headers: { "Cache-Control": "no-store" },
    });
  try {
    const form = await boundedForm(request);
    if (
      !config ||
      !form ||
      [...form.keys()].some((key) => key !== "csrf") ||
      form.getAll("csrf").length !== 1 ||
      !validCsrf(
        request,
        config,
        request.cookies.get(csrfCookie(config))?.value,
        form.get("csrf"),
      )
    ) {
      return new NextResponse("คำขอไม่ถูกต้อง", {
        status: 400,
        headers: { "Cache-Control": "no-store" },
      });
    }
    // Only this browser session is cleared; no account-wide session mutation.
    const response = NextResponse.redirect(
      `${config.origin}/auth/sign-in`,
      303,
    );
    response.headers.set("Cache-Control", "no-store");
    response.cookies.set(sessionCookie(config), "", cookieOptions(config, 0));
    response.cookies.set(csrfCookie(config), "", cookieOptions(config, 0));
    return response;
  } catch {
    return new NextResponse("คำขอไม่ถูกต้อง", {
      status: 400,
      headers: { "Cache-Control": "no-store" },
    });
  }
}
