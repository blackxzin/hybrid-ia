# Hybrid IA — Qwen local com especialistas do 9Router

Assistente de programação em Python 3.11+, sem dependências externas. Qwen produz a implementação; o 9Router pode planejar, revisar ou responder diretamente. Inclui CLI interativa, contexto limitado, memória explícita, leitura protegida de arquivos e métricas locais.

## Começar

```bash
cp .env.example .env
# Configure os endpoints e, opcionalmente, a chave do 9Router em .env.
python main.py --diagnose
python main.py "Explique como tratar iteráveis em Python" --mode local
python main.py --interactive --mode auto
```

Requer um servidor Qwen compatível com `/v1/chat/completions`. O 9Router é opcional: `ROUTER9_ENABLED=false` mantém AUTO local. O projeto não instala nem inicia servidores de modelos. Os relatórios antigos em `reports/` são registros históricos, não verificação do ambiente atual.

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

`--root /caminho/projeto` seleciona outra raiz; `.env`, memória, sessões e logs são relativos a ela. `--file` fornece contexto somente local. `--propose-diff` solicita uma proposta textual e não aplica alterações. Ferramentas são acionadas por argumentos da CLI, nunca por texto de modelos.

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

Comandos interativos: `/mode local`, `/mode hybrid`, `/mode expert`, `/mode fast`, `/mode auto`, `/metrics`, `/clear` e `/exit`. A persistência retém até 20 mensagens sanitizadas; o contexto usa até oito mensagens recentes que couberem. `--no-memory` não desativa uma sessão explicitamente solicitada.

## Skills, concisão e limites

```bash
python main.py --list-skills
python main.py "Debug deste erro" --skill debug --concise
python main.py "Revise a segurança" --skill security
```

As instruções locais em `skills/` são pequenas e selecionadas por tarefa: `minimal`, `debug` e `security`. `--skill none` desativa esse contexto. São procedimentos próprios do projeto; skills do ambiente do desenvolvedor não são importadas automaticamente.

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

O benchmark possui seis tarefas, isola memória entre execuções, compara modos e skills e salva cada resultado em `reports/`. `--live` autoriza inferência, inclusive remota nos modos escolhidos. Sem essa flag, apenas mostra a matriz planejada. Falhas e resultados degradados produzem código de saída 1.

O relatório registra tokens, tempos, tentativas, estágios e revisão. Avalia sintaxe Python sem executar código gerado. **Qualidade funcional não é avaliada automaticamente** e nenhuma vitória de modo/modelo é declarada sem medições reais.

`logs/runs.jsonl` contém metadados de execução, sem prompts/respostas. `.env`, sessões, memória, logs e modelos são ignorados pelo Git. O arquivo `ideias.md` distingue melhorias entregues de experimentos pendentes, incluindo comparação de modelos, GPU e streaming.
