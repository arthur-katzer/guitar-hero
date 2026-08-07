# Guitar Hero

Aplicativo desktop em Python/PySide6 para visualizar músicas MIDI, praticar
partes de guitarra e inspecionar sinal de áudio ao vivo.

## Abrir a interface

Na raiz do repositório, execute:

```bash
python -m interfaces.gui.app
```

Esse é o ponto de entrada da aplicação. O menu abre os três modos atuais:

- **Tocar**: selecione uma música MIDI empacotada, veja todas as trilhas no
  piano roll e use Play/Pause/Reiniciar. O playhead acompanha a reprodução.
- **Prática**: escolha uma trilha e uma região MIDI para praticar; a tela usa
  a entrada de áudio para detectar as notas tocadas.
- **Análise**: laboratório de entrada de áudio, espectro e diagnóstico de
  palhetadas/notas.

## Instalação

Requer Python 3.10 ou superior.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m interfaces.gui.app
```

No Windows PowerShell, ative o ambiente com:

```powershell
.venv\Scripts\Activate.ps1
```

## Reprodução MIDI em Tocar

O modo **Tocar** sempre carrega e exibe os MIDIs em `assets/songs/midi/`.
Para também ouvi-los, o backend padrão exige:

- o executável `fluidsynth` disponível no `PATH`;
- o soundfont General MIDI em `/usr/share/soundfonts/FluidR3_GM.sf2`;
- uma saída de áudio compatível com PulseAudio.

Se o backend não puder iniciar, a tela exibe o erro e continua permitindo
inspecionar o piano roll. As músicas e a visualização não dependem de um
microfone.

## Áudio e diagnóstico

Prática e Análise precisam de um dispositivo de entrada reconhecido pelo
`sounddevice`/PortAudio. Para consultar a ferramenta de diagnóstico pelo
terminal:

```bash
python -u audio_pitch_detector.py --help
```

`ffmpeg` é opcional: ele melhora o visualizador decorativo do menu. Sem ele,
a interface continua abrindo com uma aparência de fallback.

## Testes

Da raiz do repositório:

```bash
PYTHONPATH=. pytest -q
```

## Estrutura relevante

- `interfaces/gui/`: ponto de entrada e janela principal.
- `interfaces/play/`: visualizador e transporte MIDI.
- `interfaces/learn/`: prática orientada por MIDI.
- `interfaces/sandbox/`: análise do sinal de áudio.
- `interfaces/audio/`: parsing/renderização MIDI e entrada de áudio.
- `assets/songs/midi/`: músicas MIDI empacotadas.
