# Aurum Console — Codex Starter Pack

ชุดนี้เตรียมไว้สำหรับเริ่มพัฒนา **Aurum Console** ด้วย Codex โดยใช้ดีไซน์จาก Claude เป็น Visual and Behavioral Specification

## วิธีใช้

### Codex แบบ Local / CLI

1. สร้างโฟลเดอร์โปรเจกต์หรือ Private GitHub repository ใหม่
2. แตก ZIP นี้ไว้ที่ root ของโปรเจกต์
3. เปิดโฟลเดอร์นั้นด้วย Codex
4. วางข้อความทั้งหมดจาก `CODEX_START_PROMPT.md`
5. ให้ Codex ทำเฉพาะ Bootstrap Milestone ตาม Prompt ก่อน
6. ตรวจผล, tests และ git diff ก่อนสั่ง Milestone ถัดไป

### Codex ในหน้า ChatGPT / Cloud Workspace

1. อัปโหลด ZIP นี้ให้ Codex
2. วางข้อความจาก `CODEX_START_PROMPT.md`
3. ระบุให้ Codexแตกไฟล์และใช้โฟลเดอร์ที่แตกเป็น workspace
4. ตรวจว่า Codexอ่าน `AGENTS.md` และไฟล์ใน `docs/design-reference/` ก่อนเริ่มแก้ไฟล์

## ขอบเขตที่ล็อกแล้ว

- Environment: `DEMO ONLY`
- Asset: `XAU/USD ONLY`
- Initial runtime mode: `SHADOW`
- Maximum permitted volume: `0.01`
- Maximum open positions: `1`
- Mandatory Stop Loss
- No martingale
- No grid trading
- No averaging down
- No loss-based volume increases
- No hard-risk override
- No live-account execution
- Supabase is the control plane
- Windows Python MT5 Worker is the execution plane

## สิ่งที่ยังไม่ต้องเตรียมใน Bootstrap Milestone

อย่าใส่ credential จริงใน workspace และยังไม่ต้องให้ Codexเข้าถึง:

- MT5 login/password/server
- Supabase secret or Worker credential
- LINE channel secret/access token
- OpenAI API key
- บัญชี Live

สร้างได้เพียง `.env.example` ที่มีชื่อ Variable โดยไม่มีค่าจริง

## ไฟล์สำคัญ

- `CODEX_START_PROMPT.md` — Prompt แรกที่ต้องวางให้ Codex
- `AGENTS.md` — กฎที่ Codex ต้องปฏิบัติตลอดโปรเจกต์
- `docs/IMPLEMENTATION_ROADMAP.md` — ลำดับการพัฒนา
- `docs/P0_ACCEPTANCE_GATES.md` — Gate ก่อนเพิ่มความสามารถที่เสี่ยง
- `docs/design-reference/` — Prototype และ Handoff จาก Claude

## หลักสำคัญ

ไฟล์ `.dc.html` เป็นเพียง Design Reference ห้ามนำไป Copy เป็น Production Component ขนาดใหญ่โดยตรง และ `support.js` หรือไฟล์ใน `_ds/` ห้ามนำไปใช้เป็น Production Runtime
