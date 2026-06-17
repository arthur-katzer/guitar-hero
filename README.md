# Guitar Hero em Python

## 1. Introdução
Este projeto é um protótipo de jogo de ritmo no estilo "Guitar Hero", desenvolvido inteiramente em Python para rodar diretamente no terminal. Através dele, você pode jogar mapas musicais criados a partir de arquivos MIDI utilizando o seu teclado. A proposta do projeto é ter uma base robusta que lê arquivos MIDI, converte-os em mapas de notas e oferece uma interface em terminal (`curses`) para que o jogador acompanhe a música de forma rítmica.

O próximo marco do projeto é transformar o protótipo em uma plataforma de aprendizado e validação para detecção de notas reais. Isso significa que o código novo vem acompanhado de documentação, testes e checkpoints humanos: ninguém avança para integração com o jogo sem antes conseguir explicar o que o detector está fazendo.

## 2. Pipeline
Esta seção descreve como as funcionalidades estão divididas e como os dados fluem, desde o arquivo musical até a tela do jogador.

### 2.0 Project Layout

```text
audio/                  DSP puro e carregamento de audio
docs/                   trilha de aprendizado, checkpoints e roadmaps
experiments/            prototipos antigos e provas de conceito
game/                   engine e interface curses do jogo
samples/                arquivos de audio usados nos labs
songs/                  MIDIs e charts JSON
tests/                  testes automatizados
tools/                  CLIs e utilitarios executaveis com python -m
main.py                 entrada do jogo em modo teclado
requirements.txt        dependencias Python do projeto
```

### 2.1 Songs
O processamento das músicas acontece através do script `converter.py`. O seu papel é extrair todos os eventos de "note-on" de arquivos `.mid` localizados na pasta `songs/mid/`. Ele descobre quais são as notas musicais mais tocadas na música e as mapeia para teclas específicas do teclado (como as teclas `a`, `s`, `d`, `f`, etc). O resultado dessa conversão é um "chart" (mapa de notas) salvo em formato JSON dentro de `songs/json/`, que será lido posteriormente pelo jogo.

### 2.2 Game
A pasta `game/` contém as engrenagens principais do jogo, com as responsabilidades separadas em dois arquivos cruciais:
- **`engine.py`**: É o núcleo lógico. Ele é encarregado de cuidar do relógio interno, da janela de acertos (hit window), da contabilização de pontos, multiplicadores, combos e falhas. Este arquivo também é o responsável por invocar o processo que toca o arquivo MIDI em sincronia com o jogo (utilizando `fluidsynth`).
- **`interface.py`**: É o módulo de visualização e captura de inputs (usando a biblioteca `curses`). Ele desenha na tela do terminal as pistas com as notas caindo em tempo real e se comunica com a `engine` para verificar se a tecla apertada pelo usuário corresponde a uma nota válida na linha do tempo.

### 2.3 Main
O arquivo `main.py` é o maestro que junta todas as partes. É o ponto de entrada da aplicação que gerencia a interface inicial, permitindo ao usuário escolher uma das músicas disponíveis na pasta `songs/json/`. A partir disso, ele inicia o modo `curses`, injeta as configurações na `Engine`, carrega os gráficos pela `CursesUI` e mantém o "game loop" vivo, repassando os comandos do teclado e atualizando o estado do jogo até a música acabar ou o jogador sair.

## 3. Experiments
A pasta `experiments/` armazena os protótipos e provas de conceito para o próximo nível do projeto. Ela contém o analisador em tempo real antigo (`experiments/pitch_analyzer.py`), o smoke test de `librosa` (`experiments/librosa_smoke.py`) e os primeiros protótipos de detecção de acordes em `experiments/chord_detection/`. Essa lógica é útil como laboratório, mas não é o caminho principal do MVP atual.

## 4. Audio-to-Note Lab

A pasta `audio/` contém a base nova para análise offline de áudio:

- `audio/dsp.py`: funções puras de DSP que recebem arrays NumPy e retornam resultados estruturados.
- `audio/io.py`: carregamento de arquivos WAV/MP3/FLAC/OGG para arrays de áudio. WAV usa Python diretamente; outros formatos exigem `ffmpeg`.
- `tools/audio_lab.py`: CLI de aprendizado para resumir áudio, executar FFT/HPS e gerar uma timeline de notas detectadas.

Comandos principais:

```bash
python -m tools.audio_lab --file samples/Exploder.mp3 --mode summary
python -m tools.audio_lab --file samples/Exploder.mp3 --mode fft --window-ms 200
python -m tools.audio_lab --file samples/Exploder.mp3 --mode notes --window-ms 100 --hop-ms 50
python -m unittest discover -s tests
```

## 5. Learning Path

Leia e execute os documentos nesta ordem:

1. `docs/01_audio_as_arrays.md`
2. `docs/02_fft_and_frequency.md`
3. `docs/03_pitch_detection.md`
4. `docs/04_midi_matching_plan.md`
5. `docs/05_confidence_metric.md`
6. `docs/06_chord_detection.md`
7. `docs/MICROPHONE_TEST_GUIDE.md`
8. `docs/FINAL_PRODUCT_GUIDE.md`
9. `docs/ROADMAP_STATUS.md`
10. `docs/ARTICLE_SKELETON.md`
11. `docs/checkpoints.md`

Cada checkpoint exige uma explicação humana em linguagem simples. O padrão do projeto é: rodar o comando, observar a saída, escrever o entendimento, só então avançar.

## 6. Moving Forward
Para o futuro, a principal evolução do projeto será a integração com instrumentos reais. Utilizando a base já construída e os protótipos da pasta `experiments/`, o jogo vai escutar o áudio capturado por um microfone e identificar os acordes que estão sendo tocados por um violão ou guitarra real do outro lado. 

A ideia é manter o formato atual como um **"keyboard mode"** (modo teclado) e introduzir um novo **"instrument mode"** (modo instrumento) muito mais imersivo. Isso exigirá a expansão das mecânicas atuais para mapear e processar fielmente a complexidade dos acordes tocados por instrumentos físicos.

## 7. Chroma MVP: audio performance vs MIDI reference

This MVP compares a normal audio file, such as an MP3 recorded from guitar,
against a reference MIDI file. It does not try to solve perfect guitar
transcription. Instead, both inputs are converted into chroma features: 12
pitch-class bins (`C`, `C#`, `D`, ... `B`) over time. This is better for rough
chord/harmony matching than raw FFT peak frequency.

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

If MP3 loading fails, install `ffmpeg` and make sure it is available on `PATH`.
Tracktion Waveform can be used to record/export audio, but the analysis scripts
only need normal audio files and MIDI files.

Offline comparison:

```bash
python compare_audio_to_midi.py --audio samples/song.mp3 --midi songs/mid/reference.mid --out artifacts/report.csv
```

Convert MP3 to WAV first when you want a stable local smoke artifact:

```bash
python mp3_to_wav.py "samples/505 - Arctic Monkeys ｜ Fingerstyle Guitar ｜ TAB + Chords + Lyrics.mp3" artifacts/505.wav --overwrite
python compare_audio_to_midi.py --audio artifacts/505.wav --midi songs/mid/arctic_monkeys-505.mid --out artifacts/505_chroma_report.csv
```

Use DTW when the audio and MIDI are musically similar but not perfectly aligned:

```bash
python compare_audio_to_midi.py --audio samples/song.mp3 --midi songs/mid/reference.mid --out artifacts/report.csv --alignment dtw
```

Outputs:

- CSV report with `time_audio_sec`, `time_midi_sec`, `similarity`, `status`,
  `audio_pitch_classes`, and `midi_pitch_classes`.
- PNG similarity plot next to the CSV, unless `--no-plot` is passed.
- Terminal summary with mean cosine similarity and timeline regions such as
  likely match, weak match, and mismatch.

Useful options:

```bash
python compare_audio_to_midi.py --help
python compare_audio_to_midi.py --audio samples/song.mp3 --midi songs/mid/reference.mid --alignment fixed
python compare_audio_to_midi.py --audio samples/song.mp3 --midi songs/mid/reference.mid --alignment dtw --dtw-max-cells 20000000
```

Live microphone/audio-interface chroma test:

```bash
python live_chroma_test.py
```

The script asks for target pitch classes. For example, `0,4,7` means C major
pitch classes. You can also type note names like `C,E,G`.

Helpful live-test commands:

```bash
python live_chroma_test.py --list-devices
python live_chroma_test.py --target 0,4,7 --device 1
python live_chroma_test.py --target C,E,G --once
```

Live single-note trainer:

```bash
python live_note_trainer.py --list-devices
python live_note_trainer.py --first-note A4 --notes C4,D4,E4,F4,G4,A4,B4,C5
```

For a first smoke test with the `A4.mp3` file playing from your phone speaker,
limit the pool to A4:

```bash
python live_note_trainer.py --notes A4 --hold-seconds 0.6
```

The trainer gives one point after the target note is detected continuously for
the configured hold time. With multiple notes, it uses shuffled rounds so the
same target is not requested twice in a row.

If the trainer keeps showing `Silence`, scan the input devices while playing
`A4.mp3` from your phone:

```bash
python mic_device_scan.py --devices 1,2,7,8,14,15 --seconds 2
```

Then use the device with the highest `rms`/`peak`:

```bash
python live_note_trainer.py --device 14 --notes A4 --threshold 0.001 --hold-seconds 0.6
```

To test audio played by the computer itself, such as YouTube, use Windows
Stereo Mix / `Mixagem estéreo`:

```bash
python mic_device_scan.py --system-audio --seconds 2
python live_note_trainer.py --system-audio --notes A4 --threshold 0.001 --hold-seconds 0.6
```

If auto-detection fails but `--list-devices` shows `Mixagem estéreo`, pass it
directly. In the current scan it appeared as device `19`:

```bash
python mic_device_scan.py --devices 19 --seconds 2
python live_note_trainer.py --device 19 --notes A4 --threshold 0.001 --hold-seconds 0.6
```

Definition of done for this prototype:

- An MP3 and MIDI of the same short passage should score higher than an
  unrelated MIDI.
- The offline script produces a CSV and timeline of match/weak/mismatch regions.
- The live script can roughly detect whether a captured note/chord matches a
  target pitch-class set.
