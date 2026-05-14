# Plano de Testes Manuais SGQ

## Objetivo

Executar uma bateria manual estruturada para identificar falhas funcionais, erros de permissão, inconsistências de workflow, problemas de arquivos e regressões visuais no SistemaSGQ.

## Como usar este roteiro

- Execute os testes na ordem dos dias.
- Registre cada falha com: ID do teste, usuário, passos executados, resultado obtido, print e severidade.
- Marque cada caso como `OK`, `NOK`, `BLOQUEADO` ou `NÃO APLICÁVEL`.
- Sempre que um caso falhar, repita o fluxo com outro perfil para verificar se o defeito é global ou restrito a permissão.

## Ambientes e contas sugeridas

- Administrador: `admin@csvcascavel.com.br`
- Responsável da Qualidade: `qualidade@csvcascavel.com.br`
- Aprovador: `aprovador@csvcascavel.com.br`
- Auditor Externo/Técnico: criar manualmente no sistema para validar acesso somente leitura

## Massa de teste sugerida

- 2 arquivos PDF válidos, um pequeno e um maior
- 2 arquivos DOCX válidos, um simples e um com várias páginas
- 1 arquivo inválido para upload, como `.txt` ou `.exe`
- 1 documento com conteúdo criado pelo editor online
- 1 documento com revisão aberta
- 1 documento vigente já publicado
- 1 documento externo com arquivo e 1 sem arquivo

## Registro de defeitos

Use esta estrutura mínima por defeito:

- ID do teste
- Módulo
- Usuário
- Pré-condição
- Passos
- Resultado esperado
- Resultado obtido
- Severidade: Crítico, Alto, Médio ou Baixo
- Evidência

---

## Dia 0 - Preparação do ambiente

### Objetivo do dia

Garantir base limpa, usuários válidos, massa de teste pronta e rastreabilidade dos defeitos.

### Tópicos expandidos do dia

- Confirmar que a aplicação sobe sem erro.
- Confirmar que a base de dados foi criada e que os usuários padrão existem.
- Preparar arquivos de teste válidos e inválidos.
- Definir planilha ou documento de registro dos defeitos.

### Casos de teste

#### D0-T01 - Subida da aplicação

- Objetivo: validar se o sistema inicializa corretamente.
- Pré-condição: ambiente configurado.
- Passos:
  1. Executar a aplicação.
  2. Abrir a URL principal no navegador.
  3. Confirmar carregamento da tela inicial ou login.
- Resultado esperado: sistema abre sem erro 500, sem traceback e sem tela em branco.

#### D0-T02 - Inicialização da base

- Objetivo: validar criação da base e seed inicial.
- Pré-condição: base vazia ou nova.
- Passos:
  1. Executar `python init_db.py`.
  2. Confirmar mensagens de criação e seed.
  3. Validar que não houve erro fatal.
- Resultado esperado: tabelas criadas e usuários padrão inseridos ou reconhecidos como existentes.

#### D0-T03 - Contas padrão disponíveis

- Objetivo: garantir que as contas básicas existem para os testes seguintes.
- Pré-condição: seed executado.
- Passos:
  1. Tentar login com admin.
  2. Tentar login com qualidade.
  3. Tentar login com aprovador.
- Resultado esperado: todas as contas autenticam com sucesso.

#### D0-T04 - Massa de teste pronta

- Objetivo: evitar bloqueios nos dias seguintes.
- Pré-condição: arquivos disponíveis localmente.
- Passos:
  1. Separar arquivos PDF válidos.
  2. Separar arquivos DOCX válidos.
  3. Separar ao menos um arquivo inválido.
  4. Nomear os arquivos de forma fácil de rastrear.
- Resultado esperado: massa pronta para upload, edição e validações negativas.

---

## Dia 1 - Smoke test, login e navegação

### Objetivo do dia

Verificar se os fluxos básicos do sistema funcionam antes dos testes profundos.

### Tópicos expandidos do dia

- Login, logout e sessão.
- Navegação principal.
- Menus e telas carregando sem erro.
- Mensagens de erro amigáveis.

### Casos de teste

#### D1-T01 - Login válido

- Objetivo: validar autenticação básica.
- Pré-condição: usuário ativo existente.
- Passos:
  1. Acessar a tela de login.
  2. Informar usuário e senha válidos.
  3. Submeter o formulário.
- Resultado esperado: login realizado e redirecionamento para área autenticada.

#### D1-T02 - Login inválido

- Objetivo: validar mensagem de credenciais incorretas.
- Pré-condição: tela de login aberta.
- Passos:
  1. Informar email válido com senha errada.
  2. Repetir com email inexistente.
  3. Tentar submeter campos vazios.
- Resultado esperado: acesso negado com mensagem clara, sem traceback.

#### D1-T03 - Logout

- Objetivo: validar encerramento de sessão.
- Pré-condição: usuário logado.
- Passos:
  1. Acionar logout.
  2. Tentar voltar pelo navegador.
  3. Acessar URL interna previamente aberta.
- Resultado esperado: sessão encerrada e rotas protegidas exigem novo login.

#### D1-T04 - Acesso direto sem autenticação

- Objetivo: validar proteção das rotas.
- Pré-condição: usuário deslogado.
- Passos:
  1. Tentar acessar lista de documentos por URL.
  2. Tentar acessar detalhe de documento por URL.
  3. Tentar acessar gestão de usuários por URL.
- Resultado esperado: redirecionamento para login ou bloqueio apropriado.

#### D1-T05 - Navegação principal

- Objetivo: validar estabilidade das telas principais.
- Pré-condição: login realizado.
- Passos:
  1. Abrir dashboard.
  2. Abrir lista de documentos.
  3. Abrir documentos externos.
  4. Abrir lista mestra.
  5. Abrir gestão de usuários, se o perfil permitir.
- Resultado esperado: todas as telas carregam corretamente, sem erro 500.

#### D1-T06 - Atualização e múltiplas abas

- Objetivo: detectar problemas de sessão e estado básico.
- Pré-condição: usuário logado.
- Passos:
  1. Abrir duas abas do sistema.
  2. Navegar por páginas diferentes.
  3. Atualizar páginas repetidamente.
  4. Fazer logout em uma aba e testar a outra.
- Resultado esperado: comportamento consistente entre abas, sem sessão fantasma.

---

## Dia 2 - Permissões por perfil

### Objetivo do dia

Validar o modelo de autorização e encontrar qualquer rota ou botão exposto indevidamente.

### Tópicos expandidos do dia

- Conferir o que cada perfil consegue ver.
- Conferir o que cada perfil consegue executar.
- Tentar acessar rotas protegidas diretamente.
- Validar mensagem padrão de falta de permissão.

### Casos de teste

#### D2-T01 - Permissões do Administrador

- Objetivo: confirmar acesso total esperado.
- Pré-condição: login como admin.
- Passos:
  1. Navegar por todos os menus administrativos.
  2. Tentar criar, editar, aprovar e publicar documentos.
  3. Tentar gerenciar usuários.
- Resultado esperado: admin acessa e executa todas as funções permitidas.

#### D2-T02 - Permissões do Responsável da Qualidade

- Objetivo: validar escopo operacional intermediário.
- Pré-condição: login como qualidade.
- Passos:
  1. Tentar criar e editar documentos.
  2. Tentar abrir revisão.
  3. Tentar aprovar e publicar.
  4. Tentar gerenciar usuários.
- Resultado esperado: apenas ações compatíveis com o perfil ficam disponíveis.

#### D2-T03 - Permissões do Aprovador

- Objetivo: validar ações de aprovação e publicação.
- Pré-condição: login como aprovador.
- Passos:
  1. Acessar documentos em revisão ou aguardando aprovação.
  2. Tentar aprovar e publicar.
  3. Tentar criar ou editar usuários.
- Resultado esperado: aprovador executa aprovação/publicação e não acessa áreas indevidas.

#### D2-T04 - Permissões do Auditor Externo/Técnico

- Objetivo: garantir acesso somente leitura.
- Pré-condição: login com usuário auditor.
- Passos:
  1. Abrir lista e detalhe de documentos.
  2. Abrir documentos externos.
  3. Abrir lista mestra.
  4. Tentar criar, editar, aprovar, publicar e gerenciar usuários.
- Resultado esperado: leitura permitida e qualquer alteração bloqueada com 403 ou mensagem adequada.

#### D2-T05 - URL direta em rotas sensíveis

- Objetivo: detectar falha de autorização no backend.
- Pré-condição: login com perfil sem permissão.
- Passos:
  1. Copiar URLs de criação, edição, revisão, aprovação, publicação e usuários.
  2. Abrir essas URLs diretamente.
- Resultado esperado: acesso negado em todas as rotas proibidas.

#### D2-T06 - Consistência entre botão visível e permissão real

- Objetivo: detectar divergência entre frontend e backend.
- Pré-condição: repetir com todos os perfis.
- Passos:
  1. Verificar se botões indevidos aparecem.
  2. Quando aparecerem, tentar executar.
  3. Quando não aparecerem, tentar URL direta.
- Resultado esperado: interface e backend refletem a mesma regra de permissão.

---

## Dia 3 - Cadastro e manutenção de documentos

### Objetivo do dia

Validar a criação, edição e consistência dos metadados dos documentos.

### Tópicos expandidos do dia

- Cadastro com dados válidos e inválidos.
- Upload de PDF e DOCX.
- Validação de campos obrigatórios e limites.
- Persistência de dados após salvar.

### Casos de teste

#### D3-T01 - Criar documento com dados mínimos válidos

- Objetivo: validar criação básica.
- Pré-condição: perfil com permissão para criar.
- Passos:
  1. Abrir novo documento.
  2. Preencher código, título, tipo e revisão inicial.
  3. Salvar.
- Resultado esperado: documento criado com sucesso e status coerente.

#### D3-T02 - Criar documento com todos os campos relevantes

- Objetivo: validar persistência completa.
- Pré-condição: perfil com permissão.
- Passos:
  1. Criar documento preenchendo distribuição técnica, administrativa, treinamento, observação e requisitos relacionados.
  2. Salvar.
  3. Reabrir o documento.
- Resultado esperado: todos os campos permanecem gravados corretamente.

#### D3-T03 - Validação de obrigatórios

- Objetivo: garantir mensagens corretas de validação.
- Pré-condição: formulário de novo documento aberto.
- Passos:
  1. Tentar salvar sem código.
  2. Tentar salvar sem título.
  3. Tentar salvar sem tipo.
- Resultado esperado: sistema bloqueia envio e mostra mensagens claras.

#### D3-T04 - Limites de tamanho e texto

- Objetivo: detectar quebra por excesso de caracteres.
- Pré-condição: formulário aberto.
- Passos:
  1. Inserir código acima do limite.
  2. Inserir título acima do limite.
  3. Inserir texto muito grande em observação ou requisito.
- Resultado esperado: sistema valida corretamente ou trata o excesso sem quebrar.

#### D3-T05 - Upload de PDF válido

- Objetivo: validar anexo PDF no documento.
- Pré-condição: documento em rascunho.
- Passos:
  1. Enviar PDF válido.
  2. Salvar.
  3. Visualizar ou baixar o arquivo.
- Resultado esperado: upload aceito e arquivo acessível posteriormente.

#### D3-T06 - Upload de DOCX válido

- Objetivo: validar anexo DOCX editável.
- Pré-condição: documento em rascunho.
- Passos:
  1. Enviar DOCX válido.
  2. Salvar.
  3. Confirmar se o sistema registra o arquivo corretamente.
- Resultado esperado: upload aceito sem erro.

#### D3-T07 - Upload inválido

- Objetivo: validar rejeição de arquivos não permitidos.
- Pré-condição: tela de upload aberta.
- Passos:
  1. Tentar enviar `.txt` ou outro formato inválido.
  2. Repetir com arquivo de extensão mascarada.
- Resultado esperado: sistema rejeita o arquivo com mensagem apropriada.

#### D3-T08 - Edição de documento existente

- Objetivo: validar atualização segura do cadastro.
- Pré-condição: documento já criado.
- Passos:
  1. Alterar título, tipo e observação.
  2. Salvar.
  3. Reabrir o detalhe.
- Resultado esperado: alterações persistidas sem perda de outros dados.

#### D3-T09 - Elaborador automático

- Objetivo: validar regra de autoria automática.
- Pré-condição: documento criado por um usuário específico.
- Passos:
  1. Criar um documento com um usuário.
  2. Abrir o detalhe do documento.
  3. Conferir o elaborador exibido.
- Resultado esperado: elaborador corresponde ao usuário autenticado que criou o documento.

#### D3-T10 - Ausência de seleção manual de usuários

- Objetivo: validar o refactor do workflow.
- Pré-condição: formulário de criação e edição acessível.
- Passos:
  1. Abrir formulário de novo documento.
  2. Abrir formulário de edição.
  3. Procurar campos para escolher elaborador, revisor ou aprovador.
- Resultado esperado: esses campos não são exibidos.

---

## Dia 4 - Workflow de revisão, aprovação e publicação

### Objetivo do dia

Cobrir o fluxo mais crítico do sistema, onde normalmente aparecem os defeitos mais graves.

### Tópicos expandidos do dia

- Abrir revisão.
- Editar revisão.
- Enviar para aprovação.
- Aprovar e publicar automaticamente.
- Reprovar e retornar para edição.

### Casos de teste

#### D4-T01 - Abrir revisão de documento vigente

- Objetivo: validar criação de revisão.
- Pré-condição: documento vigente existente.
- Passos:
  1. Abrir detalhe do documento vigente.
  2. Acionar abertura de revisão.
  3. Informar motivo, se solicitado.
- Resultado esperado: revisão criada e documento entra no estado adequado.

#### D4-T02 - Editar conteúdo da revisão

- Objetivo: validar manutenção da revisão ativa.
- Pré-condição: revisão aberta.
- Passos:
  1. Editar campos da revisão ou conteúdo associado.
  2. Salvar.
  3. Reabrir a revisão.
- Resultado esperado: alterações preservadas.

#### D4-T03 - Enviar revisão para aprovação

- Objetivo: validar transição para aguardando aprovação.
- Pré-condição: revisão em edição.
- Passos:
  1. Acionar envio para aprovação.
  2. Retornar ao detalhe do documento.
- Resultado esperado: status da revisão muda para aguardando aprovação.

#### D4-T04 - Aprovar revisão com usuário aprovador

- Objetivo: validar aprovação e publicação no mesmo ato.
- Pré-condição: revisão aguardando aprovação.
- Passos:
  1. Logar como aprovador.
  2. Abrir detalhe ou preview da revisão.
  3. Clicar em aprovar.
- Resultado esperado: revisão é aprovada e publicada imediatamente, sem depender de etapa manual extra.

#### D4-T05 - Aprovador automático

- Objetivo: validar autoria automática da aprovação.
- Pré-condição: revisão aprovada por um usuário conhecido.
- Passos:
  1. Aprovar a revisão com a conta do aprovador.
  2. Verificar no detalhe, histórico ou metadados quem ficou como aprovador.
- Resultado esperado: aprovador registrado é o usuário autenticado que clicou em aprovar.

#### D4-T06 - Reprovar revisão

- Objetivo: validar retorno do fluxo para edição.
- Pré-condição: revisão aguardando aprovação.
- Passos:
  1. Abrir a revisão com usuário aprovador.
  2. Informar motivo da reprovação.
  3. Confirmar ação.
- Resultado esperado: revisão volta para edição ou estado equivalente, com motivo registrado.

#### D4-T07 - Publicar rascunho diretamente como vigente

- Objetivo: validar fluxo curto sem revisão.
- Pré-condição: documento em rascunho com conteúdo publicável.
- Passos:
  1. Logar como aprovador.
  2. Abrir detalhe ou preview do rascunho.
  3. Publicar como vigente.
- Resultado esperado: documento muda para vigente e registra aprovador automaticamente.

#### D4-T08 - Datas de aprovação e publicação

- Objetivo: validar integridade temporal do workflow.
- Pré-condição: documento ou revisão acabou de ser publicado.
- Passos:
  1. Publicar um rascunho ou aprovar uma revisão.
  2. Verificar data de aprovação.
  3. Verificar data de publicação.
- Resultado esperado: datas coerentes e registradas corretamente.

#### D4-T09 - Usuário sem permissão tentando aprovar

- Objetivo: validar bloqueio de ação crítica.
- Pré-condição: revisão aguardando aprovação.
- Passos:
  1. Logar com perfil sem permissão de aprovação.
  2. Tentar aprovar pela interface.
  3. Tentar via URL direta.
- Resultado esperado: ação bloqueada em ambos os caminhos.

#### D4-T10 - Consistência do histórico de eventos

- Objetivo: validar rastreabilidade.
- Pré-condição: fluxo de aprovação ou reprovação executado.
- Passos:
  1. Executar ações de revisão.
  2. Verificar histórico do documento.
  3. Conferir usuário, tipo de evento e descrição.
- Resultado esperado: histórico descreve corretamente quem fez cada ação e quando.

---

## Dia 5 - Editor online, preview, PDFs e arquivos

### Objetivo do dia

Validar o fluxo de conteúdo online, geração de artefatos e movimentação dos arquivos físicos.

### Tópicos expandidos do dia

- Editor online do documento.
- Preview online do rascunho e da revisão.
- Geração automática de PDF.
- Cópia e obsolescência de arquivos.

### Casos de teste

#### D5-T01 - Salvar conteúdo no editor online do documento

- Objetivo: validar persistência do conteúdo HTML.
- Pré-condição: documento em rascunho.
- Passos:
  1. Abrir editor online.
  2. Inserir conteúdo textual relevante.
  3. Salvar.
  4. Reabrir o editor.
- Resultado esperado: conteúdo reaparece corretamente.

#### D5-T02 - Preview online do rascunho

- Objetivo: validar renderização do conteúdo salvo.
- Pré-condição: documento com conteúdo online.
- Passos:
  1. Abrir preview online.
  2. Revisar título, código, revisão e conteúdo.
  3. Validar layout básico.
- Resultado esperado: preview carrega sem erro e reflete o conteúdo salvo.

#### D5-T03 - Publicar documento criado só no editor online

- Objetivo: validar fluxo sem PDF manual.
- Pré-condição: documento em rascunho com conteúdo no editor e sem PDF enviado.
- Passos:
  1. Abrir preview online.
  2. Publicar como vigente.
  3. Tentar abrir o PDF vigente gerado.
- Resultado esperado: publicação concluída e PDF vigente disponível, ou aviso controlado quando a geração automática falhar.

#### D5-T04 - Preview online de revisão

- Objetivo: validar fluxo de revisão no editor.
- Pré-condição: revisão com conteúdo online.
- Passos:
  1. Abrir preview da revisão.
  2. Conferir se o conteúdo atualizado está correto.
  3. Aprovar a partir do preview, se aplicável.
- Resultado esperado: preview estável e ação de aprovação funcionando sem erro.

#### D5-T05 - Obsolescência do PDF anterior

- Objetivo: validar troca segura de versão publicada.
- Pré-condição: documento vigente com PDF antigo e nova revisão aprovada.
- Passos:
  1. Aprovar e publicar nova revisão.
  2. Verificar se o PDF vigente anterior deixou de ser o ativo.
  3. Confirmar acesso ao novo vigente.
- Resultado esperado: nova versão vigente disponível e versão anterior tratada como obsoleta.

#### D5-T06 - DOCX editável após revisão

- Objetivo: validar preservação do arquivo editável.
- Pré-condição: revisão com DOCX associado.
- Passos:
  1. Aprovar e publicar revisão com DOCX.
  2. Verificar se o DOCX associado continua acessível.
- Resultado esperado: DOCX correto associado à versão publicada.

#### D5-T07 - Acesso a arquivos publicados

- Objetivo: validar links e downloads.
- Pré-condição: documento vigente e documento obsoleto existentes.
- Passos:
  1. Abrir PDF vigente.
  2. Abrir histórico ou obsoleto, se disponível.
  3. Repetir com outro perfil autorizado.
- Resultado esperado: links válidos e arquivos corretos sendo entregues.

#### D5-T08 - Concorrência simples em duas abas

- Objetivo: encontrar perda de atualização ou conflito de estado.
- Pré-condição: documento editável aberto em duas abas.
- Passos:
  1. Abrir o mesmo documento em duas abas.
  2. Salvar conteúdo diferente em cada aba.
  3. Reabrir o documento e o preview.
- Resultado esperado: comportamento previsível, sem corromper conteúdo ou quebrar o fluxo.

---

## Dia 6 - Documentos externos, Lista Mestra, usuários e regressão final

### Objetivo do dia

Cobrir módulos de apoio e finalizar com regressão dos fluxos mais críticos.

### Tópicos expandidos do dia

- Cadastro e consulta de documentos externos.
- Configuração e visualização da Lista Mestra.
- Gestão de usuários.
- Regressão final do fluxo principal.

### Casos de teste

#### D6-T01 - Cadastrar documento externo com arquivo

- Objetivo: validar fluxo principal do módulo externo.
- Pré-condição: usuário com permissão.
- Passos:
  1. Abrir cadastro de documento externo.
  2. Preencher identificação, título, órgão, revisão e observação.
  3. Anexar arquivo válido.
  4. Salvar.
- Resultado esperado: documento externo cadastrado e arquivo acessível.

#### D6-T02 - Cadastrar documento externo sem arquivo

- Objetivo: validar comportamento opcional do anexo.
- Pré-condição: tela de cadastro aberta.
- Passos:
  1. Preencher dados obrigatórios.
  2. Não anexar arquivo.
  3. Salvar.
- Resultado esperado: cadastro aceito se o arquivo for opcional.

#### D6-T03 - Editar documento externo

- Objetivo: validar manutenção do cadastro externo.
- Pré-condição: documento externo existente.
- Passos:
  1. Alterar título, revisão, órgão ou observação.
  2. Salvar.
- Resultado esperado: dados atualizados corretamente.

#### D6-T04 - Documento externo com arquivo inválido

- Objetivo: validar rejeição de formato não permitido.
- Pré-condição: formulário disponível.
- Passos:
  1. Tentar anexar arquivo inválido.
  2. Salvar.
- Resultado esperado: sistema rejeita o upload sem quebrar a página.

#### D6-T05 - Lista Mestra

- Objetivo: validar geração e consistência dos dados publicados.
- Pré-condição: existir ao menos um documento vigente.
- Passos:
  1. Abrir Lista Mestra.
  2. Conferir presença dos documentos publicados.
  3. Validar cabeçalho, revisão e responsáveis exibidos.
- Resultado esperado: lista coerente com o estado real dos documentos.

#### D6-T06 - Configuração da Lista Mestra

- Objetivo: validar persistência das configurações.
- Pré-condição: perfil com permissão.
- Passos:
  1. Alterar título, código e revisão da Lista Mestra.
  2. Salvar.
  3. Reabrir a configuração.
- Resultado esperado: valores persistem corretamente.

#### D6-T07 - Gestão de usuários

- Objetivo: validar criação e edição de usuários e perfis.
- Pré-condição: login como admin.
- Passos:
  1. Criar um novo usuário de teste.
  2. Alterar perfil e status.
  3. Validar login com o novo usuário.
- Resultado esperado: usuário criado e controlado corretamente.

#### D6-T08 - Regressão curta do fluxo principal

- Objetivo: confirmar que os módulos principais ainda funcionam após todos os cenários.
- Pré-condição: ambiente estável.
- Passos:
  1. Fazer login.
  2. Criar documento.
  3. Editar conteúdo.
  4. Publicar ou revisar.
  5. Visualizar documento vigente.
  6. Acessar com auditor.
- Resultado esperado: fluxo completo executado sem erro crítico.

---

## Checklist transversal para repetir durante todos os dias

Repita esta conferência sempre que executar um caso importante:

- A tela exibiu mensagem clara de sucesso ou erro?
- Houve erro 500, traceback ou página em branco?
- O status do documento ficou correto depois da ação?
- O usuário exibido como elaborador, revisor ou aprovador está correto?
- O botão mostrado na interface combina com a permissão real do usuário?
- O histórico do documento registrou a ação certa?
- O arquivo baixado é o arquivo esperado?
- O comportamento se manteve igual após atualizar a página?

## Critério de encerramento da rodada manual

Considere a rodada concluída quando:

- Todos os casos críticos e altos forem executados.
- Todos os fluxos principais tiverem pelo menos um cenário válido e um inválido.
- Todos os perfis tiverem sido usados ao menos uma vez.
- Os defeitos encontrados estiverem registrados com evidência suficiente.
