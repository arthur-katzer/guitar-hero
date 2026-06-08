#!/usr/bin/env python3
"""
pitch_analyzer.py
Real-time Pitch Analyzer with Fourier Transform & Curses UI.
Supports:
- Phase 1: Real-time file processing (MP3, WAV, etc.) via ffmpeg stream & playback.
- Phase 1.5: Terminal-based ASCII waveform (oscilloscope) and spectrum visualizer.
- Phase 2: Live microphone capturing and note detection.
"""

import os
import sys
import time
import queue
import argparse
import threading
import subprocess
import curses
import numpy as np
import sounddevice as sd

# ==============================================================================
# CONFIGURABLE SENSITIVITY & DSP TUNING LEVERS
# ==============================================================================
# 1. Noise gate RMS threshold. Below this value, audio is considered silence.
#    Lower values make the tuner more sensitive to quiet inputs.
#    Higher values filter out background hum/noise.
DEFAULT_NOISE_THRESHOLD = 0.01  

# 2. Guitar frequency bounds (Hz). Ignored frequencies outside these limits.
#    Standard guitar range is roughly E2 (~82 Hz) to high E6 (~1318 Hz).
MIN_DETECTION_FREQUENCY = 70.0   
MAX_DETECTION_FREQUENCY = 1500.0 

# 3. FFT Zero-Padding size. Higher values increase frequency resolution (precision),
#    making the cents tuner more stable and exact, but increase CPU load.
#    Should be a power of 2 (e.g., 8192, 16384, 32768).
FFT_RESOLUTION_SIZE = 16384     

# 4. HPS Max Harmonics. Controls how many downsampled copies of the spectrum
#    are multiplied in the Harmonic Product Spectrum algorithm.
#    - 1: Standard peak picking (highly sensitive, picks up octave double/triples).
#    - 2-4: Robust chord/note fundamental extraction. Default: 4.
HPS_HARMONIC_LEVEL = 4          

# 5. Note Stability Window. Number of consecutive audio frames that must agree
#    on the active note before updating the UI display.
#    - 1: Instant response (hyper-sensitive, flickers rapidly).
#    - 2-5: Smooth, stable note transitions (great for real instruments). Default: 3.
NOTE_STABILITY_WINDOW = 3       
# ==============================================================================

# Musical pitch calculation constants
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

class PitchAnalyzer:
    def __init__(self, file_path=None, sample_rate=44100, block_size=2048, threshold=DEFAULT_NOISE_THRESHOLD):
        self.file_path = file_path
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.threshold = threshold
        self.note_history = []  # List to buffer note changes for majority-vote stabilization
        
        # Audio streaming queues
        self.play_q = queue.Queue(maxsize=100)
        self.analysis_q = queue.Queue(maxsize=100)
        
        self.running = False
        self.paused = False
        self.current_mode = "Mic Mode" if not file_path else "File Mode"
        
        # Shared DSP state (thread-safe updates)
        self.lock = threading.Lock()
        self.current_samples = np.zeros(block_size, dtype=np.float32)
        self.current_magnitude = np.zeros(block_size // 2, dtype=np.float32)
        self.current_freqs = np.zeros(block_size // 2, dtype=np.float32)
        self.detected_note = "Silence"
        self.detected_hz = 0.0
        self.cents_deviation = 0.0
        self.rms_volume = 0.0
        
        # Streams & processes
        self.audio_stream = None
        self.ffmpeg_proc = None
        self.threads = []

    def start(self):
        self.running = True
        
        # Start core DSP processing thread
        dsp_thread = threading.Thread(target=self._dsp_loop, daemon=True)
        dsp_thread.start()
        self.threads.append(dsp_thread)
        
        if self.file_path:
            # File Mode: Start decoder thread and audio output stream
            decoder_thread = threading.Thread(target=self._file_decoder_loop, daemon=True)
            decoder_thread.start()
            self.threads.append(decoder_thread)
            
            try:
                self.audio_stream = sd.OutputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    blocksize=self.block_size,
                    callback=self._output_callback
                )
                self.audio_stream.start()
            except Exception as e:
                # Graceful fallback: If audio device fails, play back visually anyway (Simulation mode)
                self.current_mode = "File Mode (Simulation)"
        else:
            # Mic Mode: Start audio input stream
            try:
                self.audio_stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    blocksize=self.block_size,
                    callback=self._input_callback
                )
                self.audio_stream.start()
            except Exception as e:
                self.running = False
                raise RuntimeError(f"Failed to open microphone: {e}. Check ALSA/PipeWire configuration.")

    def stop(self):
        self.running = False
        if self.audio_stream:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception:
                pass
        if self.ffmpeg_proc:
            try:
                self.ffmpeg_proc.terminate()
            except Exception:
                pass
        for t in self.threads:
            if t.is_alive():
                t.join(timeout=0.2)

    def toggle_pause(self):
        if self.file_path:
            self.paused = not self.paused
            if self.paused:
                if self.audio_stream:
                    self.audio_stream.stop()
            else:
                if self.audio_stream:
                    self.audio_stream.start()

    def adjust_threshold(self, delta):
        with self.lock:
            self.threshold = max(0.0005, min(0.5, self.threshold + delta))

    # --- Audio I/O Callbacks ---
    def _input_callback(self, indata, frames, time_info, status):
        """Callback for sounddevice microphone input."""
        if not self.running:
            return
        mono_data = indata[:, 0].copy()
        try:
            self.analysis_q.put_nowait(mono_data)
        except queue.Full:
            pass  # Drop frames if queue overflows (prevents visual lag)

    def _output_callback(self, outdata, frames, time_info, status):
        """Callback for sounddevice file playback output."""
        if not self.running or self.paused:
            outdata.fill(0)
            return
            
        try:
            data = self.play_q.get_nowait()
            if len(data) < frames:
                outdata[:len(data), 0] = data
                outdata[len(data):, 0] = 0.0
                raise sd.CallbackStop()
            else:
                outdata[:, 0] = data[:frames]
        except queue.Empty:
            outdata.fill(0)  # Underflow fallback (silence)

    # --- Worker Loops ---
    def _file_decoder_loop(self):
        """Decodes MP3/WAV/etc using ffmpeg and feeds queues in real-time."""
        cmd = [
            "ffmpeg",
            "-i", self.file_path,
            "-f", "s16le",
            "-acodec", "pcm_s16le",
            "-ar", str(self.sample_rate),
            "-ac", "1",
            "-"
        ]
        try:
            self.ffmpeg_proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
        except FileNotFoundError:
            self.running = False
            return

        bytes_per_block = self.block_size * 2  # 16-bit = 2 bytes per sample
        
        while self.running:
            if self.paused:
                time.sleep(0.05)
                continue
                
            raw_bytes = self.ffmpeg_proc.stdout.read(bytes_per_block)
            if not raw_bytes:
                break  # EOF reached
                
            # Convert raw 16-bit PCM bytes to normalized float32 array
            samples = np.frombuffer(raw_bytes, dtype="<i2").astype(np.float32) / 32768.0
            
            # Pad chunk with zeros if it's the last incomplete chunk
            if len(samples) < self.block_size:
                samples = np.pad(samples, (0, self.block_size - len(samples)))
            
            # Feed play and analysis queues
            try:
                self.play_q.put(samples, timeout=2.0)
                self.analysis_q.put(samples, timeout=2.0)
            except queue.Full:
                pass
                
        self.running = False

    def _dsp_loop(self):
        """Consumes PCM blocks from analysis queue and executes FFT / Pitch Detection."""
        while self.running:
            try:
                # Wait briefly for incoming data chunk
                samples = self.analysis_q.get(timeout=0.1)
            except queue.Empty:
                continue
                
            # Calculate volume RMS for the Noise Gate
            rms = np.sqrt(np.mean(samples ** 2)) if len(samples) > 0 else 0.0
            
            if rms < self.threshold:
                # Noise gate triggered (Silence)
                with self.lock:
                    self.current_samples = samples
                    self.current_magnitude = np.zeros(self.block_size // 2)
                    self.current_freqs = np.zeros(self.block_size // 2)
                    self.detected_note = "Silence"
                    self.detected_hz = 0.0
                    self.cents_deviation = 0.0
                    self.rms_volume = rms
                continue
                
            # Apply Hanning window to prevent spectral leakage
            windowed = samples * np.hanning(len(samples))
            
            # Zero-pad FFT for enhanced frequency resolution using configured resolution size
            fft_size = FFT_RESOLUTION_SIZE
            rfft_res = np.fft.rfft(windowed, n=fft_size)
            magnitude = np.abs(rfft_res)
            freqs = np.fft.rfftfreq(fft_size, 1.0 / self.sample_rate)
            
            # Guitar frequency range filters using configured bounds
            min_f, max_f = MIN_DETECTION_FREQUENCY, MAX_DETECTION_FREQUENCY
            min_idx = np.searchsorted(freqs, min_f)
            max_idx = np.searchsorted(freqs, max_f)
            
            # --- Harmonic Product Spectrum (HPS) Algorithm ---
            # Combats the "octave double / harmonic peak" problem on physical instruments
            hps = magnitude.copy()
            for r in range(2, HPS_HARMONIC_LEVEL + 1):  # downsample factors configured dynamically
                indices = np.arange(0, len(magnitude), r)
                dec = magnitude[indices]
                hps[:len(dec)] *= dec
                hps[len(dec):] = 0.0
                
            # Zero-out frequencies outside our guitar boundaries in HPS spectrum
            hps[:min_idx] = 0.0
            hps[max_idx:] = 0.0
            
            # Find dominant fundamental frequency (f0)
            peak_idx = np.argmax(hps)
            f0 = freqs[peak_idx]
            
            # Convert f0 to note representation
            note_str, cents = "Silence", 0.0
            if f0 > 0:
                midi_float = 12.0 * np.log2(f0 / 440.0) + 69.0
                midi_num = int(round(midi_float))
                
                if 0 <= midi_num < 128:
                    note_name = NOTE_NAMES[midi_num % 12]
                    octave = (midi_num // 12) - 1
                    note_str = f"{note_name}{octave}"
                    cents = (midi_float - midi_num) * 100.0
            
            # --- Note Stabilization & Flickering Filtering ---
            self.note_history.append((note_str, f0, cents))
            if len(self.note_history) > NOTE_STABILITY_WINDOW:
                self.note_history.pop(0)
                
            # Determine the most common stable note in the window history
            note_counts = {}
            for item in self.note_history:
                n = item[0]
                note_counts[n] = note_counts.get(n, 0) + 1
                
            stable_note = max(note_counts, key=note_counts.get)
            
            # Retrieve the most recent HZ and cents of this stable note
            stable_hz = 0.0
            stable_cents = 0.0
            for item in reversed(self.note_history):
                if item[0] == stable_note:
                    stable_hz = item[1]
                    stable_cents = item[2]
                    break
            
            # Thread-safe updates of active analysis data
            with self.lock:
                self.current_samples = samples
                
                # Downsample/slice FFT magnitudes for visualization
                vis_max_idx = np.searchsorted(freqs, 1600.0)
                self.current_magnitude = magnitude[:vis_max_idx]
                self.current_freqs = freqs[:vis_max_idx]
                
                self.detected_note = stable_note
                self.detected_hz = stable_hz
                self.cents_deviation = stable_cents
                self.rms_volume = rms

# --- Curses UI Drawer Functions ---
def draw_waveform(stdscr, samples, r, c, h, w):
    """Draws a real-time oscilloscope of the time-domain waveform."""
    mid_y = r + h // 2
    
    # Draw central baseline
    for col in range(w):
        stdscr.addch(mid_y, c + col, '-', curses.color_pair(3))
        
    if len(samples) == 0:
        return
        
    step = max(1, len(samples) // w)
    for col in range(min(w, len(samples) // step)):
        val = samples[col * step]
        y_offset = int(val * (h // 2 - 1))
        y = mid_y - y_offset
        y = max(r, min(r + h - 1, y))
        stdscr.addch(y, c + col, '█', curses.color_pair(1) | curses.A_BOLD)

def draw_spectrum(stdscr, magnitude, freqs, r, c, h, w):
    """Draws a vertical spectrogram (frequency domain bar chart)."""
    if len(magnitude) == 0:
        return
        
    max_val = np.max(magnitude)
    if max_val <= 0:
        max_val = 1.0
        
    step = max(1, len(magnitude) // w)
    for col in range(min(w, len(magnitude) // step)):
        chunk = magnitude[col * step : (col + 1) * step]
        val = np.mean(chunk) if len(chunk) > 0 else 0.0
        
        # Scale block height
        bar_h = int((val / max_val) * (h - 1))
        bar_h = max(0, min(h - 1, bar_h))
        
        for row_offset in range(bar_h):
            try:
                y = r + h - 1 - row_offset
                stdscr.addch(y, c + col, '║', curses.color_pair(2))
            except curses.error:
                pass

def safe_addstr(stdscr, y, x, text, attr=0):
    """Safely adds a string to curses window without crashing on bounds/bottom-right cell."""
    try:
        h, w = stdscr.getmaxyx()
        if y < 0 or y >= h or x < 0 or x >= w:
            return
        # Slice text to fit screen width
        max_len = w - x
        if len(text) > max_len:
            text = text[:max_len]
        # Avoid writing to the exact bottom-right character to prevent scrolling errors
        if y == h - 1 and x + len(text) >= w:
            text = text[:w - x - 2]
        if text:
            stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass

def draw_box(stdscr, y, x, h, w):
    """Draws a simple box using standard ASCII/Unicode-like characters."""
    for col in range(x, x + w):
        try:
            stdscr.addch(y, col, '-')
            stdscr.addch(y + h - 1, col, '-')
        except curses.error:
            pass
    for row in range(y, y + h):
        try:
            stdscr.addch(row, x, '|')
            stdscr.addch(row, x + w - 1, '|')
        except curses.error:
            pass
    try:
        stdscr.addch(y, x, '+')
        stdscr.addch(y, x + w - 1, '+')
        stdscr.addch(y + h - 1, x, '+')
        stdscr.addch(y + h - 1, x + w - 1, '+')
    except curses.error:
        pass

def draw_tuner(stdscr, note, hz, cents, threshold, rms, r, w):
    """Draws a beautiful instrument note tuner and cent gauge."""
    # Frame Box
    stdscr.attron(curses.color_pair(4) | curses.A_BOLD)
    draw_box(stdscr, r, 2, 7, w - 4)
    stdscr.attroff(curses.color_pair(4) | curses.A_BOLD)
    
    # Render note text or Silence
    if note == "Silence":
        text = " [ SILENCE ] "
        safe_addstr(stdscr, r + 2, (w - len(text)) // 2, text, curses.color_pair(3) | curses.A_DIM)
    else:
        text = f"   {note}   "
        hz_text = f"{hz:.2f} Hz"
        safe_addstr(stdscr, r + 2, (w - len(text)) // 2, text, curses.color_pair(2) | curses.A_REVERSE | curses.A_BOLD)
        safe_addstr(stdscr, r + 3, (w - len(hz_text)) // 2, hz_text, curses.color_pair(3))
        
        # Cent deviation needle/gauge
        # Cents range: -50 to +50
        gauge_w = 40
        needle_pos = int(((cents + 50.0) / 100.0) * gauge_w)
        needle_pos = max(0, min(gauge_w - 1, needle_pos))
        
        gauge_str = ["-"] * gauge_w
        gauge_str[gauge_w // 2] = "|"
        
        # Determine needle state colors
        if abs(cents) < 5.0:
            gauge_str[needle_pos] = "★"
            color = curses.color_pair(2) | curses.A_BOLD  # Green (In Tune!)
            status_lbl = " [ IN TUNE ] "
        elif cents < 0:
            gauge_str[needle_pos] = "◀"
            color = curses.color_pair(1) | curses.A_BOLD  # Yellow (Flat)
            status_lbl = f" FLAT ({int(cents)} cents) "
        else:
            gauge_str[needle_pos] = "▶"
            color = curses.color_pair(5) | curses.A_BOLD  # Red (Sharp)
            status_lbl = f" SHARP (+{int(cents)} cents) "
            
        gauge_line = "   [ " + "".join(gauge_str) + " ]   "
        safe_addstr(stdscr, r + 4, (w - len(gauge_line)) // 2, gauge_line, color)
        safe_addstr(stdscr, r + 5, (w - len(status_lbl)) // 2, status_lbl, color)

    # Noise gate telemetry meter
    gate_info = f" RMS Volume: {rms:.4f}  |  Noise Gate Threshold: {threshold:.4f} "
    safe_addstr(stdscr, r + 6, (w - len(gate_info)) // 2, gate_info, curses.color_pair(4))

# --- UI Setup and Curses Lifecycle ---
def run_curses_ui(stdscr, analyzer):
    # Setup color definitions
    curses.start_color()
    curses.init_pair(1, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Waveform (Yellow)
    curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)   # Spectrogram (Green)
    curses.init_pair(3, curses.COLOR_WHITE, curses.COLOR_BLACK)   # Lines/Ticks
    curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)    # Interface details
    curses.init_pair(5, curses.COLOR_RED, curses.COLOR_BLACK)     # Tuner alarms
    
    # Hide blinking terminal cursor
    try:
        curses.curs_set(0)
    except curses.error:
        pass
        
    stdscr.nodelay(True)  # Non-blocking keyboard capturing
    
    # Start backing DSP / Capturing engines
    analyzer.start()
    
    # Refresh rate limit
    target_fps = 30
    frame_interval = 1.0 / target_fps
    
    try:
        while analyzer.running:
            start_time = time.time()
            
            # Read keyboard inputs
            key = stdscr.getch()
            if key != -1:
                key_char = chr(key) if 32 <= key <= 126 else ""
                if key_char == "q":
                    break
                elif key_char == "+":
                    analyzer.adjust_threshold(0.0005)
                elif key_char == "-":
                    analyzer.adjust_threshold(-0.0005)
                elif key_char == "p" or key_char == " ":
                    analyzer.toggle_pause()
            
            # Retrieve threat-safe variables
            with analyzer.lock:
                samples = analyzer.current_samples.copy()
                magnitude = analyzer.current_magnitude.copy()
                freqs = analyzer.current_freqs.copy()
                note = analyzer.detected_note
                hz = analyzer.detected_hz
                cents = analyzer.cents_deviation
                rms = analyzer.rms_volume
                threshold = analyzer.threshold
            
            stdscr.erase()
            h, w = stdscr.getmaxyx()
            
            # Enforce minimum terminal size constraints
            if h < 24 or w < 60:
                safe_addstr(stdscr, 0, 0, "Terminal window too small! Please resize.", curses.A_BOLD)
                stdscr.refresh()
                time.sleep(0.1)
                continue
                
            # --- Draw Header bar ---
            stdscr.attron(curses.color_pair(4) | curses.A_REVERSE | curses.A_BOLD)
            header = f" Real-Time Fourier Pitch Analyzer  |  Mode: {analyzer.current_mode} "
            safe_addstr(stdscr, 0, 0, header.ljust(w - 1)[:w-1])
            stdscr.attroff(curses.color_pair(4) | curses.A_REVERSE | curses.A_BOLD)
            
            # Highlight Paused notification
            if analyzer.paused:
                safe_addstr(stdscr, 0, w - 10, " PAUSED ", curses.color_pair(5) | curses.A_REVERSE | curses.A_BOLD)
            
            # --- Panels Layout Geometry ---
            # Oscilloscope on Left, Spectrogram on Right
            panel_h = 10
            panel_w = (w - 6) // 2
            
            # Draw Labels
            safe_addstr(stdscr, 2, 2, "=== Oscilloscope (Time-Domain) ===", curses.color_pair(1) | curses.A_BOLD)
            safe_addstr(stdscr, 2, panel_w + 4, "=== Spectrogram (Freq-Domain) ===", curses.color_pair(2) | curses.A_BOLD)
            
            # Draw actual graph frames
            draw_waveform(stdscr, samples, 3, 2, panel_h, panel_w)
            draw_spectrum(stdscr, magnitude, freqs, 3, panel_w + 4, panel_h, panel_w)
            
            # --- Tuner Layout Section ---
            draw_tuner(stdscr, note, hz, cents, threshold, rms, 14, w)
            
            # --- Help / Keybind instructions footer ---
            footer = " [q] Quit  |  [+] / [-] Adjust Gate Threshold  |  [Space/p] Pause/Resume (File Mode) "
            safe_addstr(stdscr, h - 1, (w - len(footer)) // 2, footer, curses.color_pair(4) | curses.A_BOLD)
            
            stdscr.refresh()
            
            # Limit loop iteration execution to target FPS
            elapsed = time.time() - start_time
            if elapsed < frame_interval:
                time.sleep(frame_interval - elapsed)
                
    finally:
        # Cleanup audio resources safely upon exiting curses
        analyzer.stop()

def main():
    parser = argparse.ArgumentParser(description="Real-Time Pitch Analyzer (Fourier Transform / FFT)")
    parser.add_argument("-f", "--file", type=str, default=None,
                        help="Path to an audio file (MP3, WAV, etc.) to decode & play. If omitted, uses microphone.")
    parser.add_argument("-t", "--threshold", type=float, default=DEFAULT_NOISE_THRESHOLD,
                        help=f"Initial noise gate threshold (RMS volume). Default is {DEFAULT_NOISE_THRESHOLD}.")
    parser.add_argument("-r", "--rate", type=int, default=44100,
                        help="Target sample rate (Hz). Default is 44100.")
    parser.add_argument("-b", "--blocksize", type=int, default=2048,
                        help="Audio buffer block size. Default is 2048.")
                        
    args = parser.parse_args()
    
    # Prompt user to choose between Mic and Music file if no file was passed
    if args.file is None:
        music_dir = "/home/katzer/Music/Katzer/"
        print("=" * 60)
        print(" Fourier Pitch Analyzer - Modo de Inicialização")
        print("=" * 60)
        print(" 1. Capturar áudio em tempo real do Microfone (Padrão)")
        print(" 2. Escolher um arquivo de áudio da pasta Music/Katzer/")
        print("-" * 60)
        try:
            choice = input("Escolha a opção [1 ou 2] (pressione Enter para 1): ").strip()
        except KeyboardInterrupt:
            print("\nEncerrando...")
            sys.exit(0)
        
        if choice == "2":
            if os.path.exists(music_dir):
                # Scan for typical audio extensions
                valid_exts = (".mp3", ".wav", ".ogg", ".flac", ".mid")
                files = sorted([f for f in os.listdir(music_dir) if f.lower().endswith(valid_exts)])
                if files:
                    print("\nMúsicas disponíveis em ~/Music/Katzer/:")
                    for idx, filename in enumerate(files):
                        print(f"  {idx + 1}. {filename}")
                    print("-" * 60)
                    while True:
                        try:
                            num = input("Digite o número da música (ou 'q' para usar microfone): ").strip()
                            if num.lower() == 'q':
                                break
                            idx = int(num) - 1
                            if 0 <= idx < len(files):
                                args.file = os.path.join(music_dir, files[idx])
                                break
                            else:
                                print("Opção inválida.")
                        except ValueError:
                            print("Por favor, digite um número válido.")
                        except KeyboardInterrupt:
                            print("\nEncerrando...")
                            sys.exit(0)
                else:
                    print("\nNenhuma música encontrada em ~/Music/Katzer/. Usando microfone...")
                    time.sleep(1.5)
            else:
                print(f"\nDiretório {music_dir} não encontrado. Usando microfone...")
                time.sleep(1.5)

    if args.file and not os.path.exists(args.file):
        print(f"Error: Target file not found: {args.file}", file=sys.stderr)
        sys.exit(1)
        
    # Check if ffmpeg is available when running in file mode
    if args.file:
        try:
            subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            print("Error: 'ffmpeg' is required to play/decode audio files. Please install ffmpeg.", file=sys.stderr)
            sys.exit(1)
            
    # Instantiate central analyzer coordinator
    analyzer = PitchAnalyzer(
        file_path=args.file,
        sample_rate=args.rate,
        block_size=args.blocksize,
        threshold=args.threshold
    )
    
    print("Launching Fourier Terminal UI...")
    # Wrap curses screen loop execution safety
    curses.wrapper(run_curses_ui, analyzer)
    print("Analyzer shut down successfully.")

if __name__ == "__main__":
    main()
