# Fase 1 — inspeção do ambiente

Data: 2026-09-16. A inspeção não alterou a configuração do Qwen, o llama.cpp,
serviços ou aplicações existentes. Depois da autorização para importar skills
e trabalhar no projeto, foram criados este relatório, o README e o `.gitignore`.

## Evidências locais

| Item | Resultado |
| --- | --- |
| Sistema | Arch Linux, kernel 7.1.8-arch1-3, x86_64 |
| CPU | Ryzen 5 4600G, 6 núcleos / 12 threads |
| RAM total | 16.156.912 KiB, aproximadamente 15,41 GiB |
| RAM disponível | 7,8 GiB na primeira amostra; 9,26 GiB na última |
| Swap | zram de 4 GiB; 2,6 GiB ocupados inicialmente; aproximadamente 1,71 GiB na última amostra |
| GPU detectada pelo llama.cpp | AMD Radeon RX 580 2048SP, RADV POLARIS10 |
| VRAM total | 8.192 MiB |
| VRAM livre | 6.787 MiB na enumeração Vulkan; aproximadamente 6.897 MiB na última amostra sysfs |
| Disco disponível | aproximadamente 153 GiB na partição do projeto |
| Python | 3.14.7 |
| llama-server | 0.4.1-dev, build 10988, commit 9f31776c3 |
| Checkout llama.cpp | b10985-3-g9f31776c3; último commit de 2026-09-15 |
| Build | Release, GGML_VULKAN=ON, GGML_NATIVE=ON, LLAMA_BUILD_SERVER=ON |
| Modelo | Qwen3.8-27B-UD-IQ4_XS.gguf, existente |
| Tamanho do GGUF | 14.252.845.984 bytes, 13,274 GiB |
| Processos Qwen | nenhum llama-cli, llama-server ou llama-bench encontrado na inspeção fora do sandbox |
| Porta 8080 | não constava entre as portas TCP em escuta |
| 9Router | pacote 0.5.75 instalado; diretório `~/.9router` existente |

Os valores de memória variaram durante a inspeção. São amostras do sistema,
não consumo medido com o Qwen em inferência. O espaço de swap usado, sozinho,
não demonstra que exista swapping ativo ou identifica seu causador.

A primeira enumeração Vulkan dentro do sandbox mostrou nenhum dispositivo, e
a consulta de portas falhou com `Operation not permitted`. Repetidas fora do
sandbox, com autorização, ambas funcionaram. Isso não era falha do backend.

O comando `git status` neste diretório retornou `not a git repository`; a mera
presença da entrada `.git` não confirmou um repositório utilizável. Nenhum
`git init`, commit ou alteração em metadados Git foi executado.

## Configuração de referência

Informada pelo usuário, com flags confirmadas no `--help` do binário instalado:

```bash
cd ~/llama.cpp
./build/bin/llama-cli \
  -m '/home/polar/.cache/huggingface/hub/models--unsloth--Qwen3.8-27B-GGUF/snapshots/4ca720788d1e01f1bff70c033e0d0028fd02e502/Qwen3.8-27B-UD-IQ4_XS.gguf' \
  -ngl 32 -t 10 -b 256 -ub 256 -c 8192 -fa off
```

Não havia processo ativo que permitisse confirmar seu uso atual. O arquivo
`~/llama.cpp/qwen-crash.log` estava vazio, portanto não há diagnóstico de crash
baseado nesse arquivo.

## Metadados do modelo

O cabeçalho GGUF foi lido sem carregar os tensores:

- Nome: `Qwen3.8-27B`.
- Arquitetura interna: `qwen35`. Esse identificador não contradiz, por si só,
  o nome do modelo; identifica a implementação de arquitetura usada.
- GGUF versão 3; 866 tensores; 50 entradas de metadados.
- `block_count=65`, `embedding_length=5120`.
- `attention.head_count=24`, `attention.head_count_kv=4`.
- `attention.key_length=256`, `attention.value_length=256`.
- `full_attention_interval=4`, além de metadados SSM.
- Contexto declarado: 262.144 tokens. Isso não comprova capacidade de executar
  esse contexto no hardware disponível, nem qualidade em contextos longos.

## Estimativas de memória, não benchmarks

Executado o `llama-fit-params --fit-print on` instalado, com acesso real à GPU,
mantendo `-ngl 32 -t 10 -b 256 -ub 256 -fa off` e `-np 1`. Apenas `-c` variou.
O modo `--fit-print` estima a configuração fornecida; não inicia inferência e
não aplica os parâmetros ajustados de outro modo do estimador.

Todas as execuções terminaram com código zero. Saída em MiB:

| Contexto | Pesos GPU | Contexto GPU | Compute GPU | Total GPU | Pesos host | Contexto host | Compute host | Total host |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8.192 | 6.796 | 324 | 325 | 7.445 | 6.451 | 337 | 25 | 6.813 |
| 12.288 | 6.796 | 452 | 376 | 7.624 | 6.451 | 465 | 29 | 6.945 |
| 16.384 | 6.796 | 580 | 524 | 7.900 | 6.451 | 593 | 33 | 7.077 |

Essas somas são estimativas dos buffers do llama.cpp. Não são picos medidos de
RSS, VRAM ou RAM do sistema; não incluem todos os custos do servidor, driver,
cache de arquivos, aplicações e snapshots de contexto.

Com 6.787 MiB de VRAM livre, até 8K supera a memória disponível em 658 MiB.
A última amostra também permaneceu abaixo da estimativa de 8K. Não foi
executada uma carga do modelo sob essa condição. Alocação pode falhar ou o
driver pode usar memória compartilhada, com impacto a medir.

Passar de 8K para 12K acrescenta aproximadamente 132 MiB no host e 179 MiB na
GPU nesta estimativa. Passar de 8K para 16K acrescenta 264 MiB no host e 455 MiB
na GPU. Tokens/s e qualidade permanecem desconhecidos. Não foi aplicado
aumento de contexto.

## Mais contexto, mais saída e mais velocidade

São métricas diferentes. O contexto precisa acomodar o prompt formatado,
histórico selecionado, raciocínio gerado quando aplicável e resposta. Um
limite de saída maior não aumenta a janela de contexto nem os tokens/s.

Exemplo de orçamento futuro para 8.192: reservar 2.048 tokens de saída e 256
de margem deixa até 5.888 para a entrada já formatada. Será necessário medir
com o tokenizer e o template do servidor, não apenas contar caracteres.

Para programação, a qualidade deverá ser avaliada por testes e requisitos
cumpridos. Nenhum resultado de qualidade foi medido nesta fase.

## Migração de teste para llama-server

Proposta ainda não executada:

1. Usar `llama-server`, conservando modelo, 32 camadas, 10 threads, batches 256,
   contexto 8.192 e Flash Attention desligado.
2. Adicionar `-np 1 --host 127.0.0.1 --port 8080`: uma sessão para o MVP e acesso
   apenas por loopback. Um único slot evita custos de múltiplas sessões e
   facilita atribuir o contexto à requisição.
3. RAM: overhead HTTP e caches ainda não medidos; um slot limita multiplicação
   de estados. A estimativa host acima não é o pico do servidor.
4. VRAM: preservar os principais parâmetros conserva a referência de buffers;
   validar valores reais no log de inicialização. Não há promessa de redução.
5. Tokens/s: sem ganho presumido. Medir prompt processing, generation e tempo
   total separadamente, com aquecimento identificado.
6. Reversão: encerrar apenas o servidor de teste e executar o comando original.
   Nenhuma configuração persistente do llama.cpp será substituída.

Detalhes confirmados no binário instalado: `-np` é automático por padrão;
`--cache-ram` possui limite padrão de 8.192 MiB (limite, não alocação imediata);
`--ctx-checkpoints` tem padrão 32; `--fit` ajusta argumentos não definidos.
Esses defaults precisarão ser considerados antes de uma sessão longa em
16 GiB de RAM. Qualquer redução desses limites deve ser documentada antes.

O servidor suporta `/health`, `/props`, `/tokenize` e
`/v1/chat/completions`. A documentação local descreve `usage` e `timings`,
incluindo `prompt_per_second`, `predicted_per_second` e `cache_n`.
Fonte principal desta inspeção: ajuda e código da versão instalada; referência
geral: [documentação oficial do servidor](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

## Skills importadas

Origem: `~/.claude/skills`. Destino: `~/.agents/skills`.

- 298 diretórios com `SKILL.md` encontrados.
- 289 diretórios copiados; nove existentes preservados, incluindo Caveman.
- 448 arquivos novos conferidos por SHA-256.
- Verificação final: todos os 551 arquivos das 298 skills coincidem com a origem.
- Nenhum hook, MCP, credencial, comando exclusivo do Claude ou script de
  instalação foi executado como parte da cópia.

Copiar as instruções não instala dependências externas nem garante que
comandos exclusivos do Claude funcionem no Codex. As dependências serão
avaliadas por skill ao utilizá-la. As novas skills poderão ser descobertas
no próximo turno; Caveman já estava disponível nesta sessão.

## Próximas fases e critérios

1. Liberar margem de VRAM ou avaliar uma variante explicitamente documentada;
   não encerrar aplicações do usuário automaticamente.
2. Fase 2: carregar uma única instância, conferir 8.192 por slot, obter saúde
   positiva e resposta mínima via HTTP.
3. Fase 3: medir baseline local, com tokens, tempos e teste de qualidade.
4. Fase 4: identificar endpoint e modelos do 9Router, ler credenciais sem
   imprimi-las e fazer chamada mínima. Apenas sua instalação foi identificada.
5. Fases 5–9: implementar clientes, orquestração, memória, contexto, roteamento
   e métricas somente após comprovar os componentes isolados.
6. Fase 10: comparar LOCAL e HYBRID em tarefas simples, médias e complexas,
   usando os mesmos critérios de qualidade e registrando chamadas, tokens,
   processamento local efetivo e tempos. Não presumir benefício do híbrido.
