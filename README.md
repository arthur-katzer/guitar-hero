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
