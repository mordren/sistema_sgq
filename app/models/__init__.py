# Re-export every model so the rest of the app can do:
#   from app.models import Usuario, Documento, ...

from app.models.usuario import Usuario, Perfil
from app.models.documento import Documento, TipoDocumento, StatusDocumento
from app.models.revisao import RevisaoDocumento
from app.models.historico import HistoricoEvento, AcaoEvento
from app.models.distribuicao import DistribuicaoDocumento, Area, TipoDistribuicao
from app.models.documento_externo import DocumentoExterno
from app.models.matriz_correlacao import MatrizCorrelacao
from app.models.lista_mestra_config import ListaMestraConfig
from app.models.alerta import Alerta
from app.models.consulta_remota import ConsultaRemota
from app.models.controle_versao_software import ControleVersaoSoftware
from app.models.exportacao_lote import ExportacaoLote

__all__ = [
    'Usuario', 'Perfil',
    'Documento', 'TipoDocumento', 'StatusDocumento',
    'RevisaoDocumento',
    'HistoricoEvento', 'AcaoEvento',
    'DistribuicaoDocumento', 'Area', 'TipoDistribuicao',
    'DocumentoExterno',
    'MatrizCorrelacao',
    'ListaMestraConfig',
    'Alerta',
    'ConsultaRemota',
    'ControleVersaoSoftware',
    'ExportacaoLote',
]
