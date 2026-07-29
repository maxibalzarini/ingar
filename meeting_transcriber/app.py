from __future__ import annotations

import argparse
import base64
import html
import json
import math
import multiprocessing as mp
import os
import queue
import re
import subprocess
import sys
import threading
import time
import traceback
import wave
import webbrowser
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import tkinter as tk
from tkinter import messagebox, ttk

APP_NAME = "INGAR Meeting Transcriber"
APP_VERSION = "1.4.2"
SOURCE_ROOT = Path(__file__).resolve().parent
ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else SOURCE_ROOT
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT))
ASSETS = BUNDLE_ROOT / "assets"
SESSIONS = ROOT / "sessions"
MODELS = ROOT / "models"
LOGS = ROOT / "logs"
CONFIG = ROOT / "config.json"
for folder in (SESSIONS, MODELS, LOGS):
    folder.mkdir(parents=True, exist_ok=True)

LANGUAGES = {"Automático": None, "Español": "es", "English": "en", "Português": "pt"}
MODELS_MAP = {"Base — rápido": "base", "Small — recomendado": "small", "Medium — precisión": "medium"}
NAVY, BLUE, INK, MUTED, LIGHT, WHITE, RED = "#173650", "#0878B9", "#263943", "#667985", "#F4F7F8", "#FFFFFF", "#A53A32"


def log_error(name: str, exc: BaseException) -> None:
    text = f"{datetime.now().isoformat()}\n{name}: {exc}\n\n{traceback.format_exc()}"
    try:
        (LOGS / f"{name}.log").write_text(text, encoding="utf-8")
    except Exception:
        pass


def safe_name(value: str, fallback: str = "reunion") -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value.strip())
    value = re.sub(r"\s+", "_", value).strip("._ ")
    return (value or fallback)[:90]


def fmt_time(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(path)])


@dataclass
class Device:
    index: int
    name: str
    channels: int
    sample_rate: int
    loopback: bool

    @property
    def label(self) -> str:
        kind = " · audio de Windows" if self.loopback else ""
        return f"{self.name}{kind} · {self.channels} canal(es)"


@dataclass
class Segment:
    source: str
    speaker: str
    start: float
    end: float
    text: str


def emit(event_q: mp.Queue, kind: str, **payload: Any) -> None:
    event_q.put({"kind": kind, **payload})


def list_devices_worker(event_q: mp.Queue) -> None:
    try:
        import pyaudiowpatch as pyaudio
        mics, loops = [], []
        default_mic = default_loop = None
        with pyaudio.PyAudio() as audio:
            try:
                default_mic = int(audio.get_default_input_device_info()["index"])
            except Exception:
                pass
            for raw in audio.get_device_info_generator():
                channels = int(raw.get("maxInputChannels", 0) or 0)
                if channels <= 0:
                    continue
                item = {
                    "index": int(raw["index"]),
                    "name": str(raw.get("name", "Audio")),
                    "channels": channels,
                    "sample_rate": int(float(raw.get("defaultSampleRate", 48000))),
                    "loopback": bool(raw.get("isLoopbackDevice", False)),
                }
                (loops if item["loopback"] else mics).append(item)
            try:
                default_loop = int(audio.get_default_wasapi_loopback()["index"])
            except Exception:
                default_loop = loops[0]["index"] if loops else None
        emit(event_q, "devices", mics=mics, loops=loops, default_mic=default_mic, default_loop=default_loop)
    except BaseException as exc:
        emit(event_q, "devices_error", message=str(exc), detail=traceback.format_exc())


def audio_worker(mode: str, device: dict[str, Any], source: str, output: str, control_q: mp.Queue, event_q: mp.Queue, duration: float = 5.0) -> None:
    try:
        import numpy as np
        import pyaudiowpatch as pyaudio
        mic_mode = source == "microphone"
        with pyaudio.PyAudio() as audio:
            raw = audio.get_device_info_by_index(int(device["index"]))
            capture_channels = max(1, min(2, int(raw.get("maxInputChannels", 1) or 1)))
            output_channels = 1 if mic_mode else capture_channels
            rate = int(float(raw.get("defaultSampleRate", 48000)))
            chunk = max(320, rate // 50)
            silence = b"\x00" * chunk * output_channels * 2
            wav_file = None
            if mode == "capture":
                out = Path(output)
                out.parent.mkdir(parents=True, exist_ok=True)
                wav_file = wave.open(str(out), "wb")
                wav_file.setnchannels(output_channels)
                wav_file.setsampwidth(2)
                wav_file.setframerate(rate)
            stream = audio.open(format=pyaudio.paInt16, channels=capture_channels, rate=rate, input=True, input_device_index=int(device["index"]), frames_per_buffer=chunk, start=False)
            emit(event_q, "audio_ready", source=source, rate=rate, channels=output_channels)
            while True:
                cmd = control_q.get()
                if cmd == "start":
                    break
                if cmd == "stop":
                    return
            stream.start_stream()
            emit(event_q, "audio_started", source=source)
            start = time.monotonic()
            paused = False
            selected = 0
            candidate = 0
            candidate_count = 0
            dc = 0.0
            last_level = 0.0
            try:
                while True:
                    while True:
                        try:
                            cmd = control_q.get_nowait()
                        except queue.Empty:
                            break
                        if cmd == "stop":
                            emit(event_q, "audio_finished", source=source, output=output)
                            return
                        paused = cmd == "pause" if cmd in ("pause", "resume") else paused
                    if mode == "test" and time.monotonic() - start >= duration:
                        emit(event_q, "audio_finished", source=source, output="")
                        return
                    data = stream.read(chunk, exception_on_overflow=False)
                    clipping = 0.0
                    if paused:
                        output_data, level = silence, 0.0
                    else:
                        samples = np.frombuffer(data, dtype=np.int16)
                        if mic_mode and samples.size:
                            usable = samples.size // capture_channels * capture_channels
                            frames = samples[:usable].reshape(-1, capture_channels).astype(np.float64)
                            if capture_channels == 1:
                                mono = frames[:, 0]
                            else:
                                rms_channels = np.sqrt(np.mean(frames ** 2, axis=0))
                                strongest = int(np.argmax(rms_channels))
                                if strongest != selected and rms_channels[strongest] > max(180.0, rms_channels[selected] * 1.65):
                                    if strongest == candidate:
                                        candidate_count += 1
                                    else:
                                        candidate, candidate_count = strongest, 1
                                    if candidate_count >= 12:
                                        selected, candidate_count = strongest, 0
                                else:
                                    candidate_count = max(0, candidate_count - 1)
                                weakest = int(np.argmin(rms_channels))
                                mono = frames[:, selected] if rms_channels[strongest] > 180 and rms_channels[strongest] > rms_channels[weakest] * 1.45 else np.mean(frames, axis=1)
                            mean = float(np.mean(mono))
                            dc = 0.985 * dc + 0.015 * mean
                            processed = np.clip(np.rint(mono - dc), -32768, 32767).astype(np.int16)
                            output_data = processed.tobytes()
                            rms = float(np.sqrt(np.mean(processed.astype(np.float64) ** 2)))
                            clipping = float(np.mean(np.abs(processed.astype(np.int32)) >= 31800))
                            level = min(1.0, rms / 7000.0)
                        else:
                            output_data = data
                            if samples.size:
                                rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
                                clipping = float(np.mean(np.abs(samples.astype(np.int32)) >= 31800))
                                level = min(1.0, rms / 12000.0)
                            else:
                                level = 0.0
                        if wav_file:
                            wav_file.writeframesraw(output_data)
                    now = time.monotonic()
                    if now - last_level >= 0.08:
                        emit(event_q, "level", source=source, value=level, clipping=clipping)
                        last_level = now
            finally:
                try:
                    stream.stop_stream()
                except Exception:
                    pass
                stream.close()
                if wav_file:
                    wav_file.writeframes(b"")
                    wav_file.close()
    except BaseException as exc:
        emit(event_q, "audio_error", source=source, message=str(exc), detail=traceback.format_exc())


def optimize_microphone(source: Path, target: Path) -> dict[str, float]:
    import numpy as np
    with wave.open(str(source), "rb") as reader:
        channels, width, rate, frames = reader.getnchannels(), reader.getsampwidth(), reader.getframerate(), reader.getnframes()
        if width != 2:
            raise RuntimeError("Formato de micrófono no admitido")
        raw = np.frombuffer(reader.readframes(frames), dtype=np.int16)
    if channels > 1:
        raw = np.mean(raw[: raw.size // channels * channels].reshape(-1, channels).astype(np.float64), axis=1)
    else:
        raw = raw.astype(np.float64)
    centered = raw - float(np.mean(raw))
    block = max(1, rate // 4)
    rms_values = [float(np.sqrt(np.mean(centered[i:i+block] ** 2))) for i in range(0, centered.size, block) if centered[i:i+block].size]
    nonzero = [x for x in rms_values if x > 8]
    noise = float(np.percentile(nonzero, 20)) if nonzero else 0.0
    speech = [x for x in nonzero if x > max(110.0, noise * 1.75)]
    speech_rms = float(np.percentile(speech, 65)) if speech else (float(np.percentile(nonzero, 80)) if nonzero else 0.0)
    gain = float(np.clip(5200.0 / speech_rms, 0.75, 6.0)) if speech_rms > 1 else 1.0
    normalized = centered * gain
    threshold, ratio = 9000.0, 2.6
    mag = np.abs(normalized)
    compressed = np.sign(normalized) * np.where(mag <= threshold, mag, threshold + (mag - threshold) / ratio)
    limited = np.tanh(compressed / 30000.0) * 30000.0
    out = np.clip(np.rint(limited), -32768, 32767).astype(np.int16)
    with wave.open(str(target), "wb") as writer:
        writer.setnchannels(1); writer.setsampwidth(2); writer.setframerate(rate); writer.writeframes(out.tobytes())
    return {"gain": gain, "noise_rms": noise, "speech_rms": speech_rms, "duration": frames / max(1, rate)}


def write_results(folder: Path, meta: dict[str, Any], segments: list[Segment]) -> dict[str, str]:
    txt = folder / "transcripcion.txt"
    js = folder / "transcripcion.json"
    page = folder / "transcripcion.html"
    js.write_text(json.dumps([asdict(s) for s in segments], ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [APP_NAME, f"Empresa: {meta['company']}", f"Reunión: {meta['meeting']}", f"Contactos: {meta['contacts']}", ""]
    for s in segments:
        lines.append(f"[{fmt_time(s.start)} - {fmt_time(s.end)}] {s.speaker}: {s.text}")
    txt.write_text("\n".join(lines), encoding="utf-8")
    logo_data = ""
    logo = ASSETS / "logo_ingar.png"
    if logo.exists():
        logo_data = "data:image/png;base64," + base64.b64encode(logo.read_bytes()).decode("ascii")
    cards = "".join(f'<article data-speaker="{html.escape(s.speaker)}"><div><b>{fmt_time(s.start)} — {html.escape(s.speaker)}</b></div><p contenteditable="true">{html.escape(s.text)}</p></article>' for s in segments)
    page.write_text(f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><title>{html.escape(meta['meeting'])}</title><style>body{{font-family:Arial;margin:0;color:#263943}}header{{position:sticky;top:0;background:white;border-bottom:1px solid #ccd7dd;padding:14px 5vw;display:flex;gap:20px;align-items:center}}img{{width:.75in}}main{{max-width:1050px;margin:22px auto;padding:0 5vw}}h1{{color:#173650;font-size:22px;margin:0}}.controls{{margin-left:auto}}input,button{{padding:8px;border:1px solid #ccd7dd;background:white}}.players{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:18px 0}}audio{{width:100%}}article{{border-bottom:1px solid #ccd7dd;padding:12px 0}}article b{{color:#0878b9}}article p{{font-size:15px;line-height:1.5;outline:none}}@media(max-width:800px){{.players{{grid-template-columns:1fr}}}}</style></head><body><header><img src="{logo_data}"><div><h1>{html.escape(meta['meeting'])}</h1><small>{html.escape(meta['company'])} · {html.escape(meta['contacts'])}</small></div><div class="controls"><input id="q" placeholder="Buscar"><button onclick="window.print()">PDF</button></div></header><main><div class="players"><div><b>Tu voz optimizada</b><audio controls src="audio_microfono.wav"></audio></div><div><b>Tu voz original</b><audio controls src="audio_microfono_original.wav"></audio></div><div><b>Interlocutores</b><audio controls src="audio_sistema.wav"></audio></div></div><section id="list">{cards or '<p>No se detectó voz.</p>'}</section></main><script>q.oninput=()=>document.querySelectorAll('article').forEach(x=>x.style.display=x.innerText.toLowerCase().includes(q.value.toLowerCase())?'':'none')</script></body></html>''', encoding="utf-8")
    return {"html": str(page), "txt": str(txt), "json": str(js)}


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("980x700")
        self.minsize(880, 620)
        self.configure(bg=WHITE)
        ico = ASSETS / "ingar_meeting_transcriber.ico"
        if ico.exists() and sys.platform.startswith("win"):
            try: self.iconbitmap(default=str(ico))
            except Exception: pass
        self.event_q: mp.Queue = mp.Queue()
        self.processes: dict[str, mp.Process] = {}
        self.controls: dict[str, mp.Queue] = {}
        self.devices: dict[str, list[Device]] = {"mic": [], "loop": []}
        self.ready: set[str] = set()
        self.finished: set[str] = set()
        self.folder: Optional[Path] = None
        self.started: Optional[float] = None
        self.recording = False
        self.paused = False
        self.transcribing = False
        self.test_mode = False
        self.latest_html = ""
        self._style()
        self._ui()
        self.after(100, self._poll)
        self.after(500, self._timer)
        self.after(200, self.refresh_devices)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _style(self) -> None:
        s = ttk.Style(self)
        try: s.theme_use("clam")
        except Exception: pass
        s.configure("TFrame", background=WHITE); s.configure("TLabel", background=WHITE, foreground=INK, font=("Segoe UI", 9))
        s.configure("Title.TLabel", background=WHITE, foreground=NAVY, font=("Segoe UI", 20, "bold")); s.configure("Sub.TLabel", background=WHITE, foreground=MUTED, font=("Segoe UI", 8))
        s.configure("Primary.TButton", background=NAVY, foreground=WHITE, padding=(14, 9), font=("Segoe UI", 9, "bold")); s.configure("Accent.TButton", background=BLUE, foreground=WHITE, padding=(14, 9), font=("Segoe UI", 9, "bold")); s.configure("Danger.TButton", background=RED, foreground=WHITE, padding=(14, 9), font=("Segoe UI", 9, "bold"))
        s.configure("Level.Horizontal.TProgressbar", troughcolor="#DDE5E9", background=BLUE)

    def _ui(self) -> None:
        root = ttk.Frame(self, padding=22); root.pack(fill="both", expand=True)
        top = ttk.Frame(root); top.pack(fill="x")
        self.logo_img = None
        logo = ASSETS / "logo_ingar.png"
        if logo.exists():
            try:
                self.logo_img = tk.PhotoImage(file=str(logo)); factor = max(1, self.logo_img.width() // 150); self.logo_img = self.logo_img.subsample(factor, factor)
                ttk.Label(top, image=self.logo_img).pack(side="left", padx=(0, 18))
            except Exception: pass
        titles = ttk.Frame(top); titles.pack(side="left", fill="x", expand=True)
        ttk.Label(titles, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(titles, text="Grabación y transcripción local · sin API paga", style="Sub.TLabel").pack(anchor="w")
        ttk.Button(top, text="Abrir sesiones", command=lambda: open_folder(SESSIONS)).pack(side="right")
        form = ttk.Frame(root); form.pack(fill="x", pady=(18, 8)); form.columnconfigure(0, weight=1); form.columnconfigure(1, weight=1)
        self.company, self.meeting, self.contacts = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for col, label, var in [(0,"EMPRESA",self.company),(1,"REUNIÓN",self.meeting)]:
            ttk.Label(form, text=label).grid(row=0,column=col,sticky="w"); ttk.Entry(form,textvariable=var).grid(row=1,column=col,sticky="ew",padx=(0,8 if col==0 else 0))
        ttk.Label(form,text="CONTACTOS").grid(row=2,column=0,sticky="w",pady=(9,0)); ttk.Entry(form,textvariable=self.contacts).grid(row=3,column=0,sticky="ew",padx=(0,8))
        self.language = tk.StringVar(value="Automático"); self.model = tk.StringVar(value="Small — recomendado")
        advanced = ttk.Frame(form); advanced.grid(row=2,column=1,rowspan=2,sticky="ew",pady=(9,0)); advanced.columnconfigure(0,weight=1); advanced.columnconfigure(1,weight=1)
        ttk.Combobox(advanced,textvariable=self.language,values=list(LANGUAGES),state="readonly").grid(row=0,column=0,sticky="ew",padx=(0,5)); ttk.Combobox(advanced,textvariable=self.model,values=list(MODELS_MAP),state="readonly").grid(row=0,column=1,sticky="ew")
        audio = ttk.Frame(root); audio.pack(fill="x", pady=8); audio.columnconfigure(0,weight=1); audio.columnconfigure(1,weight=1)
        self.mic_var, self.loop_var = tk.StringVar(), tk.StringVar()
        ttk.Label(audio,text="MICRÓFONO · TU VOZ").grid(row=0,column=0,sticky="w"); ttk.Label(audio,text="AUDIO DE WINDOWS · INTERLOCUTORES").grid(row=0,column=1,sticky="w",padx=(8,0))
        self.mic_combo=ttk.Combobox(audio,textvariable=self.mic_var,state="readonly"); self.loop_combo=ttk.Combobox(audio,textvariable=self.loop_var,state="readonly")
        self.mic_combo.grid(row=1,column=0,sticky="ew"); self.loop_combo.grid(row=1,column=1,sticky="ew",padx=(8,0))
        self.mic_level=ttk.Progressbar(audio,style="Level.Horizontal.TProgressbar",maximum=100); self.loop_level=ttk.Progressbar(audio,style="Level.Horizontal.TProgressbar",maximum=100)
        self.mic_level.grid(row=2,column=0,sticky="ew",pady=(8,0)); self.loop_level.grid(row=2,column=1,sticky="ew",padx=(8,0),pady=(8,0))
        buttons=ttk.Frame(root); buttons.pack(fill="x",pady=10)
        ttk.Button(buttons,text="Actualizar audio",command=self.refresh_devices).pack(side="left")
        self.test_btn=ttk.Button(buttons,text="Probar 5 segundos",command=self.test_audio); self.test_btn.pack(side="left",padx=7)
        self.consent=tk.BooleanVar(); ttk.Checkbutton(buttons,text="Confirmo que la reunión puede ser grabada",variable=self.consent).pack(side="right")
        controls=ttk.Frame(root); controls.pack(fill="x",pady=8)
        self.start_btn=ttk.Button(controls,text="INICIAR GRABACIÓN",style="Primary.TButton",command=self.start_recording); self.pause_btn=ttk.Button(controls,text="PAUSAR",style="Accent.TButton",command=self.toggle_pause,state="disabled"); self.stop_btn=ttk.Button(controls,text="FINALIZAR Y TRANSCRIBIR",style="Danger.TButton",command=self.stop_recording,state="disabled")
        self.start_btn.pack(side="left"); self.pause_btn.pack(side="left",padx=8); self.stop_btn.pack(side="left")
        self.timer_var=tk.StringVar(value="00:00:00"); ttk.Label(controls,textvariable=self.timer_var,style="Title.TLabel").pack(side="right")
        self.status=tk.StringVar(value="Preparando dispositivos…"); ttk.Label(root,textvariable=self.status,style="Sub.TLabel").pack(anchor="w",pady=(8,3))
        self.log=tk.Text(root,height=10,wrap="word",font=("Consolas",8),relief="solid",borderwidth=1); self.log.pack(fill="both",expand=True)
        bottom=ttk.Frame(root); bottom.pack(fill="x",pady=(8,0)); self.result_btn=ttk.Button(bottom,text="Abrir última transcripción",command=self.open_result,state="disabled"); self.result_btn.pack(side="left")

    def _append(self, text: str) -> None:
        self.log.insert("end", f"[{datetime.now():%H:%M:%S}] {text}\n"); self.log.see("end")

    def refresh_devices(self) -> None:
        self.status.set("Detectando dispositivos de audio…"); mp.Process(target=list_devices_worker,args=(self.event_q,),daemon=True).start()

    def _selected(self, kind: str, label: str) -> Optional[Device]:
        return next((d for d in self.devices[kind] if d.label == label), None)

    def _spawn_audio(self, mode: str, duration: float = 5.0) -> None:
        mic, loop = self._selected("mic",self.mic_var.get()), self._selected("loop",self.loop_var.get())
        if not mic or not loop:
            raise ValueError("Seleccione micrófono y audio de Windows")
        self.ready.clear(); self.finished.clear(); self.processes.clear(); self.controls.clear()
        outputs = {"microphone": str(self.folder / "audio_microfono_original.wav") if self.folder else "", "system": str(self.folder / "audio_sistema.wav") if self.folder else ""}
        for source, device in (("microphone",mic),("system",loop)):
            cq: mp.Queue = mp.Queue(); self.controls[source]=cq
            p=mp.Process(target=audio_worker,args=(mode,asdict(device),source,outputs[source],cq,self.event_q,duration),daemon=True); self.processes[source]=p; p.start()

    def test_audio(self) -> None:
        if self.recording or self.transcribing: return
        try: self.test_mode=True; self.test_btn.configure(state="disabled"); self._spawn_audio("test",5.0); self.status.set("Preparando prueba de audio…")
        except Exception as exc: self.test_mode=False; self.test_btn.configure(state="normal"); messagebox.showerror(APP_NAME,str(exc))

    def start_recording(self) -> None:
        if not self.consent.get(): messagebox.showerror(APP_NAME,"Confirme que la reunión puede ser grabada"); return
        if not self.meeting.get().strip(): messagebox.showerror(APP_NAME,"Ingrese el nombre de la reunión"); return
        try:
            now=datetime.now(); self.folder=SESSIONS/f"{now:%Y%m%d_%H%M%S}_{safe_name(self.company.get(),'empresa')}_{safe_name(self.meeting.get())}"; self.folder.mkdir(parents=True)
            meta={"company":self.company.get().strip(),"meeting":self.meeting.get().strip(),"contacts":self.contacts.get().strip(),"started_at":now.isoformat(timespec="seconds")}; (self.folder/"datos_reunion.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
            self.recording=True; self.started=time.monotonic(); self._spawn_audio("capture"); self.start_btn.configure(state="disabled"); self.pause_btn.configure(state="normal"); self.stop_btn.configure(state="normal"); self.status.set("Preparando grabación…")
        except Exception as exc: self.recording=False; messagebox.showerror(APP_NAME,str(exc))

    def toggle_pause(self) -> None:
        self.paused=not self.paused
        for q in self.controls.values(): q.put("pause" if self.paused else "resume")
        self.pause_btn.configure(text="REANUDAR" if self.paused else "PAUSAR"); self.status.set("Pausado" if self.paused else "Grabando")

    def stop_recording(self) -> None:
        if not self.recording: return
        self.recording=False
        for q in self.controls.values(): q.put("stop")
        self.pause_btn.configure(state="disabled"); self.stop_btn.configure(state="disabled"); self.status.set("Cerrando audio…")
        threading.Thread(target=self._wait_and_transcribe,daemon=True).start()

    def _wait_and_transcribe(self) -> None:
        for p in self.processes.values(): p.join(timeout=12)
        self.after(0,self._start_transcription)

    def _start_transcription(self) -> None:
        if not self.folder: return
        self.transcribing=True; self.status.set("Preparando tu voz y transcribiendo…"); threading.Thread(target=self._transcribe,daemon=True).start()

    def _transcribe(self) -> None:
        try:
            from faster_whisper import WhisperModel
            assert self.folder
            original=self.folder/"audio_microfono_original.wav"; optimized=self.folder/"audio_microfono.wav"; system=self.folder/"audio_sistema.wav"
            diagnostic=optimize_microphone(original,optimized); (self.folder/"diagnostico_microfono.json").write_text(json.dumps(diagnostic,indent=2),encoding="utf-8")
            model_name=MODELS_MAP[self.model.get()]; lang=LANGUAGES[self.language.get()]
            model=WhisperModel(model_name,device="cpu",compute_type="int8",cpu_threads=max(4,min(12,os.cpu_count() or 8)),download_root=str(MODELS))
            segments=[]
            for source,speaker,path in (("microphone","Maximiliano",optimized),("system","Interlocutor",system)):
                if not path.exists() or path.stat().st_size<1000: continue
                vad={"threshold":0.10,"min_speech_duration_ms":40,"min_silence_duration_ms":850,"speech_pad_ms":750} if source=="microphone" else {"threshold":0.34,"min_speech_duration_ms":120,"min_silence_duration_ms":420,"speech_pad_ms":300}
                raw,_=model.transcribe(str(path),language=lang,task="transcribe",beam_size=7 if source=="microphone" else 5,temperature=0,vad_filter=True,vad_parameters=vad,condition_on_previous_text=source!="microphone",no_speech_threshold=0.55)
                for item in raw:
                    text=str(item.text).strip()
                    if text: segments.append(Segment(source,speaker,float(item.start),float(item.end),text))
            segments.sort(key=lambda x:(x.start,x.end,x.source))
            meta=json.loads((self.folder/"datos_reunion.json").read_text(encoding="utf-8")); outputs=write_results(self.folder,meta,segments)
            self.event_q.put({"kind":"transcription_done","outputs":outputs,"count":len(segments)})
        except BaseException as exc:
            self.event_q.put({"kind":"transcription_error","message":str(exc),"detail":traceback.format_exc()})

    def _poll(self) -> None:
        while True:
            try: e=self.event_q.get_nowait()
            except queue.Empty: break
            kind=e.get("kind")
            if kind=="devices":
                self.devices["mic"]=[Device(**x) for x in e["mics"]]; self.devices["loop"]=[Device(**x) for x in e["loops"]]
                self.mic_combo.configure(values=[d.label for d in self.devices["mic"]]); self.loop_combo.configure(values=[d.label for d in self.devices["loop"]])
                mic=next((d.label for d in self.devices["mic"] if d.index==e.get("default_mic")), self.devices["mic"][0].label if self.devices["mic"] else ""); loop=next((d.label for d in self.devices["loop"] if d.index==e.get("default_loop")), self.devices["loop"][0].label if self.devices["loop"] else "")
                self.mic_var.set(mic); self.loop_var.set(loop); self.status.set("Listo" if mic and loop else "Falta un dispositivo de audio"); self._append(f"Micrófonos: {len(self.devices['mic'])} · audio Windows: {len(self.devices['loop'])}")
            elif kind=="devices_error": self.status.set("Error de audio"); self._append(e.get("message","Error"))
            elif kind=="audio_ready":
                self.ready.add(e["source"])
                if self.ready=={"microphone","system"}:
                    for q in self.controls.values(): q.put("start")
                    self.status.set("Probando audio…" if self.test_mode else "Grabando")
            elif kind=="level":
                value=float(e.get("value",0))*100
                (self.mic_level if e["source"]=="microphone" else self.loop_level)["value"]=value
            elif kind=="audio_finished":
                self.finished.add(e["source"])
                if self.test_mode and self.finished=={"microphone","system"}:
                    self.test_mode=False; self.test_btn.configure(state="normal"); self.status.set("Prueba finalizada")
            elif kind=="audio_error": self.status.set("Error de captura"); self._append(f"{e.get('source')}: {e.get('message')}")
            elif kind=="transcription_done":
                self.transcribing=False; self.latest_html=e["outputs"]["html"]; self.status.set(f"Transcripción terminada · {e['count']} segmentos"); self.start_btn.configure(state="normal"); self.result_btn.configure(state="normal"); webbrowser.open(Path(self.latest_html).as_uri())
            elif kind=="transcription_error": self.transcribing=False; self.status.set("Error de transcripción"); self.start_btn.configure(state="normal"); self._append(e.get("message","Error")); messagebox.showerror(APP_NAME,e.get("message","Error"))
        self.after(100,self._poll)

    def _timer(self) -> None:
        if self.started and (self.recording or self.transcribing): self.timer_var.set(fmt_time(time.monotonic()-self.started))
        self.after(500,self._timer)

    def open_result(self) -> None:
        if self.latest_html: webbrowser.open(Path(self.latest_html).as_uri())

    def _close(self) -> None:
        if self.recording:
            messagebox.showwarning(APP_NAME,"Finalice la grabación antes de cerrar"); return
        self.destroy()


def main() -> int:
    try:
        App().mainloop(); return 0
    except BaseException as exc:
        log_error("startup_error",exc)
        if sys.platform.startswith("win"):
            try:
                import ctypes; ctypes.windll.user32.MessageBoxW(0,f"No se pudo iniciar.\n\n{exc}\n\nRevise logs\\startup_error.log",APP_NAME,0x10)
            except Exception: pass
        return 1


if __name__ == "__main__":
    mp.freeze_support()
    mp.set_start_method("spawn", force=True)
    raise SystemExit(main())
