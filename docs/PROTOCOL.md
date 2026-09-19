# Protocolo do Pichau Aurum V60 (`36ae:fe9c`)

Esta página documenta o que o OpenAurum sabe sobre o teclado. Tudo aqui foi **observado** no tráfego USB do app oficial da Pichau (Windows, capturado com `usbmon`/Wireshark numa máquina virtual em 2026-09-18) e depois confirmado olhando o teclado. Nada foi adivinhado.

## Onde falar

- O teclado tem várias interfaces USB HID. A de configuração é a **interface 2**: página de uso *vendor* `0xFF00`, relatórios de 64 bytes nos dois sentidos, **sem report ID**.
- No Linux, é o `/dev/hidrawN` cujo `HID_ID` é `0003:000036AE:0000FE9C` e cujo `HID_PHYS` termina em `/input2` (`protocol.find_hidraw()`).
- Escrevendo no hidraw, o primeiro byte é `00` (report ID vazio), seguido dos 64 bytes do comando completados com zeros.
- Toda resposta começa com `aa <comando>`.

## Comandos

```
  06 0a                         -> current mode at byte 7 (reply aa 0a ...; the
                                   reply is sometimes one byte shorter, so the
                                   settings come from 06 16)
  06 16 00 00 00 01 00 MM       -> stored settings of mode MM (reply aa 16 0b ...)
  06 0b 0b 00 00 01 00 MM BR SP X1 MO XX HH SS VV
                                -> switch to mode MM with these settings; the
                                   keyboard echoes them (aa 0b 01 ...)
     MM mode 0-16 (MODES)       BR brightness 0-4     SP speed 0-2 (0 = slowest)
     X1 01 once the app changed something (03 in factory settings)
     MO 1 = one color, 0 = RGB  XX 00 whenever the app sets a color
     HH SS VV color as HSV, each 0-255 (green = 55 ff ff)
     In one-color mode the firmware IGNORES BR (so did the Pichau app's slider)
     and lights the color at its V; with RGB BR works (0 = off). apply() turns
     a brightness level 0-10 into V (MONO_LEVELS, per mode).
     With MO=0 the HSV fields are ignored: the last one-color color stays stored.
     CustomLightning (16) ignores BR too (tested 2026-09-19, 4 -> 0: no change):
     openaurum.scenes dims the per-key colors on the PC instead (MONO_LEVELS[16]).
  06 13 3a LL HH                -> per-key colors, 0x38 bytes from address HHLL
                                   (reply aa 13 3a LL HH 00 00 00 + data); the app
                                   reads 0x000-0x150
  06 14 03 LL HH 00 00 00 RR GG BB
                                -> color of one key (CustomLightning), address
                                   = 3 * matrix index, plain RGB; echoed aa 14 01 ...
  06 08 3a LL HH                -> keymap (4 bytes per matrix index: 20 00 <HID
                                   usage> 00); KEY_INDEX below was read from it
  06 0f ff = factory reset, and firmware update: never sent from here
```

## Descobertas (testadas no teclado)

- **Brilho com a cor única:** o firmware **ignora o byte BR** e acende a cor no V (brilho) do HSV. O slider de brilho do app oficial também não fazia nada nesse modo. O OpenAurum escreve `V = V da cor × nível / 255` e mantém o BR coerente para quando o efeito for trocado para RGB.
- **LEDs não são lineares.** O V mínimo visível foi calibrado a olho em cada efeito (vermelho, velocidade 2). O nível 1 é esse mínimo, e os níveis 2 a 10 seguem uma escala geométrica até 255:

| Efeito | V mínimo | Níveis 1-10 |
|---|---|---|
| 1 Static | 12 | 12, 17, 24, 33, 47, 66, 92, 129, 182, 255 |
| 2 Breath | 35 | 35, 44, 54, 68, 85, 105, 132, 164, 205, 255 |
| 5 Stream | 35 | 35, 44, 54, 68, 85, 105, 132, 164, 205, 255 |
| 6 Bloom | 16 | 16, 22, 30, 40, 55, 74, 101, 138, 187, 255 |
| 7 UDWave | 16 | 16, 22, 30, 40, 55, 74, 101, 138, 187, 255 |
| 8 Cross | 16 | 16, 22, 30, 40, 55, 74, 101, 138, 187, 255 |
| 9 Rain | 12 | 12, 17, 24, 33, 47, 66, 92, 129, 182, 255 |
| 10 Meteor | 35 | 35, 44, 54, 68, 85, 105, 132, 164, 205, 255 |
| 11 TrigSpread | 16 | 16, 22, 30, 40, 55, 74, 101, 138, 187, 255 |
| 12 TrigSpread Reverse | 16 | 16, 22, 30, 40, 55, 74, 101, 138, 187, 255 |
| 13 TrigSingle | 12 | 12, 17, 24, 33, 47, 66, 92, 129, 182, 255 |
| 14 Sudoku | 12 | 12, 17, 24, 33, 47, 66, 92, 129, 182, 255 |
| 15 Tide | 35 | 35, 44, 54, 68, 85, 105, 132, 164, 205, 255 |
| 16 CustomLightning | 5 | 5, 8, 12, 19, 29, 44, 69, 106, 165, 255 |

- **RGB:** o BR funciona (0 = apagado). No *Stream*, o BR 1 já apaga.
- **Spin e ColorLoop** são só RGB (o app oficial desativa "cor única" neles).
- **CustomLightning (16)** também ignora o BR. O brilho das cenas é aplicado no PC, multiplicando a cor de cada tecla.
- Com `MO=0` (RGB), os campos HSV são ignorados, e a última cor única continua guardada. Para restaurar ajustes com exatidão, grava-se primeiro uma cópia em cor única e depois os ajustes RGB (`Keyboard.restore`).
- O teclado responde `XX=ff` para cor única e `08` para RGB, qualquer que seja o valor enviado.
- **Tudo fica na flash:** efeito, ajustes e a tabela de cores por tecla sobrevivem a desconectar o cabo (a tabela sobreviveu até ao reset de fábrica, que o OpenAurum nunca envia). Por isso nada é animado a partir do PC, e `Keyboard.push()` só regrava as teclas diferentes, conferindo depois com uma leitura.
- **Um programa por vez:** com dois processos mandando comandos juntos, o teclado **descarta** comandos (cerca de 25% num teste de estresse). Todo acesso passa por uma trava de arquivo (`$XDG_RUNTIME_DIR/openaurum.lock`), e cada comando é repetido até 3 vezes se não houver resposta.
- **Tempos:** `set_key` ≈ 7 ms de ida e volta; ler a tabela inteira ≈ 20 ms.
- **Endereços das teclas:** matriz de 6 × 21, lida do keymap (`06 08`). Por exemplo, Esc = 21, Q = 43, A = 64, Espaço = 111. A tabela completa está em `protocol.KEY_INDEX`.

## Comandos que o OpenAurum nunca envia

- `06 0f ff`: reset de fábrica.
- Atualização de firmware (o app oficial tem, e ela nunca foi usada nem capturada).
- Qualquer comando ou valor que não tenha aparecido no tráfego do app oficial.

Se você for contribuir, siga a mesma regra: capture o app oficial fazendo aquilo e só então reproduza.
