# Hybrid IA — modelos locais com especialistas do 9Router

Assistente de programação em Python 3.11+, com núcleo sem dependências Python externas. O modelo local produz a implementação; o 9Router pode planejar, revisar ou responder diretamente. Inclui CLI interativa, contexto limitado, memória explícita, leitura protegida de arquivos e métricas locais.

## Começar

```bash
cp .env.example .env
# Configure os endpoints e, opcionalmente, a chave do 9Router em .env.
python main.py --diagnose
python main.py "Explique como tratar iteráveis em Python" --mode local
python main.py --interactive --mode auto
```

Aceita Qwen/llama-server e modelos locais do Ollama. O endpoint configurado deve ser compatível com `/v1/chat/completions`. O 9Router é opcional: `ROUTER9_ENABLED=false` mantém AUTO local. O projeto não instala nem inicia servidores de modelos. Os relatórios antigos em `reports/` são registros históricos, não verificação do ambiente atual.

## Modos e revisão

| Modo | Fluxo |
|---|---|
| LOCAL | Qwen responde |
| HYBRID | Qwen analisa brevemente → especialista critica → Qwen responde |
| EXPERT | especialista planeja → Qwen implementa → especialista revisa → no máximo uma correção pelo Qwen e uma conferência final |
| FAST | especialista responde diretamente |
| AUTO | classifica o pedido; escolhe LOCAL, HYBRID ou EXPERT conforme complexidade e configuração |

Somente a resposta exata `APROVADO` encerra uma revisão com aprovação. Divergências remanescentes aparecem como `review_status=unresolved`; revisões interrompidas como `incomplete`. O sistema não interpreta parecer de modelo como teste executado. Uma resposta já produzida é preservada quando uma revisão falha.

Falhas remotas anteriores à resposta acionam fallback local. Métricas distinguem o modo solicitado, o modo efetivo, chamadas bem-sucedidas e tentativas falhas. Não há repetição automática ilimitada.

## Arquivos, ferramentas e permissões

```bash
python main.py --list-files
python main.py "Explique este módulo" --file core/router.py --mode local
python main.py "Proponha uma correção" --file core/router.py --propose-diff
python main.py --check syntax
python main.py --check unittest --allow-exec
python main.py "Analise os resultados" --check syntax --mode local
```

`--root /caminho/projeto` seleciona outra raiz; `.env`, memória, sessões e logs são relativos a ela. `--file` fornece contexto somente local. `--propose-diff` solicita uma proposta textual. A aplicação é uma etapa separada com `--apply-patch` e autorização explícita. Ferramentas são acionadas por argumentos da CLI, nunca por texto de modelos.

A checagem de sintaxe analisa Python sem executar o código. A checagem `unittest` executa código real do projeto, exige `--allow-exec`, usa comando fixo, diretório definido e timeout de 30 segundos. Essa execução não é uma sandbox para código hostil. A saída apresentada é limitada e sanitizada.

Envio de arquivos ao especialista exige seleção e autorização explícitas:

```bash
python main.py "Revise este módulo" --mode expert \
  --allow-external-files --external-file core/router.py
```

São bloqueados caminhos fora da raiz, links para fora dela, `.env*`, `.git`, diretórios privados, chaves e certificados. `HYBRID_PRIVATE_PATHS` aceita nomes e caminhos relativos separados por vírgulas. Arquivos grandes ou binários são recusados; o limite total inclui os cabeçalhos. Recusas são informadas na CLI e no JSON.

Todos os prompts enviados ao 9Router passam pelo sanitizador, incluindo análises e código produzido pelo Qwen. A detecção usa padrões conhecidos e não garante reconhecer qualquer segredo. A instrução para ignorar comandos embutidos em arquivos também não garante resistência absoluta a prompt injection.

**Histórico, memória existente e arquivos locais não são autorizados para exportação.** Quando estão presentes, modos remotos fazem fallback para LOCAL. Para obter revisão externa de um arquivo, inicie uma execução sem esse contexto privado e use `--external-file` explicitamente.

## Memória e conversa

Pedidos e respostas não são adicionados automaticamente à memória técnica. Salve apenas informações que você confirmar:

```bash
python main.py --memory show
python main.py --memory add --category constraints "Usar somente biblioteca padrão"
python main.py --memory remove --category constraints --index 0
python main.py --memory clear
python main.py "Explique esta função" --no-memory
```

A edição de uma entrada pode ser feita removendo-a e adicionando a versão corrigida. Arquivos de memória são gravados atomicamente com permissão `0600`. Não há mesclagem de gravações concorrentes; use um processo por sessão/memória.

O histórico fica apenas em RAM, exceto quando `--session` é usado:

```bash
python main.py --interactive --session meu-projeto
python main.py --session meu-projeto --clear-session
```

Comandos interativos: `/mode local|hybrid|expert|fast|auto`, `/model` (catálogo), `/model CHAVE`, `/search TERMOS`, `/skills [FILTRO]`, `/skill NOME`, `/metrics`, `/clear` e `/exit`. A persistência retém até 20 mensagens sanitizadas; o contexto usa até oito mensagens recentes que couberem. `--no-memory` não desativa uma sessão explicitamente solicitada.

## Skills, concisão e limites

```bash
python main.py --list-skills
python main.py "Debug deste erro" --skill debug --concise
python main.py "Revise a segurança" --skill security
```

As instruções locais em `skills/` são pequenas e selecionadas por tarefa: `minimal`, `debug`, `security`, `explore`, `patch`, `testing` e `review`. `--skill none` desativa esse contexto. São procedimentos próprios do projeto; skills do ambiente do desenvolvedor não são importadas automaticamente.

| Configuração | Padrão | Efeito |
|---|---:|---|
| `LOCAL_CONTEXT_TOKENS` | 8192 | Janela local |
| `LOCAL_RESPONSE_RESERVE_TOKENS` | 1024 | Reserva de saída |
| `LOCAL_CONTEXT_SAFETY_TOKENS` | 256 | Margem adicional |
| `HYBRID_MAX_EXTERNAL_CALLS` | 3 | Máximo de tentativas externas por tarefa |
| `HYBRID_EXTERNAL_TOKEN_BUDGET` | 1600 | Soma dos limites de **saída** reservados antes das chamadas, incluindo falhas |
| `HYBRID_TASK_TIMEOUT_SECONDS` | 900 | Prazo verificado entre etapas |
| `HYBRID_PROVIDER_TIMEOUT_SECONDS` | 120 | Timeout das operações de rede |
| `EXTERNAL_FILE_CHAR_LIMIT` | 12000 | Limite total de caracteres de arquivos |

O prazo entre etapas não mata uma operação de rede já em andamento; o timeout HTTP limita essa operação. Tokens de entrada externos são medidos, mas não estão incluídos no orçamento de saída. Não há estimativa de preço monetário sem uma tabela configurada.

O contexto reserva resposta e margem. Sem tokenizador local, usa uma estimativa conservadora por bytes UTF-8. Pedidos e evidências essenciais grandes demais são recusados em vez de cortados silenciosamente. Memória e histórico opcionais são reduzidos para caber.

## Validação e benchmark

```bash
python -m unittest discover -v
python main.py --check syntax
python benchmarks/run.py
python benchmarks/run.py --live --modes local hybrid expert --task simple_clamp
python benchmarks/run.py --live --skills none auto --repeat 2
```

O benchmark possui seis tarefas, isola memória entre execuções, compara modelos, modos e skills e salva cada resultado em `reports/`. `--live` autoriza inferência, inclusive remota nos modos escolhidos. Sem essa flag, apenas mostra a matriz planejada. Falhas e resultados degradados produzem código de saída 1.

O relatório registra tokens, tempos, tentativas, estágios e revisão. Por padrão avalia apenas sintaxe Python. Com `--functional`, executa critérios funcionais fixos em Docker isolado; nenhuma vitória de modo/modelo é declarada sem medições suficientes.

`logs/runs.jsonl` contém metadados de execução, sem prompts/respostas. `.env`, sessões, memória, logs e modelos são ignorados pelo Git. O arquivo `ideias.md` distingue melhorias entregues de experimentos pendentes, incluindo comparação ampla de modelos e ajustes de GPU.


## Modelos locais e streaming

```bash
python main.py --list-models
python main.py --interactive --model ollama:hermes3:latest --stream
python main.py "Explique esta função" --model ollama:hermes3:latest --file core/router.py --stream
```

O catálogo consulta `/v1/models` no servidor configurado e no Ollama (`OLLAMA_BASE_URL`, padrão `http://127.0.0.1:11434/v1`). Só lista modelos servidos; arquivos GGUF sem servidor ativo não aparecem. Seleção explícita valida disponibilidade, preserva histórico e não baixa modelos. Nomes ambíguos exigem a chave com prefixo `qwen:` ou `ollama:`. Não há escolha automática do melhor modelo sem avaliação.

`--stream` exibe a resposta local final nos modos LOCAL/HYBRID e a resposta remota em FAST. EXPERT mantém rascunhos internos e apresenta o resultado após a revisão. Ctrl+C cancela a CLI. No painel, Cancelar interrompe o socket de streaming já aberto; conexão inicial e tokenização podem aguardar o timeout. Respostas parciais canceladas não entram na sessão. Servidores precisam oferecer SSE compatível; não há repetição silenciosa de geração se o formato falhar. `--stream` e `--json` são mutuamente exclusivos.

## Busca local e aplicação de patches

```bash
python main.py --search "decide_route"
python main.py "Explique como funciona o roteamento" --auto-context --stream
python main.py "Proponha uma correção como unified diff" --file core/router.py --skill patch
python main.py --apply-patch proposta.diff
python main.py --apply-patch proposta.diff --yes --check unittest --allow-exec
```

A busca é lexical: classifica arquivos e trechos por termos, devolve caminhos/linhas e limita o contexto a 6000 caracteres. Não requer embeddings, rede ou índice. A varredura considera até 1000 arquivos, 256 KB por arquivo e 8 MB por busca. Arquivos privados, binários e maiores que esse limite são excluídos; trechos passam pelo sanitizador. `--auto-context` refaz a busca a cada pedido e mantém seus resultados somente locais, acionando o fallback LOCAL nas rotas externas.

Sem `--yes`, a CLI apenas mostra a prévia. No painel é necessário gerar a prévia e clicar em Confirmar e aplicar. A aplicação aceita alterações, criação e remoção de arquivos UTF-8 com hunks exatos; recusa caminhos privados, symlinks, renomes, metadados de modo, contexto divergente e arquivos alterados desde a prévia do painel. A escrita é atômica por arquivo, com reversão dos arquivos já escritos se a aplicação falhar. Não é uma transação contra outros processos nem mantém backup permanente: use controle de versão. Verificação sintática roda após aplicar; testes reais exigem `--allow-exec` ou a caixa correspondente no painel. Falha nos testes é exibida e não desfaz automaticamente um patch aplicado.

## Painel web local

```bash
python main.py --web
# Porta alternativa:
python main.py --web --port 8766
```

Abra a URL completa impressa no terminal. O serviço escuta apenas em `127.0.0.1`, usa token aleatório por processo e verifica Host/Origin. O token fica na sessão do navegador, é retirado do fragmento da URL após abertura e muda quando o servidor reinicia. O painel oferece modelos disponíveis, chat em streaming, cancelamento, sessões, skills, métricas, busca e aplicação de diffs. Nenhum pacote de frontend é necessário. Sem nome de sessão cada pedido é independente; para conversar com histórico, informe uma sessão. Uma tarefa de geração/aplicação roda por vez. As regras de privacidade e fallback da CLI também se aplicam.

## Biblioteca de skills

```bash
python main.py --list-skills
python main.py --skill-search segurança
python main.py --show-skill patch
python main.py "Revise a função" --skill review
python main.py --import-skill /caminho/SKILL.md --skill-name minha-skill
# Leia a prévia antes de confirmar:
python main.py --import-skill /caminho/SKILL.md --skill-name minha-skill --yes
python main.py "Minha tarefa" --skill minha-skill
```

A seleção `auto` carrega uma única skill embutida conforme o pedido; o nome efetivo é registrado nas métricas. Skills externas importadas ficam em `skills/custom/`, precisam ser selecionadas explicitamente e não substituem as embutidas. A importação aceita até 8000 bytes de texto UTF-8, recusa links e não copia scripts, dependências, ferramentas nem permissões. Faça uma versão resumida de skills maiores. Instruções importadas devem ser revisadas: importar não constitui análise automática de segurança. A biblioteca do Codex em `~/.agents/skills` ou `~/.codex/skills` não é carregada automaticamente. Skills orientam o texto do modelo; não executam ações.

## Benchmark funcional e comparação de modelos/skills

```bash
# Preparação única; Docker precisa estar disponível:
docker pull python:3.11-slim
# Matriz sem inferência nem execução:
python benchmarks/run.py --models ollama:hermes3:latest --skills none auto --functional
# Avaliação real e restrita a uma tarefa:
python benchmarks/run.py --live --modes local --models ollama:hermes3:latest --skills none auto --task simple_clamp --functional
```

Os seis contratos verificam clamp, média de iteráveis, unicidade com ordem, parse de JSON, validação de caminhos e orçamento de chamadas. `--functional` inclui um contrato público padronizado no pedido e testa o código retornado. Executa apenas em contêiner Docker sem rede, sem mounts do projeto, filesystem de imagem somente leitura, usuário não privilegiado, capabilities removidas, 256 MB de memória, uma CPU e timeout de 20 segundos. A imagem precisa existir localmente (`--pull=never`). O Docker é necessário apenas para avaliação funcional; nunca há fallback para executar código gerado diretamente no host.

Relatórios registram aprovação/falha, asserções aprovadas, erro/timeout, modelo, skill e métricas. Docker indisponível resulta em erro de avaliação, não aprovação. Os testes são uma amostra finita do contrato e não uma prova de qualidade geral ou resistência a candidatos adversariais. Comparações devem repetir tarefas e modelos; uma execução isolada não estabelece um vencedor.

## Testes de integração opcionais

```bash
python -m unittest discover -v
HYBRID_NETWORK_TESTS=1 python -m unittest tests.test_web -v
# Navegador: Playwright e Chromium instalados, fixture em outro terminal:
python tests/browser_fixture.py
HYBRID_PLAYWRIGHT_PATH=/caminho/node_modules/playwright node scripts/smoke_web.cjs
```

Testes HTTP exigem sockets de loopback; por padrão ficam pulados em ambientes restritos. A fixture do navegador usa respostas determinísticas e um projeto temporário, sem acessar modelos ou alterar este repositório.

## Registro da entrega

Veja o [CHANGELOG](CHANGELOG.md) e o [relatório de implementação e validação](reports/features-20260926.md). As [capturas desktop](reports/web-desktop.png) e [mobile](reports/web-mobile.png) mostram o painel com dados da fixture de teste. A CI executa testes unitários e HTTP em Python 3.11–3.13, checagem de sintaxe e planejamento do benchmark sem inferência.
