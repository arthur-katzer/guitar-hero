# Guitar Hero em Python

## 1. Introdução
Este projeto é um protótipo de jogo de ritmo no estilo "Guitar Hero", desenvolvido inteiramente em Python para rodar diretamente no terminal. Através dele, você pode jogar mapas musicais criados a partir de arquivos MIDI utilizando o seu teclado. A proposta do projeto é ter uma base robusta que lê arquivos MIDI, converte-os em mapas de notas e oferece uma interface em terminal (`curses`) para que o jogador acompanhe a música de forma rítmica.

## 2. Pipeline
Esta seção descreve como as funcionalidades estão divididas e como os dados fluem, desde o arquivo musical até a tela do jogador.

### 2.1 Songs
O processamento das músicas acontece através do script `converter.py`. O seu papel é extrair todos os eventos de "note-on" de arquivos `.mid` localizados na pasta `songs/mid/`. Ele descobre quais são as notas musicais mais tocadas na música e as mapeia para teclas específicas do teclado (como as teclas `a`, `s`, `d`, `f`, etc). O resultado dessa conversão é um "chart" (mapa de notas) salvo em formato JSON dentro de `songs/json/`, que será lido posteriormente pelo jogo.

### 2.2 Game
A pasta `game/` contém as engrenagens principais do jogo, com as responsabilidades separadas em dois arquivos cruciais:
- **`engine.py`**: É o núcleo lógico. Ele é encarregado de cuidar do relógio interno, da janela de acertos (hit window), da contabilização de pontos, multiplicadores, combos e falhas. Este arquivo também é o responsável por invocar o processo que toca o arquivo MIDI em sincronia com o jogo (utilizando `fluidsynth`).
- **`interface.py`**: É o módulo de visualização e captura de inputs (usando a biblioteca `curses`). Ele desenha na tela do terminal as pistas com as notas caindo em tempo real e se comunica com a `engine` para verificar se a tecla apertada pelo usuário corresponde a uma nota válida na linha do tempo.

### 2.3 Main
O arquivo `main.py` é o maestro que junta todas as partes. É o ponto de entrada da aplicação que gerencia a interface inicial, permitindo ao usuário escolher uma das músicas disponíveis na pasta `songs/json/`. A partir disso, ele inicia o modo `curses`, injeta as configurações na `Engine`, carrega os gráficos pela `CursesUI` e mantém o "game loop" vivo, repassando os comandos do teclado e atualizando o estado do jogo até a música acabar ou o jogador sair.

## 3. Not-now
A pasta `not-now/` armazena os protótipos e provas de conceito para o próximo nível do projeto. Ela contém arquivos como `audio_capture.py`, `chord_detector.py` e `chord_templates.py`. Essas ferramentas capturam áudio e realizam análises espectrais para detectar acordes e notas musicais reais. Por enquanto, essa lógica está separada e serve apenas como laboratório, mas desempenhará o papel mais importante nas futuras iterações.

## 4. Moving Forward
Para o futuro, a principal evolução do projeto será a integração com instrumentos reais. Utilizando a base já construída e os protótipos da pasta `not-now`, o jogo vai escutar o áudio capturado por um microfone e identificar os acordes que estão sendo tocados por um violão ou guitarra real do outro lado. 

A ideia é manter o formato atual como um **"keyboard mode"** (modo teclado) e introduzir um novo **"instrument mode"** (modo instrumento) muito mais imersivo. Isso exigirá a expansão das mecânicas atuais para mapear e processar fielmente a complexidade dos acordes tocados por instrumentos físicos.
