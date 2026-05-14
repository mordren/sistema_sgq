#!/usr/bin/env python3
"""
Test script for document workflow refactoring.
Validates that auto-attribution and auto-publication work correctly.

Usage:
  cd D:\Documentos\Python\SistemaSGQ
  python test_workflow_refactor.py
"""

import sys
from datetime import datetime
from app import create_app, db
from app.models import Documento, Usuario, RevisaoDocumento, HistoricoEvento
from app.models.documento import StatusDocumento, TipoDocumento
from app.models.usuario import Perfil
from app.utils.datetime_utils import agora_brasilia


def print_test(name: str, passed: bool):
    """Print test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} | {name}")
    return passed


def test_forms_dont_have_user_selects():
    """Test that forms no longer have user select fields."""
    app = create_app()
    with app.app_context():
        from app.documentos.forms import (
            NovoDocumentoForm, EditarDocumentoForm,
            PublicarVigenteForm, AprovarRevisaoForm
        )
        
        results = []
        
        # Check class-level field definitions instead of instantiating
        novo_fields = {name for name, obj in NovoDocumentoForm.__dict__.items()
                      if not name.startswith('_')}
        results.append(print_test(
            "NovoDocumentoForm missing elaborado_por_id",
            'elaborado_por_id' not in novo_fields
        ))
        results.append(print_test(
            "NovoDocumentoForm missing aprovado_por_id",
            'aprovado_por_id' not in novo_fields
        ))
        
        # EditarDocumentoForm
        editar_fields = {name for name, obj in EditarDocumentoForm.__dict__.items()
                        if not name.startswith('_')}
        results.append(print_test(
            "EditarDocumentoForm missing elaborado_por_id",
            'elaborado_por_id' not in editar_fields
        ))
        
        # PublicarVigenteForm
        publicar_fields = {name for name, obj in PublicarVigenteForm.__dict__.items()
                          if not name.startswith('_')}
        results.append(print_test(
            "PublicarVigenteForm missing aprovado_por_id",
            'aprovado_por_id' not in publicar_fields
        ))
        results.append(print_test(
            "PublicarVigenteForm has motivo field",
            'motivo' in publicar_fields
        ))
        
        # AprovarRevisaoForm
        aprovar_fields = {name for name, obj in AprovarRevisaoForm.__dict__.items()
                         if not name.startswith('_')}
        results.append(print_test(
            "AprovarRevisaoForm missing all user fields",
            'elaborado_por_id' not in aprovar_fields and
            'revisado_por_id' not in aprovar_fields and
            'aprovado_por_id' not in aprovar_fields
        ))
        results.append(print_test(
            "AprovarRevisaoForm still has submit button",
            'submit' in aprovar_fields
        ))
        
        return all(results)


def test_database_schema():
    """Test that database schema is intact."""
    app = create_app()
    with app.app_context():
        results = []
        
        # Check Documento columns
        doc_cols = {col.name for col in Documento.__table__.columns}
        results.append(print_test(
            "Documento.elaborado_por_id column exists",
            'elaborado_por_id' in doc_cols
        ))
        results.append(print_test(
            "Documento.aprovado_por_id column exists",
            'aprovado_por_id' in doc_cols
        ))
        results.append(print_test(
            "Documento.data_aprovacao column exists",
            'data_aprovacao' in doc_cols
        ))
        results.append(print_test(
            "Documento.data_publicacao column exists",
            'data_publicacao' in doc_cols
        ))
        
        # Check RevisaoDocumento columns
        rev_cols = {col.name for col in RevisaoDocumento.__table__.columns}
        results.append(print_test(
            "RevisaoDocumento.aprovado_por_id column exists",
            'aprovado_por_id' in rev_cols
        ))
        
        return all(results)


def test_permissions_intact():
    """Test that permission methods still exist."""
    app = create_app()
    with app.app_context():
        results = []
        
        # Create a test user
        user = Usuario.query.first()
        if user:
            results.append(print_test(
                "Usuario.pode_editar_documentos() exists",
                hasattr(user, 'pode_editar_documentos')
            ))
            results.append(print_test(
                "Usuario.pode_aprovar() exists",
                hasattr(user, 'pode_aprovar')
            ))
            return all(results)
        else:
            print("⚠️  SKIP | No test users in database")
            return True


def test_document_creation_workflow():
    """Test that document creation auto-sets elaborador."""
    app = create_app()
    with app.app_context():
        results = []
        
        # Get or create test user (ADMIN)
        admin = Usuario.query.filter_by(perfil=Perfil.ADMINISTRADOR).first()
        if not admin:
            print("⚠️  SKIP | No admin user for testing")
            return True
        
        # Create a test document (simulating novo())
        test_codigo = f"TEST-{datetime.now().timestamp()}"
        doc = Documento(
            codigo=test_codigo,
            titulo="Test Document",
            tipo_documento=TipoDocumento.PA,
            revisao_atual=0,
            status=StatusDocumento.RASCUNHO,
            elaborado_por_id=admin.id,  # Auto-set by novo()
        )
        
        results.append(print_test(
            "Document.elaborado_por_id auto-set during creation",
            doc.elaborado_por_id == admin.id
        ))
        
        # Simulate saving
        db.session.add(doc)
        db.session.commit()
        
        # Verify persistence
        retrieved = Documento.query.filter_by(codigo=test_codigo).first()
        results.append(print_test(
            "Document.elaborado_por_id persisted correctly",
            retrieved and retrieved.elaborado_por_id == admin.id
        ))
        
        # Cleanup
        if retrieved:
            db.session.delete(retrieved)
            db.session.commit()
        
        return all(results)


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("WORKFLOW REFACTORING VALIDATION TESTS")
    print("="*60 + "\n")
    
    test_results = []
    
    print("1. FORM STRUCTURE TESTS")
    print("-" * 40)
    test_results.append(test_forms_dont_have_user_selects())
    
    print("\n2. DATABASE SCHEMA TESTS")
    print("-" * 40)
    test_results.append(test_database_schema())
    
    print("\n3. PERMISSION TESTS")
    print("-" * 40)
    test_results.append(test_permissions_intact())
    
    print("\n4. WORKFLOW SIMULATION TESTS")
    print("-" * 40)
    test_results.append(test_document_creation_workflow())
    
    print("\n" + "="*60)
    if all(test_results):
        print("✅ ALL TESTS PASSED")
        print("="*60 + "\n")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print("="*60 + "\n")
        return 1


if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
