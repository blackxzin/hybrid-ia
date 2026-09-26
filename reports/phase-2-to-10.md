# Fases 2–10 — MVP local-first e benchmark

Data: 2026-09-16.

## Fase 2 — llama-server com Qwen

O `llama-server` 0.4.1-dev (build 10988, commit `9f31776c3`) respondeu em `127.0.0.1:8080`. A configuração em execução foi `-ngl 26 -t 10 -b 256 -ub 256 -c 8192 -fa off -np 1 --cache-ram 128 --ctx-checkpoints 1 --metrics --perf --alias local-qwen`.

Foi mantido um slot com contexto de 8.192 tokens. As 26 camadas na GPU são uma variante temporária que coube na VRAM disponível; não substituem o comando de referência do usuário. O servidor permaneceu ativo ao final dos testes.

## Fase 3 — baseline local

| Teste | Entrada | Saída | Prompt | Geração | Total | Resultado |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `OK` inicial | 18 | 2 | 3,10 s (5,80 tok/s) | 0,54 s (1,85 tok/s) | 3,65 s | passou |
| `clamp` inicial | 46 | 41 | 4,06 s (11,32 tok/s) | 19,72 s (2,03 tok/s) | 23,79 s | 9 casos passaram |
| smoke do MVP | 265 | 2 | 10,73 s (24,70 tok/s) | 0,45 s (2,24 tok/s) | 11,19 s | passou |

O desempenho de geração observado ficou próximo de 1,8–2,25 tokens/s. A API não aumentou os tokens/s; ela fornece métricas e permite ao orquestrador reduzir trabalho supérfluo.

## Fase 4 — 9Router

- 9Router: versão `0.5.75`, endpoint local `http://127.0.0.1:20128/v1`.
- A configuração local exige chave de acesso. A chave foi lida apenas para a validação em memória, nunca exibida, gravada no projeto ou incorporada no código.
- `GET /v1/models` retornou 97 modelos/combinações.
- O teste direto com `gh/gpt-5-mini` devolveu HTTP 503.
- O teste mínimo com a combinação `awe` passou inicialmente: o 9Router escolheu `gpt-5.6-terra-review`, retornou `OK`, cinco tokens de saída, em 1,113 s pelo cliente Python. A combinação também retornou HTTP 503 em outro teste autenticado; por isso o padrão atual usa o modelo direto `cx/gpt-5.6-terra-review`, validado com `OK` em 1,668 s.

O servidor temporário do 9Router foi encerrado depois dos testes. Para uso do MVP, o usuário precisa iniciar seu 9Router local e definir `ROUTER9_API_KEY` no ambiente ou em `.env` ignorado pelo Git.

## Fases 5–9 — MVP implementado

| Componente | Implementação |
| --- | --- |
| Clientes | `providers/local_qwen.py` usa `/v1/chat/completions`, `/apply-template` e `/tokenize`; `providers/router9.py` usa API OpenAI-compatible e só aceita chave de ambiente. |
| Roteador | `core/router.py`: SIMPLE fica LOCAL; MEDIUM vira HYBRID e COMPLEX vira EXPERT somente com especialista configurado. FAST exige modo explícito. |
| Orquestrador | HYBRID faz análise curta local, crítica remota e final local. EXPERT faz plano remoto, implementação local, revisão remota e correção local quando há problemas. |
| Contexto | `core/context_manager.py` combina memória estruturada, até oito mensagens recentes e contexto auxiliar. Estimativa conservadora precede a contagem exata do `llama-server`; geração é bloqueada se o orçamento seguro for excedido. |
| Memória | `data/technical-memory.json`, local e ignorada pelo Git: requisitos, decisões, erros, arquivos, comandos, testes, TODOs e restrições. |
| Privacidade | Nenhum arquivo sai por padrão. `--allow-external-files` e `--external-file` exigem seleção explícita; o sanitizador bloqueia caminhos privados, `.env`, `.git`, certificados e chaves, além de redigir padrões de segredo no pedido e nos arquivos. |
| Métricas | `logs/runs.jsonl`, local e ignorado: modelos, modo, tokens, tempos, chamadas externas, contexto, velocidades do llama.cpp, redações e erros seguros. |

Os 11 testes unitários passaram: classificação, memória, compactação, sanitização, privacidade do pedido e papéis HYBRID/EXPERT. Não há automação de terminal, Git ou aplicação de patches neste MVP; essa é a próxima fronteira de escopo seguro.

## Fase 10 — benchmark LOCAL vs HYBRID

Arquivo bruto: [benchmark-20260916-202334.json](benchmark-20260916-202334.json). Tarefas sintéticas, nenhum arquivo do projeto enviado, `LOCAL_RESPONSE_RESERVE_TOKENS=180`, temperatura zero. HYBRID usou `awe`, que roteou para `gpt-5.6-terra-review`; o MVP atual usa esse modelo diretamente para evitar a instabilidade observada na combinação.

| Categoria | LOCAL total | HYBRID total | Delta | Tokens locais LOCAL/HYBRID | Chamadas externas | Qualidade verificada |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Simples: `clamp` | 27,27 s | 89,45 s | +62,18 s | 145 / 312 | 1 | ambos passaram 4 casos |
| Média: `average` para iteráveis | 91,94 s | 157,62 s | +65,69 s | 228 / 463 | 1 | ambos passaram lista, gerador e vazio |
| Complexa: validação de caminho | 96,02 s | 176,35 s | +80,33 s | 317 / 674 | 1 | ambos incompletos com teto de 180 tokens |

Nos três casos, HYBRID foi pior em tempo total e aumentou o trabalho do Qwen local. As chamadas externas foram rápidas (2,44 s; 4,62 s; 6,17 s), mas o custo da análise local curta e do contexto de revisão sobrepôs qualquer benefício.

Os dois resultados complexos não são aceitáveis como implementação final: LOCAL terminou antes de implementar a validação e HYBRID deixou uma docstring sem fechar. O teste confirma que 180 tokens é insuficiente para este escopo; ele não é uma medida de que LOCAL ou HYBRID tenha resolvido a tarefa complexa.

O arquivo bruto mostra `task_class=medium` para a tarefa simples e `simple` para a complexa, pois o classificador inicial tratava `ValueError` como "erro" e a tarefa complexa não possuía um termo forte de arquitetura/segurança. A fonte do benchmark manteve as categorias corretas, e a falsa detecção por `ValueError` foi corrigida após a execução. Isso não altera tempos, tokens ou respostas medidas.

## Conclusão operacional

Para esta máquina e os prompts medidos, use LOCAL para tarefas simples e médias. Não ative HYBRID por padrão para reduzir tempo: ele aumentou 62–80 segundos e 167–357 tokens locais por tarefa. EXPERT continua disponível para tarefas realmente complexas quando planejamento e revisão elevarem a qualidade mais do que o tempo adicional; ele precisa ser reavaliado com uma tarefa complexa cujo orçamento de saída seja suficiente e com testes de aceitação executáveis.
