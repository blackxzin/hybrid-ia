# Histórico de alterações

## 2026-09-26 — Modelos, painel e avaliação funcional

### Adicionado

- Descoberta e seleção de modelos locais Qwen/llama-server e Ollama.
- Streaming, cancelamento e indicação de respostas limitadas por tokens.
- Busca lexical no projeto com trechos sanitizados, linhas e contexto automático opcional.
- Prévia e aplicação explícita de unified diffs, com checagem de contexto, caminhos e testes autorizados.
- Painel web local com autenticação por token, sessões, métricas, modelos, skills, busca e patches.
- Benchmark funcional em Docker isolado para seis contratos; comparação entre modelos e skills.
- Catálogo pesquisável de sete skills, seleção interativa, visualização e importação textual revisada.

### Corrigido e atualizado

- Seleção automática não confunde `ValueError` com solicitação de debug.
- O benchmark escolhe a skill a partir do pedido original, antes de acrescentar o contrato de avaliação.
- Busca preserva números de linha após ocultar segredos multilinha.
- Limites da análise de sintaxe e da busca independem do limite de contexto enviado ao modelo.
- README, exemplos de configuração, roteiro de ideias, relatórios e capturas atualizados.
- CI inclui os testes HTTP locais em Python 3.11–3.13.

### Validação

95 testes passaram com integração HTTP habilitada. Fluxos do painel verificados no Chromium, incluindo viewport móvel. Benchmark real de `clamp` com Hermes aprovado com e sem skill, seis critérios por execução. Resultados e limites estão em [reports/features-20260926.md](reports/features-20260926.md).
