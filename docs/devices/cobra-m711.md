# Cobra M711 · kit S118

## Identificação e transporte

Referência da revisão USB `04d9:fc30`, `bcdDevice 0x0112`. Outros modelos ou revisões não têm compatibilidade confirmada. Existem cinco perfis com cinco níveis de DPI cada.

A configuração usa a interface HID 2, usage page `0xFFA0`, descoberta pelo sysfs e descritor. Não se deve fixar `/dev/hidrawN`. Feature Reports disponíveis, incluindo o ID: 2 (16 bytes), 3 (64), 4 (256), 5 (1024) e 6 (2048). A implementação usa o ID 2 pelos ioctls Linux `HIDIOCSFEATURE` e `HIDIOCGFEATURE`. O primeiro byte do buffer é o Report ID.

## Quadros e sessão

O quadro enviado tem 16 bytes. A tabela descreve o formato do protocolo, sem duplicar a implementação.

| Bytes | Conteúdo                                         |
| ----- | ------------------------------------------------ |
| 0     | Report ID `02`                                   |
| 1     | Operação                                         |
| 2–3   | Endereço little-endian ou parâmetros da operação |
| 4     | Quantidade de dados, quando aplicável            |
| 5–7   | Zeros                                            |
| 8–15  | Dados e preenchimento com zeros                  |

| Prefixo hexadecimal | Operação                                                 |
| ------------------- | -------------------------------------------------------- |
| `02 F5 00`          | Abrir sessão                                             |
| `02 F5 01`          | Encerrar sessão                                          |
| `02 F2`             | Solicitar leitura do endereço e quantidade especificados |
| `02 F3`             | Escrever até oito bytes no endereço especificado         |
| `02 F1 02 02`       | Aplicar DPI                                              |
| `02 F1 02 04`       | Aplicar iluminação                                       |

Uma leitura envia SET_FEATURE e recebe GET_FEATURE do ID 2, solicitando `8 + quantidade` bytes. A resposta contém `02 08 <eco baixo> <0x60 OU eco alto> <quantidade> 00 FA FA`, seguida dos dados. Para endereços ímpares, o eco é o endereço par anterior, mas os dados começam no endereço solicitado. Respostas curtas ou cabeçalhos diferentes são rejeitados.

A implementação limita leituras a 50 bytes conforme fontes externas; isso não comprova o máximo aceito pelo hardware. A sessão é encerrada também no tratamento de falhas. Envio bem-sucedido não confirma a configuração: é necessária releitura. Não há confirmação independente de gravação documentada.

## DPI

O perfil ativo fica em `0x002C`, um byte de 0 a 4. Os blocos de DPI têm 32 bytes.

| Perfil, índice do protocolo | Base     |
| --------------------------- | -------- |
| 0                           | `0x0042` |
| 1                           | `0x0102` |
| 2                           | `0x01B2` |
| 3                           | `0x0262` |
| 4                           | `0x0312` |

O byte 0 do bloco indica o nível ativo (0–4). O nível `i` começa em `base + 2 + 6 × i`: habilitado, código X, flag X, código Y, flag Y, preenchimento. A escrita altera somente os quatro bytes de X/Y. Os eixos são gravados iguais; níveis desabilitados ou assimétricos não são editáveis.

| DPI nominal permitido | Código, flag 0 |
| --------------------- | -------------- |
| 500                   | `0B`           |
| 800                   | `12`           |
| 1000                  | `16`           |
| 1200                  | `1B`           |
| 2000                  | `2E`           |
| 2400                  | `37`           |
| 3000                  | `45`           |
| 3600                  | `53`           |
| 5000                  | `73`           |

Todos esses códigos foram gravados e relidos no aparelho. Para 800, 1000 e 5000 houve também percepção do efeito pelo usuário. A precisão física não foi medida; os rótulos são nominais, baseados nas referências externas. Mínimo, máximo e incrementos livres não estão confirmados. Flag 1 e os anunciados 10.000 DPI não estão liberados.

F3 modifica a memória; a implementação envia também a aplicação de DPI. A necessidade isolada desse comando não está determinada. A configuração persiste após reconexão.

### Eventos do botão físico

A interface 2 emite Input Report de oito bytes `08 02 <nível> 00 00 00 00 00`. O nível corresponde ao byte 0 do bloco, entre 0 e 4, sem circular nos extremos. A leitura dos eventos é passiva, sem sessão. Outros eventos são ignorados. A aplicação acompanha o nível, mas não grava esse byte nem ativa perfis no hardware.

## Iluminação

Cada perfil `p` tem um registro de oito bytes em `0x0449 + 8 × p`.

| Deslocamento | Conteúdo                       | Suporte            |
| ------------ | ------------------------------ | ------------------ |
| 0–2          | R, G, B: 0–255 por canal       | Editável           |
| 3            | Modo 1                         | Efeitos suportados |
| 4            | Velocidade: 1 rápida a 8 lenta | Editável em onda   |
| 5            | Modo 2                         | Efeitos suportados |
| 6            | Brilho, observados 2 e 3       | Preservado         |
| 7            | Desconhecido, observado `80`   | Preservado         |

| Modo 1 / modo 2 | Efeito     | Comportamento                         |
| --------------- | ---------- | ------------------------------------- |
| `01 / 02`       | Estático   | Usa RGB; preserva velocidade          |
| `02 / 00`       | Onda       | Multicolorida, ignora RGB visualmente |
| `01 / 04`       | Respiração | Reconhecido, não editável             |

Não há onda monocromática validada. Os extremos de velocidade 1 e 8 foram observados visualmente; os intermediários seguem as referências do protocolo, sem avaliação visual individual. Modos desconhecidos são preservados até escolha explícita do usuário.

Somente o trecho necessário dos seis primeiros bytes é gravado. F3 altera os dados e `F1 02 04` aplica a iluminação. A releitura confirma o registro, não o efeito visual. A configuração persiste após reconexão. Editar um perfil inativo não muda a luz do perfil ativo.

## Garantias da integração

Edição e prévia são locais. Somente Salvar grava, após leitura, validação de conflitos e backup. Após aplicar, há releitura e comparação. Campos desconhecidos e configurações não editadas são preservados.

Não existe atomicidade entre gravações, repetição automática ou reversão automática. Falhas podem deixar estado parcial ou incerto, que precisa ser informado sem apresentar sucesso. Operações são serializadas no processo e entre processos do aplicativo.

## Referências

- [Linux hidraw](https://www.kernel.org/doc/html/latest/hid/hidraw.html): transporte e Feature Reports.
- [mouse_m908](https://github.com/dokutan/mouse_m908): layout, efeitos e rótulos nominais do M711.
- [OpenRGB](https://gitlab.com/CalcProgrammer1/OpenRGB): controlador Redragon e aplicação da iluminação.

Referências externas não comprovam compatibilidade com outras revisões. A implementação do projeto é própria e MIT; esta documentação não incorpora código dessas fontes.
