# config/xpaths.py
# =============================================================================
# XPaths da interface APLAT (P-18) – Trabalho a Quente
# Centralização de seletores para facilitar manutenção e refatoração
# =============================================================================


# =============================================================================
# URLs (não é XPath, mas é constante de navegação do sistema)
# =============================================================================

URL_PROGRAMACAO_DIARIA = (
    "https://aplat.petrobras.com.br/#/permissaotrabalho/"
    "P-18/planejamento/programacaodiaria"
)


# =============================================================================
# BOTÕES PRINCIPAIS (tela e modais)
# =============================================================================

XPATH_BTN_EXIBIR_OPCOES = "//button[normalize-space()='Exibir opções']"
XPATH_BTN_PESQUISAR = "//button[normalize-space()='Pesquisar']"
XPATH_BTN_FECHAR = "//app-botoes-etapa//button[normalize-space()='Fechar']"
XPATH_BTN_CONFIRMAR = "//app-botoes-etapa//button[normalize-space()='Confirmar']"
XPATH_BTN_OK = "//app-messagebox//button[normalize-space()='Ok']"


# =============================================================================
# LOGIN / AUTENTICAÇÃO
# =============================================================================

# Possíveis botões de login (fallback)
LOGIN_BUTTON_XPATHS = [
    "//button[normalize-space()='Entrar']",
    "//button[normalize-space()='Acessar']",
    "//input[@type='submit']",
    "//button[contains(.,'Sign in') or contains(.,'Login')]",
]

# Campos de credenciais
XPATH_PASSWORD_FIELD = "//input[@type='password' and not(@disabled)]"
XPATH_PASSWORD_FIELD_ANY = "//input[@type='password']"

# Campos genéricos de usuário (texto/email)
XPATH_LOGIN_USER_FIELD = "//input[@type='text' or @type='email' or not(@type)]"


# =============================================================================
# CAMPOS DE FORMULÁRIO – ETAPA / PLANEJAMENTO
# =============================================================================

XPATH_CAMPO_DATA = "//input[@placeholder='Selecione uma data']"
XPATH_CAMPO_NUMERO = "//input[@formcontrolname='numeroetapa']"

# Tipo de trabalho / PT
XPATH_LABEL_TIPO_TRABALHO = (
    "//span[@id='label-subtitulo' and normalize-space()='Tipo Trabalho']"
)
XPATH_SELECT_TIPO_PT = (
    "//app-combo-box[@formcontrolname='tipoPT']//select"
)

# Fieldset de tipo de etapa
XPATH_FIELDSET_TIPO_ETAPA = (
    "//legend[contains(normalize-space(),'Tipo de Etapa')]/.."
)


# =============================================================================
# ABAS DE NAVEGAÇÃO (template)
# =============================================================================

def xpath_tab_by_label(label: str) -> str:
    """
    Retorna o XPath de uma aba da APLAT pelo texto visível.
    """
    return (
        "//ul[contains(@class,'tabAplat')]//a"
        f"[normalize-space()='{label}']"
    )


# =============================================================================
# INDICADORES DE TELA PRINCIPAL (pós-login)
# =============================================================================

MAIN_SCREEN_INDICATORS = [
    "//button[normalize-space()='Exibir opções']",
    "//a[normalize-space()='EPI']",
    "//h3[contains(.,'Cadastro de PT')]",
]


# =============================================================================
# RESULTADOS DE PESQUISA (fallback para primeira linha)
# =============================================================================

SEARCH_RESULT_XPATHS = [
    "(//app-grid//table/tbody/tr)[1]",
    "(//table//tbody//tr)[1]",
    "(//ul[contains(@class,'list-group')]"
    "//li[contains(@class,'listagem')])[1]",
]


# =============================================================================
# MODAIS (genéricos e mensagens)
# =============================================================================

XPATH_MODAL_CONTENT_GENERIC = "//div[contains(@class,'modal-content')]"

XPATH_MODAL_EXCLUIR_GIM_FAM = (
    "//h5[contains(.,'deseja realmente excluir o nº da GIM/FAM')]"
)

XPATH_MODAL_EPI_CODIGO_VAZIO = (
    "//h5[contains(.,'código de EPI não pode ser vazio')]"
)


# =============================================================================
# PLANO / DESCRIÇÃO DA ETAPA
# =============================================================================

XPATH_DESCRICAO_ETAPA_FALLBACK = [
    "//app-dados-da-etapa//textarea[contains(@formcontrolname,'descricao')]",
    "//textarea[contains(@formcontrolname,'descricao')]",
    "//textarea[@id='descricao']",
]

XPATH_CARACTERISTICAS_TRABALHO = (
    "//app-input-caracteristicas//span[@class='nomecaracteristica']"
)

XPATH_FIELDSET_CARACTERISTICAS = (
    "//fieldset[contains(.//legend, 'Características do trabalho')]"
)

XPATH_CONTAINER_DADOS_ETAPA = "//app-dados-da-etapa"


# =============================================================================
# QUESTIONÁRIO / APN1 / ANÁLISE AMBIENTAL
# =============================================================================

# Containers principais
XPATH_CONTAINER_APN1 = [
    "//div[@id='APN1']//div[contains(@class,'row') "
    "and starts-with(@id,'questao_')]",
    "//app-apn1//div[contains(@class,'row') "
    "and starts-with(@id,'questao_')]",
    "//div[contains(@class,'row') "
    "and starts-with(@id,'questao_')]",
]

XPATH_ANALISE_AMBIENTAL = (
    "//div[@id='AMB' or "
    ".//h4[contains(.,'O local de trabalho tem:')]]"
)


# =============================================================================
# XPATHS RELATIVOS (USO COM ELEMENTO-PAI)
# NÃO usar com driver.find_element diretamente
# =============================================================================

REL_XPATH_RADIO_CHECKED = ".//input[@type='radio' and @checked]"
REL_XPATH_RADIO_ALL = ".//input[@type='radio']"
REL_XPATH_RADIO_APN1 = ".//input[contains(@id,'APN1_')]"

REL_XPATH_SPAN_OPCAO_RADIO = ".//span[.//input[@type='radio']]"

REL_XPATH_PERGUNTA = ".//div[contains(@class,'pergunta')]"

REL_XPATH_ROWS_QUESTOES = ".//div[starts-with(@id,'questao_')]"

REL_XPATH_LABEL_NAO = (
    ".//label[contains("
    "translate(text(), 'ÁÀÂÃÉÊÍÓÔÕÚÇ', 'AAAAEEIOOOUC'), 'NAO')]"
)


# =============================================================================
# EPI – CONTAINERS, MODAIS E AÇÕES
# =============================================================================

XPATH_CONTAINER_EPI = (
    "//app-epi-da-etapa//section[@id='questionario']//div[@id='EPI']"
)

def xpath_epi_categoria(nome_categoria: str) -> str:
    """
    Retorna o XPath da categoria de EPI pelo nome.
    """
    return (
        "//app-epi-da-etapa//label"
        f"[normalize-space()='{nome_categoria}']"
    )

XPATH_EPI_MODAL_CONTENT = (
    "//app-epi-da-etapa//app-associar-epi"
    "//app-modal//div[contains(@class,'modal-content')]"
)

XPATH_EPI_MODAL_TABLE_ROWS = (
    "//app-epi-da-etapa//app-associar-epi//table//tr[.//td]"
)

XPATH_EPI_BTN_CONFIRMAR = (
    "//app-epi-da-etapa//app-associar-epi"
    "//button[normalize-space()='Confirmar']"
)

XPATH_EPI_BTN_CANCELAR = (
    "//app-epi-da-etapa//app-associar-epi"
    "//button[normalize-space()='Cancelar']"
)

def xpath_epi_linha_por_codigo(xpath_literal: str) -> str:
    """
    Retorna o XPath da linha da tabela de EPI pelo texto exato do código.
    """
    return (
        "//app-epi-da-etapa//app-associar-epi//table//tr"
        f"[.//td[normalize-space()={xpath_literal}]]"
    )


# =============================================================================
# FIM DO ARQUIVO
# =============================================================================
