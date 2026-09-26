# Ideias para melhorar o projeto

Atualizado em 26/09/2026. Itens marcados foram implementados e cobertos pela validação local. Itens abertos continuam sendo propostas ou experimentos; não representam funcionalidades já entregues.

## Entrega de setembro

- Ciclo EXPERT limitado a uma correção, com conferência final, preservação do código original e status de divergências.
- Sanitização também em respostas intermediárias; arquivos privados e contexto local permanecem locais.
- CLI interativa, memória explícita, sessões opcionais, skills pequenas e ferramentas de leitura/verificação.
- Benchmark com seis tarefas, três modos, comparação de skills e isolamento de memória. A análise automática é sintática; qualidade funcional e custo monetário ainda não são avaliados.
- Limites de chamadas e tokens de saída externos; timeout por operação e prazo entre etapas. Não há orçamento rígido de custo ou tokens totais.
- CI para Python 3.11–3.13. Comparação real de modelos, otimização de hardware, streaming e opiniões independentes continuam pendentes.

A CLI propõe diffs como texto; não aplica patches. O projeto não é um agente que modifica e testa código autonomamente. Checklists marcados descrevem essas capacidades limitadas, documentadas no README.

## Colaboração entre Qwen local e 9Router

- [x] **Fechar o ciclo de revisão:** Qwen prepara a resposta; 9Router revisa; Qwen corrige uma vez; 9Router faz uma conferência final.
- [x] **Definir papéis claros:** pedir revisões focadas em bugs, requisitos esquecidos, segurança ou qualidade do código, em vez de uma revisão genérica.
- [ ] **Dividir tarefas grandes:** 9Router propõe etapas e critérios de aceite; Qwen trabalha nas etapas; 9Router verifica se tudo foi coberto.
- [ ] **Usar verificações concretas:** quando apropriado, executar testes ou checagens de sintaxe e passar os resultados ao modelo para orientar correções.
- [ ] **Tratar divergências:** quando os modelos discordarem, registrar os pontos em conflito e buscar evidências em testes ou documentação antes de decidir.
- [x] **Controlar chamadas e rodadas:** limitar correções e revisões e parar cedo quando a resposta já passar pelas verificações.

## Memória e privacidade

- [x] Dar controle ao usuário sobre o que é salvo na memória técnica.
- [x] Permitir desativar a memória e apagar o conteúdo salvo com facilidade.
- [x] Revisar a sanitização de segredos e o limite de tamanho dos arquivos enviados ao serviço externo.

## Medição de qualidade

- [x] Ampliar o benchmark com mais tarefas e comparar LOCAL, HYBRID e EXPERT.
- [ ] Medir qualidade, erros encontrados, latência, número de chamadas e custo, para confirmar quando a colaboração realmente ajuda.
- [ ] Guardar exemplos de revisões úteis para orientar melhorias e novos casos de benchmark.

## Experiência de uso

- [x] Considerar histórico de conversa persistente na CLI.
- [x] Adicionar comandos para consultar, editar e limpar a memória técnica.

## Skills e fluxo de agentes

As skills Caveman, Ponytail e as skills de agentes disponíveis neste ambiente são instruções para orientar um agente; elas não são plug-ins que o Qwen ou o 9Router já carregam automaticamente. Podemos aproveitar as ideias e criar um carregamento seletivo no próprio projeto.

- [x] **Criar skills locais simples:** guardar procedimentos reutilizáveis em arquivos Markdown, por exemplo diagnóstico de bugs, revisão de segurança e planejamento de mudanças.
- [x] **Selecionar skill por tarefa:** identificar o tipo de pedido e carregar só a instrução relevante, sem colocar todas as skills em todo prompt.
- [x] **Usar uma abordagem Ponytail:** antes de propor uma solução, procurar o caminho mínimo que resolve o problema, reutilizar código existente e evitar dependências e abstrações sem necessidade.
- [x] **Oferecer respostas concisas no estilo Caveman:** opção de resposta curta que preserve os detalhes técnicos e possa ser ativada pelo usuário.
- [x] **Dar instruções compatíveis com cada papel:** Qwen recebe a skill de implementação; 9Router recebe a skill de revisão ou planejamento; ambos recebem critérios de aceite comuns.
- [ ] **Medir se cada skill ajuda:** comparar tarefas com e sem a skill e manter apenas instruções que melhorem os resultados sem aumentar demais latência ou contexto.
- [ ] **Manter uma biblioteca pesquisável:** separar skills usadas com frequência das referências ocasionais e carregar estas últimas somente quando necessário.
- [ ] **Tratar skills externas como conteúdo a revisar:** verificar instruções e comandos antes de adotar skills baixadas; começar por arquivos locais e confiáveis.

## Confiabilidade do agente

- [x] **Auditar as camadas do agente:** revisar prompts, histórico, memória, roteamento, chamadas externas, fallbacks e saída para encontrar pontos onde a resposta pode piorar.
- [x] **Tornar etapas observáveis:** registrar qual modo e skill foram selecionados, quais verificações rodaram e por que houve fallback, sem registrar chaves ou conteúdo sensível desnecessário.
- [x] **Definir recuperação de falhas:** quando uma chamada falhar, registrar a causa de forma segura, limitar tentativas e orientar o próximo passo em vez de repetir indefinidamente.
- [x] **Evitar memória contaminada:** não transformar automaticamente toda resposta ou raciocínio dos modelos em memória; priorizar decisões confirmadas e correções do usuário.

## Assistente de programação no projeto

- [x] **Criar uma CLI completa para o assistente híbrido:** evoluir a CLI atual, que recebe um pedido por execução, para uma interface interativa com conversa, seleção de modo (`LOCAL`, `HYBRID`, `EXPERT`), uso de skills, métricas e comandos de memória.
- [x] **Adicionar ferramentas de leitura do projeto:** permitir listar arquivos e ler arquivos selecionados para responder sobre o código, respeitando pastas privadas e limites de tamanho.
- [x] **Propor alterações como diff:** mostrar exatamente quais linhas mudariam e deixar a aplicação das mudanças sob controle do usuário.
- [x] **Executar verificações com limites:** oferecer testes ou checagens em comandos permitidos, com timeout e diretório definidos; apresentar o resultado real ao modelo e ao usuário.
- [x] **Começar em modo somente leitura:** separar leitura, proposta de alteração e execução de comandos como permissões distintas.
- [ ] **Detectar mudanças no pedido:** depois de cada etapa, conferir os critérios de aceite e os arquivos envolvidos para evitar que o plano se desvie da tarefa.

## Roteamento, velocidade e custo

- [ ] **Escolher modelos por capacidade e disponibilidade:** permitir modelos diferentes para planejamento, revisão e resposta, com fallback local claro quando um deles estiver indisponível.
- [ ] **Definir um orçamento por tarefa:** limitar chamadas externas, tokens e tempo; parar quando atingir o limite e explicar o estado ao usuário.
- [ ] **Usar duas opiniões externas só em casos difíceis:** comparar respostas independentes apenas quando a tarefa justificar o custo e pedir uma verificação objetiva das divergências.
- [x] **Manter um modo rápido:** pular planejamento e revisão em tarefas simples, sem impedir que o usuário peça uma revisão extra.
- [ ] **Considerar streaming da resposta:** mostrar o texto conforme é gerado para reduzir a espera percebida, se o servidor local e o cliente suportarem esse fluxo de forma confiável.

## Segurança e previsibilidade

- [ ] **Defender-se contra instruções maliciosas em arquivos:** tratar conteúdo lido do repositório como dados, não como instruções para mudar o comportamento do agente ou enviar informações.
- [x] **Criar limites explícitos para cada ferramenta:** restringir caminhos acessíveis e comandos executáveis; não permitir que texto do modelo amplie essas permissões.
- [x] **Separar evidência de sugestão:** indicar o que veio de arquivo, teste ou resposta de modelo e não afirmar que um comando rodou quando ele não foi executado.
- [x] **Adicionar um comando de diagnóstico:** verificar conexão com Qwen e 9Router, configuração, modelos disponíveis e limites locais sem exibir credenciais.

## Desempenho local para Ryzen 5 4600G + RX 580 8 GB + 16 GB RAM (Arch Linux)

- [ ] **Comparar um modelo menor de código:** testar o `Qwen3.8-9B-Distill` comunitário em `Q4_K_M` (GGUF de cerca de 5,78 GB) com o Qwen3.8-27B atual. O 9B pode responder mais rápido, mas não é um lançamento oficial Qwen nessa dimensão e sua qualidade precisa ser comparada nas nossas tarefas; medir também se cabe com folga na VRAM disponível.
- [ ] **Comparar IQ4_XS com uma quantização K-quant:** o modelo atual usa IQ4_XS; a matriz de recursos do llama.cpp alerta que I-quants no Vulkan podem ser mais lentos. Medir uma variante K-quant compatível antes de trocar.
- [ ] **Fazer uma rodada curta de `llama-bench`:** variar threads (por exemplo, 6, 8 e 10), batch e camadas na GPU, registrando geração e processamento de prompt separadamente.
- [ ] **Medir `-fa off` e `-fa on`:** manter desligado como referência e só usar a opção que funcionar e melhorar no build Vulkan atual.
- [ ] **Medir cache KV com K e V no mesmo formato:** comparar `f16` com `q8_0` (e, se suportado, `q4_0`), observando velocidade, memória e qualidade; não assumir que cache quantizado acelera geração.
- [ ] **Preservar margem de VRAM e RAM:** medir memória livre antes e durante a inferência; evitar aumentar camadas, contexto ou batch até o limite, pois o sistema já tem 16 GB e a GPU também atende o desktop.
- [ ] **Confirmar o backend e o driver usados:** o registro atual mostra `llama.cpp` com Vulkan e RADV POLARIS10; manter esse caminho como baseline e não migrar para ROCm sem confirmar suporte oficial à RX 580 e ao Arch.
- [ ] **Medir clocks e temperatura durante uma geração:** conferir se a RX 580 mantém clocks sob carga antes de mexer em perfis de energia; qualquer ajuste deve ser temporário, reversível e comparado com o padrão.
- [ ] **Criar perfis de uso:** perfil “rápido” com modelo menor/contexto moderado e perfil “melhor resposta” com o 27B, deixando claro o custo de tempo de cada um.
