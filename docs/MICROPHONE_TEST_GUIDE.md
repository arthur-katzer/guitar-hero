# Microphone / Audio Interface Test Guide

Use this guide when testing with a real instrument.

## 1. Check Devices

Run:

```bash
python -m tools.mic_lab --list-devices
```

You need at least one input device. If the default device is `[-1, -1]`, Python
cannot see an input.

On Linux, also check:

```bash
pactl list sources short
arecord -l
```

## 2. Connect The Instrument

Preferred setup:

```text
instrument -> audio interface input -> computer
```

Set the interface input gain so the signal is strong but not clipping.

Avoid testing against a full song playing through speakers. The detector expects
mostly isolated instrument input.

## 3. Capture One Note

Run:

```bash
python -m tools.mic_lab --seconds 3 --mode fft --save-wav artifacts/mic_note.wav
```

Play one sustained note during the capture.

Expected output:

- detected note
- MIDI number
- peak frequency
- HPS frequency
- confidence
- RMS
- strongest FFT peaks

The captured file can be re-analyzed offline:

```bash
python -m tools.audio_lab --file artifacts/mic_note.wav --mode fft --window-ms 2000 --start-sec 0.5 --plot-out artifacts/mic_note_fft.png
```

## 4. Capture One Chord

Run:

```bash
python -m tools.mic_lab --seconds 3 --mode chord --save-wav artifacts/mic_chord.wav
```

Then inspect the saved audio:

```bash
python -m tools.audio_lab --file artifacts/mic_chord.wav --mode chord --window-ms 2000 --start-sec 0.5 --plot-out artifacts/mic_chord_chroma.png
```

## 5. If Capture Fails

Common causes:

- OS denied microphone permission.
- Audio interface is not selected as input.
- PipeWire/PulseAudio is not running.
- The terminal/session cannot access desktop audio.
- Input is muted or gain is too low.

Useful checks:

```bash
python -m tools.mic_lab --list-devices
pactl list sources short
arecord -l
```

## 6. If The Audio Sounds Weird

First capture a WAV anyway:

```bash
python -m tools.mic_lab --seconds 3 --mode fft --save-wav artifacts/mic_debug.wav
```

Then diagnose that WAV:

```bash
python -m tools.mic_lab --diagnose-wav artifacts/mic_debug.wav
```

The diagnostic output checks:

- RMS volume
- peak level
- clipping ratio
- DC offset
- duration
- sample rate

Interpretation:

```text
near-silence       -> wrong device, muted input, or gain too low
very quiet         -> raise input gain or move mic closer
clipping risk      -> lower input gain
high DC offset     -> input chain may need correction/filtering
usable for DSP     -> proceed to FFT/chord analysis
```

For an audio interface, also check the OS mixer:

```bash
pavucontrol
```

Recommended settings:

```text
Input device: your audio interface, not monitor/source playback
Input level: peaks around -12 dB to -6 dB, not red/clipping
Sample rate: 48000 Hz if available
Channel: mono input where the instrument is plugged in
```

## 7. What Counts As A Useful Test

Good test:

```text
single sustained note, isolated instrument, clean input, enough volume
```

Weak test:

```text
full chord with distortion, vocals/drums in background, quiet room mic, clipping
```

Record the WAV anyway. A bad capture is still useful evidence.
