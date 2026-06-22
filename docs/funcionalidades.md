# Funcionalidades atuais

Este documento resume o comportamento atual do app a partir das telas de produto: Play, Learn e Sandbox. A regra central é manter a lógica de música, prática e pontuação fora da interface Qt. A UI escolhe arquivos, trilhas, regiões e dispositivos; os controladores recebem alvos, notas detectadas e tempos já normalizados.

## Play

Play é o modo de pontuação cronometrada. Ele usa uma trilha MIDI selecionada como partitura esperada e compara eventos de nota detectados contra a posição atual da música.

Features:

- Carregamento de músicas MIDI empacotadas em `assets/songs/midi`.
- Seleção explícita de trilha quando o MIDI tem mais de uma parte tocável.
- Conversão de eventos MIDI em alvos de pontuação. Notas que começam quase juntas viram um único alvo musical.
- Separação entre notas originais do MIDI e notas transpostas. A pontuação usa a expectativa ativa, mas preserva o material importado.
- Transposição por semitons para corrigir charts deslocados sem alterar o MIDI original.
- Timeline/piano roll com notas, medidas, trilhas e faixa de pitch para contexto visual.
- Controle de início, pausa, reinício e seek.
- Count-in de retomada antes do relógio de pontuação voltar a avançar.
- Pontuação por alvo com feedback `PERFECT`, `GOOD`, `MISS` ou neutro.
- Suporte a notas sustentadas: silêncio durante a duração de uma nota ainda não é erro; o miss ocorre quando o intervalo do alvo expira.
- Miss por nota tocada em silêncio esperado. Esse erro não consome o próximo alvo, então tocar cedo ainda permite acertar a nota no momento certo.
- Ignora eventos de baixa confiança na pontuação para reduzir falsos misses.
- Match incremental para alvos com várias notas, porque o detector atual emite eventos de nota individuais.

Lógica mais importante:

- O controller de Play não conhece Qt, arquivos MIDI nem microfone. Ele opera sobre `PlaySection`, `PlayTarget`, `TimeRegion` e eventos de nota MIDI.
- Um alvo passa quando a proporção de notas esperadas detectadas atinge `required_match_ratio`. Para alvos simples, a exigência normal é exata.
- `PERFECT` exige notas esperadas completas, confiança alta e timing dentro da janela curta. Quando o alvo passa, mas não cumpre todos esses critérios, o feedback é `GOOD`.
- O playhead é o contrato de tempo. A pontuação só considera o alvo cujo intervalo contém o playhead; notas fora desse intervalo contam como erro de silêncio esperado.

## Learn

Learn é o modo de estudo. Ele ensina uma parte selecionada de uma música sem transformar a prática em pontuação full-speed.

Features:

- Carregamento de MIDI real e fallback de demonstração quando não há material válido.
- Descoberta de MIDIs empacotados em `assets/songs/midi`, mantendo compatibilidade com assets antigos durante a migração.
- Seleção explícita da trilha alvo. Outras trilhas podem existir como contexto, mas só a trilha escolhida gera alvos de prática.
- Piano roll de estudo com eixo vertical de pitches MIDI, eixo horizontal de tempo, marcas de compasso e retângulos de notas.
- Visibilidade e audibilidade de trilhas separadas. Uma trilha pode estar visível e muda, ou oculta e audível.
- Seleção manual de região de prática por início e fim.
- Clamp da região para impedir seleção fora dos limites da música ou região colapsada.
- Wait Mode: a prática só avança quando o alvo atual é tocado corretamente.
- Sem avanço por relógio no modo atual. `update()` não pula alvos apenas porque o tempo passou.
- Checklist de notas detectadas, notas faltantes, acertos e erros por alvo.
- Agrupamento de notas próximas em um único gesto de prática.
- Suporte parcial a acordes: uma ou duas notas exigem match completo; alvos com três ou mais notas aceitam porcentagem mínima para não bloquear o estudo enquanto a detecção de acordes ainda é limitada.
- Transposição manual de -12 a +12 semitons.
- Validação de faixa de guitarra após transposição, com referência em E2 como limite inferior padrão.
- Sugestão de transposição quando a menor nota importada está logo abaixo da faixa padrão, sem aplicar automaticamente.

Lógica mais importante:

- Learn consome `LearnSection`, `PracticeRegion`, `LearnTarget` e eventos de nota. Arquivo MIDI, áudio e widgets são detalhes externos.
- Eventos MIDI com inícios dentro de 50 ms são agrupados porque o usuário percebe isso como um gesto musical, não como notas isoladas.
- A região de prática filtra alvos pelo início do alvo. Isso mantém a seleção previsível: o usuário escolhe onde os gestos começam.
- A transposição cria novos alvos com notas ativas corrigidas, preservando notas originais, tempos, durações e região selecionada.
- O app não escolhe automaticamente "a trilha certa" porque MIDIs podem conter baixo, melodia, solo e acompanhamento. Escolher errado com aparência de acerto seria pior do que exigir uma escolha explícita.

## Sandbox

Sandbox é o laboratório operacional de áudio. Ele responde "o que estou tocando?" e expõe evidência de espectro para calibrar o detector antes de usar esse sinal em fluxos de prática ou pontuação.

Features:

- Listagem de dispositivos de entrada de áudio via PortAudio/sounddevice.
- Abertura de stream ao vivo com taxa e canais controlados.
- FFT por frame com faixa útil de guitarra e picos ranqueados.
- Gráfico de espectro em tempo real com linha de pico dominante e provável fundamental.
- Painel de top peaks com frequência, nota, MIDI, magnitude relativa e marcação de harmônicos.
- Detecção de palhetada em nível de evento, separada da leitura frame a frame.
- Estado de detecção com ataque, captura curta e latch durante o decaimento da corda.
- Leitura estável de nota detectada por palhetada, mesmo quando os harmônicos mudam durante o sustain.
- Relatório de famílias de cordas soltas para E2, A2, D3, G3, B3 e E4.
- Classificação de cada família como ativa, incerta, sobreposição harmônica ou inativa.
- Diagnóstico de harmônicos 1x a 6x, incluindo evidência fraca para E2/A2.
- Compatibilidade de importação: `interfaces/sandbox/audio_pitch.py` continua existindo, mas delega para a fronteira compartilhada em `interfaces/audio/pitch.py`.

Lógica mais importante:

- O Sandbox mantém duas leituras diferentes: o FFT vivo, que pode mudar a cada frame, e a nota de palhetada, que representa o evento musical.
- A nota de palhetada é escolhida por persistência e coerência de série harmônica dentro de uma janela curta de captura.
- O relatório de cordas soltas não é reconhecimento de acorde. Ele mostra evidência por família de corda e conserva incerteza quando um pico pode ser explicado por mais de uma corda.
- Harmônicos altos sozinhos não ativam uma corda grave. A família precisa de âncora em 1x ou 2x, ou evidência independente suficiente, para evitar falsos positivos.

## Problemas encontrados e soluções implementadas

| Problema | Onde foi relevante | Solução implementada |
| --- | --- | --- |
| O protótipo antigo misturava CLI, captura de áudio, impressão e análise. | Sandbox | A política de detecção foi portada para uma fronteira própria sem Qt. A tela passou a cuidar só de dispositivo, controles e visualização. |
| A nota exibida mudava várias vezes durante uma única palhetada, porque cada frame de FFT podia ter um harmônico dominante diferente. | Sandbox | Foi criado um detector em nível de palhetada: captura uma janela curta, classifica o evento e mantém a nota latched durante o decaimento. |
| Uma única nota não bastava para inspecionar plucks com múltiplas cordas soltas. | Sandbox | Foi adicionado o relatório de famílias de cordas soltas, separado da nota principal, com status por corda e evidência harmônica. |
| Um E4 real podia ser interpretado como evidência falsa de A2 por coincidência com harmônicos inferiores. | Sandbox | Famílias graves passaram a exigir âncora em fundamental ou segundo harmônico forte; harmônicos 3x a 6x viraram evidência diagnóstica, não ativação por si só. |
| Harmônicos tardios podiam tornar uma corda "incerta" mesmo sem âncora física plausível. | Sandbox | O score foi calibrado para reduzir peso de 5x/6x e exigir âncora parcial ou múltiplos harmônicos baixos independentes. |
| E2 e A2 desapareciam em plucks de múltiplas cordas quando seus fundamentos estavam fracos. | Sandbox | O detector passou a aceitar âncoras fracas em 1x/2x apenas para E2/A2, preservando a regra conservadora contra ativações por harmônicos altos. |
| Uma corda alta tocada junto com uma corda grave podia ser suprimida porque seu fundamental também era harmônico da grave. | Sandbox | Foi adicionada recuperação de âncora co-presente: o fundamental sobreposto pode contar se houver suporte independente da própria família alta. |
| Learn precisava praticar trechos reais sem virar Play nem depender do diagnóstico experimental do Sandbox. | Learn | Learn foi criado como caso de uso separado, com alvos MIDI, seleção manual de região e consumo apenas de eventos de nota estáveis. |
| A escolha automática de trilha poderia ensinar a parte errada de um MIDI. | Learn, Play | A seleção da trilha alvo é explícita quando há múltiplas partes tocáveis. Trilhas não selecionadas podem dar contexto, mas não geram match. |
| A timeline inicial de Learn sugeria performance, não estudo. | Learn | Learn adotou piano roll com notas, pitches, medidas, visibilidade/audibilidade por trilha e região manual. A highway ficou reservada para Play. |
| MIDIs da internet podem estar deslocados em semitons, abaixo da faixa padrão de guitarra ou representar outra afinação/instrumento. | Learn, Play | A transposição corrige a expectativa ativa sem mutar o MIDI original. Learn também valida a faixa de guitarra e pode sugerir correção sem aplicar sozinho. |
| Silêncio durante uma nota sustentada era ambíguo para pontuação. | Play | Play passou a marcar miss só quando o intervalo do alvo expira; enquanto a nota sustentada ainda está ativa, silêncio permanece neutro. |
| Tocar antes da hora podia consumir ou invalidar o alvo seguinte. | Play | Pluck confiante durante silêncio esperado conta como miss separado, mas não consome o alvo futuro. |
