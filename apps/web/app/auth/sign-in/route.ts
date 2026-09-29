import { NextRequest, NextResponse } from "next/server";

import {
  boundedForm,
  cookieOptions,
  csrfCookie,
  newCsrfToken,
  passwordSession,
  sessionCookie,
  validCsrf,
  validRequestOrigin,
  webConfiguration,
} from "../../../lib/supabase-auth";

export const dynamic = "force-dynamic";

export function GET() {
  const config = webConfiguration(process.env);
  const csrf = newCsrfToken();
  // All HTML is fixed presentation text except a generated lowercase hex nonce.
  const form = config
    ? `<form method="post" action="/auth/sign-in">
    <input type="hidden" name="csrf" value="${csrf}">
    <p><label>อีเมล <input name="email" type="email" maxlength="254" autocomplete="username" required></label></p>
    <p><label>รหัสผ่าน <input name="password" type="password" maxlength="1024" autocomplete="current-password" required></label></p>
    <button type="submit">เข้าสู่ระบบแบบอ่านอย่างเดียว</button></form>`
    : '<p role="status">ยังไม่ได้ตั้งค่าการเชื่อมต่อที่ปลอดภัย · not_configured</p>';
  const response = new NextResponse(
    `<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>เข้าสู่ระบบ · Aurum</title>
    <style nonce="${csrf}">:root{color-scheme:dark}body{margin:0;background:#101115;color:#eee;font:16px/1.7 Tahoma,sans-serif}main{max-width:36rem;margin:8vh auto;padding:2rem}h1,a{color:#e6c171}form{padding:1.5rem;border:1px solid #555;background:#191b21}label,input{display:block}input{box-sizing:border-box;width:100%;min-height:44px;padding:.5rem;border:1px solid #777;background:#101115;color:#fff;font:inherit}button{min-height:44px;padding:.5rem 1rem;background:#e6c171;color:#101115;border:0;font:inherit;cursor:pointer}a:focus,input:focus,button:focus{outline:3px solid #e6c171;outline-offset:3px}p{overflow-wrap:anywhere}@media(max-width:600px){main{margin:2vh auto;padding:1rem}}</style></head>
    <body><main><h1>Aurum · DEMO ONLY · SHADOW</h1><p>เข้าสู่ระบบด้วยบัญชี Supabase ที่ได้รับการจัดเตรียมแล้ว ไม่ใช่ข้อมูลรับรอง MT5</p>
    ${form}<p>แอปไม่บันทึกรหัสผ่านหรือโทเค็นใน localStorage ใช้เฉพาะคุกกี้เซสชันที่ป้องกันไว้ เมื่อหมดอายุต้องเข้าสู่ระบบใหม่</p><a href="/dashboard">กลับหน้าภาพรวม</a></main></body></html>`,
    {
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": `default-src 'none'; style-src 'nonce-${csrf}'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'`,
        "X-Content-Type-Options": "nosniff",
      },
    },
  );
  if (config)
    response.cookies.set(csrfCookie(config), csrf, cookieOptions(config, 3600));
  return response;
}

export async function POST(request: NextRequest) {
  const config = webConfiguration(process.env);
  const reject = () =>
    new NextResponse(
      "ไม่สามารถเข้าสู่ระบบได้ กรุณากลับไปหน้าเข้าสู่ระบบแล้วลองใหม่",
      {
        status: 400,
        headers: {
          "Cache-Control": "no-store",
          "Content-Type": "text/plain; charset=utf-8",
          "X-Content-Type-Options": "nosniff",
        },
      },
    );
  if (!config || !validRequestOrigin(request, config)) return reject();
  try {
    const form = await boundedForm(request);
    if (
      !form ||
      [...form.keys()].some(
        (key) => !["csrf", "email", "password"].includes(key),
      ) ||
      ["csrf", "email", "password"].some(
        (key) => form.getAll(key).length !== 1,
      ) ||
      !validCsrf(
        request,
        config,
        request.cookies.get(csrfCookie(config))?.value,
        form.get("csrf"),
      )
    )
      return reject();
    const session = await passwordSession(
      config,
      form.get("email") ?? "",
      form.get("password") ?? "",
    );
    const response = NextResponse.redirect(`${config.origin}/dashboard`, 303);
    response.headers.set("Cache-Control", "no-store");
    response.cookies.set(
      sessionCookie(config),
      session.token,
      cookieOptions(config, session.maxAge),
    );
    response.cookies.set(
      csrfCookie(config),
      newCsrfToken(),
      cookieOptions(config, session.maxAge),
    );
    return response;
  } catch {
    return reject();
  }
}
