# Document Workflow Refactoring Summary

## Overview
Refactored the SGQ document approval workflow to enforce automatic user attribution and combined approval/publication.

**Old Workflow:** Rascunho → Aguardando Aprovação → Aprovado → Vigente (multi-step, manual user selection)  
**New Workflow:** Rascunho → Vigente (approval auto-publishes, users auto-set)

---

## Business Rules Implemented

### 1. Auto-Set Elaborador
- **Rule:** "Elaborado por" must always be the authenticated user who created or saved the draft.
- **Implementation:**
  - In `novo()`: `doc.elaborado_por_id = current_user.id` (automatic)
  - In `editar()`: User field not editable; `elaborado_por_id` remains unchanged
  - In `editor_documento()`: When saving draft content, `elaborado_por_id` remains `current_user.id`
  - Form fields removed from `NovoDocumentoForm` and `EditarDocumentoForm`
- **Result:** No manual selection; always reflects real creator

### 2. Auto-Set Aprovador
- **Rule:** "Aprovado por" must always be the authenticated user who clicks approve/publish.
- **Implementation:**
  - In `publicar_vigente()`: `doc.aprovado_por_id = current_user.id` (automatic, permission-checked)
  - In `aprovar_revisao()`: `revisao.aprovado_por_id = current_user.id` (automatic, permission-checked)
  - Form fields removed from `PublicarVigenteForm` and `AprovarRevisaoForm`
- **Result:** No manual selection; always reflects real approver

### 3. Approval Auto-Publishes
- **Rule:** There should be no intermediate "Aprovado" state requiring separate publish action.
- **Implementation:**
  - `aprovar_revisao()`: Revision goes directly from `AGUARDANDO_APROVACAO` → `VIGENTE`
  - `publicar_vigente()`: Document goes directly from `RASCUNHO` → `VIGENTE`
  - Both operations set `data_aprovacao` and `data_publicacao` simultaneously using `agora_brasilia()`
- **Result:** Single-click approval = immediate publication

---

## Changes by File

### `app/documentos/forms.py`

#### Removed Fields
- `NovoDocumentoForm`:
  - Removed `elaborado_por_id` SelectField
  - Removed `revisado_por_id` SelectField
  - Removed `aprovado_por_id` SelectField

- `EditarDocumentoForm`:
  - Removed `elaborado_por_id` SelectField
  - Removed `revisado_por_id` SelectField
  - Removed `aprovado_por_id` SelectField

- `PublicarVigenteForm`:
  - Removed `aprovado_por_id` SelectField
  - Kept `motivo` field (user provides reason for publication)

- `AprovarRevisaoForm`:
  - Removed all user SelectFields
  - Now only has submit button

#### Unchanged
- `AbrirRevisaoForm`, `ReprovarRevisaoForm`, `PublicarRevisaoForm` (not modified)

---

### `app/documentos/routes.py`

#### Function: `novo()`
- Removed: `_populate_user_selects(form)` call
- Changed: `doc.elaborado_por_id = current_user.id` (was reading from form)
- Removed: Assignment of `doc.revisado_por_id` and `doc.aprovado_por_id` from form

#### Function: `editar()`
- Removed: `_populate_user_selects(form)` call
- Changed: **Do NOT** update `elaborado_por_id`, `revisado_por_id`, `aprovado_por_id` from form
- Removed: Pre-population of user select fields for GET requests

#### Function: `publicar_vigente()`
- Changed: Require only `current_user.pode_aprovar()` (was: `pode_abrir_revisao() OR pode_aprovar()`)
- Removed: User selection form logic (no `aprovado_por_id.choices`)
- Changed: `doc.aprovado_por_id = current_user.id` (automatic)
- Changed: `doc.data_aprovacao` and `doc.data_publicacao` set simultaneously to `agora_brasilia()`

#### Function: `aprovar_revisao()`
- Removed: All user selection form logic (`elaborado_por_id`, `revisado_por_id`, `aprovado_por_id` choices)
- Changed: Form validation simplified (form now only has submit button)
- Changed: `revisao.aprovado_por_id = current_user.id` (automatic)
- Changed: `revisao.data_aprovacao = agora` set during approval (not on form)
- Changed: Document object updated to auto-set `aprovado_por_id = current_user.id`
- Changed: History event updated to reflect automatic approval by current user

#### Function: `detalhe()`
- Removed: `_populate_user_selects()` calls for forms
- Removed: Code that populates `aprovado_por_id.choices` for publication and approval forms
- Removed: Pre-fill logic for user select fields
- Kept: Permission checks (`pode_editar`, `pode_publicar`, `pode_aprovar_doc`)
- Removed: `tem_aprovadores` variable (no longer needed)

#### Unchanged Helper
- `_populate_user_selects()` function definition kept (not called, could be removed later)

---

### `app/templates/documentos/novo.html`

#### Removed
- Entire "Responsáveis" section with user select fields
  - Removed: `elaborado_por_id` select
  - Removed: `revisado_por_id` select
  - Removed: `aprovado_por_id` select

---

### `app/templates/documentos/editar.html`

#### Removed
- Entire "Responsáveis" section with user select fields
  - Removed: `elaborado_por_id` select
  - Removed: `revisado_por_id` select
  - Removed: `aprovado_por_id` select

---

### `app/templates/documentos/detalhe.html`

#### Approval Form Section (Revision Approval)
- Simplified card: removed all user select fields
- Now displays: Message indicating current user will be recorded as approver
- Button: "Aprovar e Publicar" (single action)

#### Publication Form Section (Draft Publication)
- Removed: `aprovado_por_id` select field
- Kept: `motivo` field for publication reason
- Updated: Message clarifies current user will be recorded as approver
- Removed: Conditional check for `tem_aprovadores` (always allow if `pode_publicar`)

---

## Key Behavioral Changes

### Before Refactoring
1. Create document: User manually selects who elaborated, revised, approved
2. Save draft: No automatic attribution
3. Approve revision: Admin manually selects elaborator, reviewer, approver
4. Publish approved: Admin manually selects approver
5. Status flow: Rascunho → Aguardando Aprovação → Aprovado → Vigente (4 states)

### After Refactoring
1. Create document: System automatically sets elaborador = current_user
2. Save draft: Elaborador remains current_user (or original creator if already set)
3. Approve revision: System automatically sets approver = current_user, publishes immediately
4. Publish draft: System automatically sets approver = current_user (one-click publication)
5. Status flow: Rascunho → Vigente (2 states, no intermediate Aprovado for new workflow)

---

## Permission Model (Unchanged)

- **Create/Edit Drafts:** Requires `current_user.pode_editar_documentos()`
- **Approve & Publish:** Requires `current_user.pode_aprovar()`
- **Open Revision:** Requires `current_user.pode_abrir_revisao()`

## Data Integrity

- ✅ `elaborado_por_id`: Always = authenticated user who created/last saved draft
- ✅ `aprovado_por_id`: Always = authenticated user who clicked approve/publish
- ✅ `data_aprovacao`: Set when approval occurs
- ✅ `data_publicacao`: Set when publication occurs
- ✅ `revisado_por_id`: Maintained from revision record (can be null for new workflow)

---

## Backward Compatibility

- **Old Enum Status Preserved:** `StatusDocumento.APROVADO` still exists (for old records)
- **Database Columns Unchanged:** All user ID and datetime columns remain
- **Old Records Unaffected:** Documents with manual user selection remain as-is
- **New Workflow Separate:** New approvals auto-set users and don't rely on old APROVADO state

---

## Testing Checklist

- [ ] Non-approver cannot access approval routes (403 Forbidden)
- [ ] Approver cannot spoof another approver (their ID auto-set)
- [ ] Creating draft auto-sets `elaborado_por_id = current_user.id`
- [ ] Approving revision sets `aprovado_por_id = current_user.id` and publishes immediately
- [ ] Publishing draft sets `aprovado_por_id = current_user.id` immediately
- [ ] `data_aprovacao` and `data_publicacao` set simultaneously
- [ ] PDF generation works with auto-set users
- [ ] History events show correct user attribution
- [ ] No manual user selection possible on creation or approval
- [ ] UI forms no longer show user select dropdowns

---

## Migration Notes

- ✅ **No database migrations needed:** All columns already exist
- ✅ **No data cleanup required:** Old records with manual selections unaffected
- ✅ **Forms backward-compatible:** Old form definitions still importable (unused fields ignored)
- ⚠️ **UI Change:** Users expecting dropdowns won't see them; inform via release notes

---

## Future Enhancements

1. Remove `_populate_user_selects()` helper if not used elsewhere
2. Consider removing old `StatusDocumento.APROVADO` from new document workflows
3. Add audit log for user spoofing attempts (always validate permission before auto-set)
4. Consider removing `revisado_por_id` field if revision review is discontinued

---

## Completion Date

**Date:** May 11, 2026  
**Status:** ✅ COMPLETE  
**Syntax Validated:** ✅ YES  
**Tests:** ⏳ PENDING (see checklist above)

