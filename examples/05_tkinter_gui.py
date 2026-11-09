#!/usr/bin/env python3
"""
Example 5: Visual Desktop GUI Application (Tkinter)
Provides an interactive GUI with live preview of fingerprint scans,
quality metrics, visual enrollment, and 1:1 verification feedback.
"""

import sys
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import ImageTk, Image

from dp4500 import UareU4500, ReaderManager, FingerprintTemplate, FingerprintImage
from dp4500.backends.mock import MockBackend


class FingerprintApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DigitalPersona U.are.U 4500 - Biometric Console")
        self.geometry("520x680")
        self.resizable(False, False)

        self.enrolled_template = None
        self.last_image = None
        self.backend = MockBackend() if "--mock" in sys.argv else None

        self._build_ui()
        self._check_hardware()

    def _build_ui(self):
        # Header
        header = ttk.Frame(self, padding=12)
        header.pack(fill=tk.X)
        title_lbl = ttk.Label(
            header,
            text="DigitalPersona 4500 Biometric Console",
            font=("Helvetica", 14, "bold"),
        )
        title_lbl.pack(anchor=tk.W)

        self.device_lbl = ttk.Label(header, text="Detecting reader...", foreground="#666")
        self.device_lbl.pack(anchor=tk.W)

        # Image Display Canvas
        img_frame = ttk.LabelFrame(self, text=" Sensor Preview (500 DPI) ", padding=10)
        img_frame.pack(padx=16, pady=8, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(img_frame, width=290, height=384, bg="#1e1e1e", highlightthickness=1)
        self.canvas.pack(pady=4)

        self.info_lbl = ttk.Label(img_frame, text="Ready. Place finger on sensor.", font=("Helvetica", 10))
        self.info_lbl.pack(pady=4)

        # Controls
        ctrl_frame = ttk.Frame(self, padding=12)
        ctrl_frame.pack(fill=tk.X)

        btn_row = ttk.Frame(ctrl_frame)
        btn_row.pack(fill=tk.X, pady=4)

        self.btn_capture = ttk.Button(btn_row, text="📸 Capture Scan", command=self.on_capture)
        self.btn_capture.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)

        self.btn_enroll = ttk.Button(btn_row, text="📝 Enroll User", command=self.on_enroll)
        self.btn_enroll.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)

        self.btn_verify = ttk.Button(btn_row, text="🔐 Verify Finger", command=self.on_verify)
        self.btn_verify.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)

        # Status Bar
        self.status_var = tk.StringVar(value="Status: Idle")
        status_bar = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=4)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _check_hardware(self):
        try:
            with UareU4500(backend=self.backend) as reader:
                self.device_lbl.config(
                    text=f"Connected: {reader.name} | Driver: {reader.driver} ({reader.backend.backend_name()})"
                )
        except Exception as e:
            self.device_lbl.config(
                text=f"No hardware reader connected (Run with --mock for simulation)",
                foreground="#d9534f",
            )

    def _display_image(self, fp_image: FingerprintImage):
        self.last_image = fp_image
        pil_img = fp_image.to_pil()
        # Scale to fit canvas if needed
        tk_img = ImageTk.PhotoImage(pil_img)
        self.canvas.image = tk_img
        self.canvas.create_image(145, 192, image=tk_img)
        self.info_lbl.config(
            text=f"Dimensions: {fp_image.width}x{fp_image.height} | Quality: {fp_image.quality_score}%"
        )

    def on_capture(self):
        self.status_var.set("Status: Waiting for finger on sensor...")
        self.btn_capture.config(state=tk.DISABLED)

        def worker():
            try:
                with UareU4500(backend=self.backend) as reader:
                    img = reader.capture(wait_for_finger=True)
                    self.after(0, lambda: self._display_image(img))
                    self.after(0, lambda: self.status_var.set("Status: Fingerprint captured."))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Capture Error", str(e)))
                self.after(0, lambda: self.status_var.set("Status: Capture failed."))
            finally:
                self.after(0, lambda: self.btn_capture.config(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=True).start()

    def on_enroll(self):
        self.status_var.set("Status: Enrolling user (5 touches)...")
        self.btn_enroll.config(state=tk.DISABLED)

        def worker():
            try:
                def progress(completed, total):
                    self.after(0, lambda: self.status_var.set(f"Enrollment Touch {completed}/{total}..."))

                with UareU4500(backend=self.backend) as reader:
                    tpl = reader.enroll(stages=5, on_stage_progress=progress, username="User 1")
                    self.enrolled_template = tpl
                    # Capture one final image for display
                    img = reader.capture(wait_for_finger=False)
                    self.after(0, lambda: self._display_image(img))
                    self.after(0, lambda: messagebox.showinfo("Enrollment", "Fingerprint successfully enrolled!"))
                    self.after(0, lambda: self.status_var.set("Status: User enrolled."))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Enrollment Error", str(e)))
                self.after(0, lambda: self.status_var.set("Status: Enrollment failed."))
            finally:
                self.after(0, lambda: self.btn_enroll.config(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=True).start()

    def on_verify(self):
        if not self.enrolled_template:
            messagebox.showwarning("Verify", "Please enroll a fingerprint first!")
            return

        self.status_var.set("Status: Place finger on sensor to verify...")
        self.btn_verify.config(state=tk.DISABLED)

        def worker():
            try:
                with UareU4500(backend=self.backend) as reader:
                    res = reader.verify(self.enrolled_template)
                    if res.matched:
                        self.after(0, lambda: messagebox.showinfo("Verification", f"MATCH! Verified (Score: {res.score:.2f})"))
                        self.after(0, lambda: self.status_var.set(f"Status: Verified (Score {res.score:.2f})"))
                    else:
                        self.after(0, lambda: messagebox.showwarning("Verification", f"NO MATCH! (Score: {res.score:.2f})"))
                        self.after(0, lambda: self.status_var.set("Status: Verification failed."))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Verification Error", str(e)))
                self.after(0, lambda: self.status_var.set("Status: Verification error."))
            finally:
                self.after(0, lambda: self.btn_verify.config(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    app = FingerprintApp()
    app.mainloop()
