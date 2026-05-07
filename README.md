# SistemaSGQ (SGQ) — README

**Descrição**
- Sistema de Gestão da Qualidade (SGQ) para gestão de documentos, revisões e Lista Mestra.

**Requisitos**
- Python 3.8+ (Windows recomendado para este repositório).
- Dependências listadas em `requirements.txt`.

**Instalação (Windows PowerShell)**
```powershell
python -m venv venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Configuração e execução**
- Crie a database/inicialize dados:
```powershell
python init_db.py
```
- Inicie a aplicação:
```powershell
python run.py
# ou, alternativamente, configure FLASK_APP e use: flask run
```

**Usuários e perfis**
- Há perfis definidos em `app/models/usuario.py`.
- Foi adicionado o perfil:
  - `Auditor Externo / Técnico` — conta de acesso somente leitura.
- Para criar/atribuir este perfil: entre em **Admin → Gerenciar Usuários**, edite/crie um usuário e selecione `Auditor Externo / Técnico` no campo "Perfil".

**Mensagem exibida para ações proibidas**
- Quando um usuário sem permissão tentar executar uma ação protegida, a mensagem exibida é:

  "Você não tem permissão para executar esta ação."

**Permissões resumidas do perfil `Auditor Externo / Técnico`**
- Permitido:
  - Efetuar login
  - Visualizar lista de documentos
  - Visualizar detalhes / pré-visualizações
  - Acessar documentos Vigentes e Obsoletos (quando aplicável)
  - Visualizar Documentos Externos
  - Visualizar/baixar arquivos publicados (PDF/DOCX quando permitido)
  - Visualizar Lista Mestra
- Bloqueado (todas as rotas protegidas retornam 403):
  - Criar/editar documentos
  - Enviar/editar uploads de PDF/DOCX
  - Criar revisões, aprovar, publicar, obsoletar
  - Gerenciar Documentos Externos (criar/editar)
  - Gerenciar usuários
  - Editar configurações ou metadados da Lista Mestra

**Arquivos importantes**
- `app/models/usuario.py` — perfis e helpers de permissão
- `app/utils/decorators.py` — decoradores de controle de acesso
- `app/documentos/routes.py` — rotas principais de documentos
- `app/templates/` — templates (contém verificações de permissão para esconder botões)
- `.gitignore` — já atualizado para ignorar `venv`, `instance/`, `storage/`, etc.

**Testes**
- Se houver testes, execute:
```powershell
pytest -q
```

**Boas práticas**
- Não comitar arquivos em `instance/` ou `storage/` (já ignorados pelo `.gitignore`).
- Use usuários admin para testar criação/atribuição de perfis.

**Contribuição / Deploy**
- Faça fork/branch para features; quando pronto, faça PR descrevendo mudanças.

---
Se quiser, eu posso também:
- Comitar o `README.md` para o repositório (`git add README.md && git commit -m "Add README"`).
- Gerar um resumo em formato README mais curto ou em inglês.
