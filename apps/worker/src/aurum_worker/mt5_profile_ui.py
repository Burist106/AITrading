"""Local-only manual confirmation UI. Never automated or browser-accessible."""

from __future__ import annotations

import io
import tkinter as tk
from contextlib import redirect_stdout
from functools import partial
from tkinter import filedialog, messagebox, ttk

from aurum_worker.local_mt5_profile import ProfileStore, reject_binding_environment
from aurum_worker.models.mt5 import (
    AccountObservation,
    BrokerSymbolCandidate,
    BrokerSymbolObservation,
)
from aurum_worker.mt5_profile_cli import run_saved, safe_reason
from aurum_worker.mt5_profile_setup import setup_profile


class LocalSetupDialogs:
    def __init__(self, parent: tk.Tk) -> None:
        self.parent = parent

    def confirm_replace(self) -> bool:
        return messagebox.askyesno(
            "ยืนยันการตั้งค่าใหม่",
            "มีโปรไฟล์เดิมอยู่แล้ว ต้องการตั้งค่าและยืนยันใหม่หรือไม่?\n"
            "โปรไฟล์เดิมจะคงอยู่หากยกเลิกหรือการตรวจไม่ผ่าน",
            parent=self.parent,
            default=messagebox.NO,
        )

    def choose_terminal(self) -> str | None:
        value = filedialog.askopenfilename(
            parent=self.parent,
            title="เลือก terminal64.exe ของ MT5 Demo ที่คุณเปิดอยู่",
            filetypes=[("MetaTrader 5 Terminal", "terminal64.exe")],
        )
        return value or None

    def confirm_account(self, account: AccountObservation) -> bool:
        return messagebox.askyesno(
            "ขั้นที่ 1: ยืนยันบัญชี Demo",
            f"บัญชี: {account.masked_login}\nเซิร์ฟเวอร์: {account.masked_server}\n"
            "ประเภท: DEMO\n\nเทียบกับบัญชีที่คุณเปิดใน MT5 ด้วยตัวเอง\n"
            "ยืนยันว่าบัญชีนี้คือบัญชี Demo ที่ต้องการจดจำหรือไม่?\n"
            "ไม่ต้องคัดลอก fingerprint และไม่ต้องกรอกรหัสผ่าน",
            parent=self.parent,
            default=messagebox.NO,
        )

    def choose_symbol(self, candidates: list[BrokerSymbolCandidate]) -> str | None:
        window = tk.Toplevel(self.parent)
        window.title("ขั้นที่ 2: เลือก XAU/USD ที่ต้องการ")
        window.geometry("560x330")
        window.transient(self.parent)
        ttk.Label(
            window, text="คลิกเลือก symbol ที่คุณต้องการ (แสดงเฉพาะ XAU/USD ที่มองเห็น)"
        ).pack(padx=16, pady=12)
        choices = tk.Listbox(window, exportselection=False, height=9)
        for candidate in candidates:
            choices.insert(tk.END, candidate.broker_symbol)
        choices.pack(fill=tk.BOTH, expand=True, padx=16)
        selected: str | None = None

        def accept() -> None:
            nonlocal selected
            indexes = choices.curselection()
            if indexes:
                selected = candidates[indexes[0]].broker_symbol
                window.destroy()

        buttons = ttk.Frame(window)
        buttons.pack(pady=14)
        ttk.Button(buttons, text="ยืนยัน symbol ที่เลือก", command=accept).pack(
            side=tk.LEFT, padx=8
        )
        ttk.Button(buttons, text="ยกเลิก", command=window.destroy).pack(side=tk.LEFT)
        window.grab_set()
        self.parent.wait_window(window)
        return selected

    def confirm_specification(self, specification: BrokerSymbolObservation) -> bool:
        # Explicit allowlist: never stringify the whole model or raw native structure.
        rows = (
            ("Symbol", specification.broker_symbol),
            ("Canonical", specification.canonical_symbol),
            (
                "Base / Profit / Margin",
                f"{specification.base_currency} / {specification.profit_currency} / "
                f"{specification.margin_currency}",
            ),
            ("Digits / Point", f"{specification.digits} / {specification.point}"),
            ("Tick size", specification.tick_size),
            ("Tick value", specification.tick_value),
            (
                "Tick value profit / loss",
                f"{specification.tick_value_profit} / {specification.tick_value_loss}",
            ),
            ("Contract size", specification.contract_size),
            (
                "Minimum / Maximum volume",
                f"{specification.minimum_volume} / {specification.maximum_volume}",
            ),
            ("Volume step", specification.volume_step),
            (
                "Stops / Freeze level",
                f"{specification.stops_level} / {specification.freeze_level}",
            ),
            ("Calculation mode", specification.trade_calculation_mode),
            ("Trade mode", specification.trade_mode.value),
            ("Filling mode", specification.filling_mode),
            ("Usability", specification.usability_state.value),
        )
        details = "\n".join(f"{label}: {value}" for label, value in rows)
        return messagebox.askyesno(
            "ขั้นที่ 3: ตรวจและยืนยันสเปกแยกจากบัญชี",
            details + "\n\nตรวจสเปกด้านบนแล้ว ยืนยันให้จดจำสเปกนี้หรือไม่?\n"
            "หากสเปกเปลี่ยน ระบบจะหยุดและขอให้ยืนยันใหม่\n"
            "การยืนยันนี้ไม่ใช่การผ่าน smoke และไม่อนุญาตให้เทรด",
            parent=self.parent,
            default=messagebox.NO,
        )


def open_profile_window() -> int:
    root = tk.Tk()
    root.title("Aurum — Local Demo Profile")
    root.geometry("720x480")
    root.minsize(720, 480)
    root.option_add("*Font", ("Leelawadee UI", 12))
    style = ttk.Style(root)
    style.configure(".", font=("Leelawadee UI", 12))
    style.configure("TButton", padding=(12, 8))
    frame = ttk.Frame(root, padding=24)
    frame.pack(fill=tk.BOTH, expand=True)
    ttk.Label(
        frame, text="Aurum • DEMO ONLY / SHADOW", font=("Leelawadee UI", 17, "bold")
    ).pack(anchor=tk.W)
    ttk.Label(
        frame, text="จำบัญชีที่คุณยืนยัน • ไม่เก็บรหัสผ่าน • ไม่มีคำสั่งซื้อขาย", wraplength=660
    ).pack(anchor=tk.W, pady=(8, 16))
    status = tk.StringVar(value="ตั้งค่าครั้งแรกหนึ่งครั้ง แล้วใช้ปุ่มตรวจสอบได้หลังเปิดเครื่องใหม่")
    buttons: list[ttk.Button] = []

    def action(name: str) -> None:
        for button in buttons:
            button.state(["disabled"])
        status.set("กำลังตรวจแบบ read-only…")
        root.update_idletasks()
        try:
            if name == "setup":
                reject_binding_environment()
                setup_profile(ProfileStore(), LocalSetupDialogs(root))
                status.set("บันทึกโปรไฟล์เข้ารหัสแล้ว — รอบถัดไปไม่ต้องกรอก fingerprint")
                messagebox.showinfo(
                    "บันทึกแล้ว",
                    "จำบัญชีและสเปกที่ยืนยันแล้ว\nยังไม่ได้รัน smoke และไม่ได้ส่งคำสั่งซื้อขาย",
                    parent=root,
                )
            else:
                output = io.StringIO()
                with redirect_stdout(output):
                    code = run_saved(name)
                details = output.getvalue().strip()
                status.set(
                    "ตรวจเสร็จแล้ว — อ่านผลด้านล่าง"
                    if code == 0
                    else "หยุดตามด่านความปลอดภัย — ดูรหัสเหตุผล"
                )
                if code == 0:
                    messagebox.showinfo(
                        "ผล read-only — ไม่ใช่ smoke", details, parent=root
                    )
                else:
                    messagebox.showwarning(
                        "ยังดำเนินการต่อไม่ได้",
                        details + "\n\nหากยังไม่มีโปรไฟล์ ให้กดตั้งค่าครั้งแรก\n"
                        "หากบัญชีหรือสเปกเปลี่ยน ต้องตรวจและยืนยันใหม่ด้วยตัวเอง",
                        parent=root,
                    )
        except Exception as error:
            status.set("ยังยืนยันผลการตั้งค่าไม่ได้ — ดูรหัสเหตุผลก่อนลองใหม่")
            messagebox.showwarning("หยุดการตั้งค่า", safe_reason(error), parent=root)
        finally:
            for button in buttons:
                button.state(["!disabled"])

    for label, name in (
        ("ตั้งค่าครั้งแรก / ยืนยันค่าใหม่", "setup"),
        ("ตรวจบัญชีและสเปกที่จดจำไว้", "check"),
        ("ตรวจเวลา tick (diagnostic เท่านั้น)", "tick-time"),
    ):
        button = ttk.Button(frame, text=label, command=partial(action, name))
        button.pack(fill=tk.X, pady=5)
        buttons.append(button)
    ttk.Label(frame, textvariable=status, wraplength=660).pack(
        anchor=tk.W, pady=(18, 8)
    )
    ttk.Label(
        frame,
        text="เปิด MT5 และเลือกบัญชี Demo ด้วยตัวเองก่อน • ไม่มีการรันอัตโนมัติเมื่อเปิดหน้าต่าง",
        wraplength=660,
    ).pack(anchor=tk.W)
    root.mainloop()
    return 0
