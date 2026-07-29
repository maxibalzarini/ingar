from pathlib import Path
import re

path = Path('meeting_transcriber/app.py')
text = path.read_text(encoding='utf-8')

text = text.replace('APP_VERSION = "1.4.2"', 'APP_VERSION = "1.5.0"', 1)
text = text.replace(
    'self.language = tk.StringVar(value="Automático"); self.model = tk.StringVar(value="Small — recomendado")',
    'self.language = tk.StringVar(value="Español"); self.model = tk.StringVar(value="Medium — precisión")',
    1,
)

old_mix = 'mono = frames[:, selected] if rms_channels[strongest] > 180 and rms_channels[strongest] > rms_channels[weakest] * 1.45 else np.mean(frames, axis=1)'
if old_mix not in text:
    raise RuntimeError('No se encontró la mezcla de canales del micrófono')
text = text.replace(
    old_mix,
    'mono = frames[:, selected]  # No promediar: evita cancelación de fase y pérdida de consonantes',
    1,
)

start = text.index('    def _transcribe(self) -> None:\n')
end = text.index('\n    def _poll(self) -> None:', start)

method = r'''    def _transcribe(self) -> None:
        try:
            from faster_whisper import WhisperModel

            assert self.folder
            original = self.folder / "audio_microfono_original.wav"
            optimized = self.folder / "audio_microfono.wav"
            system = self.folder / "audio_sistema.wav"
            diagnostic = optimize_microphone(original, optimized)
            (self.folder / "diagnostico_microfono.json").write_text(
                json.dumps(diagnostic, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            model_name = MODELS_MAP[self.model.get()]
            language = LANGUAGES[self.language.get()] or "es"
            model = WhisperModel(
                model_name,
                device="cpu",
                compute_type="int8",
                cpu_threads=max(4, min(12, os.cpu_count() or 8)),
                download_root=str(MODELS),
            )

            meta = json.loads(
                (self.folder / "datos_reunion.json").read_text(encoding="utf-8")
            )
            base_prompt = (
                "Transcripción literal. No resumir ni sustituir palabras por sinónimos. "
                f"Empresa: {meta.get('company', '')}. "
                f"Reunión: {meta.get('meeting', '')}. "
                f"Contactos: {meta.get('contacts', '')}. "
                "Conservar consonantes y palabras completas. Vocabulario posible: "
                "pisotearon, mantenimiento, confiabilidad, criticidad, trazabilidad, "
                "indicadores, activos, ingeniería, operación, inspección, laboratorio."
            )

            def collect(path, source, speaker, prompt, beam, vad, previous):
                raw, _ = model.transcribe(
                    str(path),
                    language=language,
                    task="transcribe",
                    beam_size=beam,
                    temperature=0,
                    vad_filter=True,
                    vad_parameters=vad,
                    condition_on_previous_text=previous,
                    no_speech_threshold=0.50,
                    initial_prompt=prompt,
                    word_timestamps=False,
                )
                found = []
                weighted = 0.0
                weight = 0.0
                transcript = []
                for item in raw:
                    value = str(item.text).strip()
                    if not value:
                        continue
                    found.append(
                        Segment(
                            source,
                            speaker,
                            float(item.start),
                            float(item.end),
                            value,
                        )
                    )
                    transcript.append(value)
                    logprob = getattr(item, "avg_logprob", None)
                    duration = max(0.25, float(item.end) - float(item.start))
                    if logprob is not None:
                        weighted += float(logprob) * duration
                        weight += duration
                score = weighted / weight if weight else -99.0
                return found, score, " ".join(transcript)

            segments = []
            remote_text = ""
            if system.exists() and system.stat().st_size >= 1000:
                remote_vad = {
                    "threshold": 0.34,
                    "min_speech_duration_ms": 120,
                    "min_silence_duration_ms": 420,
                    "speech_pad_ms": 300,
                }
                remote_segments, _, remote_text = collect(
                    system,
                    "system",
                    "Interlocutor",
                    base_prompt,
                    5,
                    remote_vad,
                    True,
                )
                segments.extend(remote_segments)

            local_prompt = base_prompt
            if remote_text:
                local_prompt += " Contexto de los interlocutores: " + remote_text[-1800:]

            local_vad = {
                "threshold": 0.08,
                "min_speech_duration_ms": 30,
                "min_silence_duration_ms": 950,
                "speech_pad_ms": 900,
            }
            candidates = []
            for label, candidate_path in (("original", original), ("optimizado", optimized)):
                if not candidate_path.exists() or candidate_path.stat().st_size < 1000:
                    continue
                local_segments, score, _ = collect(
                    candidate_path,
                    "microphone",
                    "Maximiliano",
                    local_prompt,
                    10,
                    local_vad,
                    True,
                )
                if local_segments:
                    candidates.append((label, local_segments, score))

            if candidates:
                selected_label, selected_segments, selected_score = max(
                    candidates,
                    key=lambda item: item[2],
                )
                segments.extend(selected_segments)
                (self.folder / "diagnostico_transcripcion_local.json").write_text(
                    json.dumps(
                        {
                            "selected_pass": selected_label,
                            "selected_score": selected_score,
                            "model": model_name,
                            "language": language,
                            "context_from_interlocutors": bool(remote_text),
                            "candidates": [
                                {
                                    "pass": label,
                                    "score": score,
                                    "segments": len(items),
                                }
                                for label, items, score in candidates
                            ],
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

            segments.sort(key=lambda x: (x.start, x.end, x.source))
            outputs = write_results(self.folder, meta, segments)
            self.event_q.put(
                {
                    "kind": "transcription_done",
                    "outputs": outputs,
                    "count": len(segments),
                }
            )
        except BaseException as exc:
            self.event_q.put(
                {
                    "kind": "transcription_error",
                    "message": str(exc),
                    "detail": traceback.format_exc(),
                }
            )
'''

text = text[:start] + method + text[end:]
path.write_text(text, encoding='utf-8')
print('PATCH_V1_5_OK')
