from __future__ import annotations

# plano.py
# =============================================================================
# Geração de plano (lógica de negócio)
# - Coleta descrição e características
# - Monta ctx (flags)
# - Ajusta bases (QPT, EPI radios, EPIs por categoria)
# - APN-1: coleta dinâmica (17 ou 20), identifica por texto, responde por regras
# =============================================================================

import os
import re
import unicodedata
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from selenium.webdriver.common.by import By

from aplatquente.infra import Driver, clicar_botao_confirmar_rodape, safe_find_element


# =============================================================================
# YAML
# =============================================================================

def _dig(d: dict, path: Tuple[str, ...]) -> Optional[Any]:
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict):
            return None
        if p not in cur:
            return None
        cur = cur[p]
    return cur


def _first_present(d: dict, candidates: List[Tuple[str, ...]], default: Any) -> Any:
    for path in candidates:
        v = _dig(d, path)
        if v is not None:
            return v
    return default


def carregar_regras(regras_path: Optional[str] = None) -> Dict[str, Any]:
    if regras_path is None:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "."))
        regras_path = os.path.join(base_dir, "config", "regras.yaml")

    try:
        import yaml  # type: ignore
    except Exception as e:
        raise RuntimeError("PyYAML não instalado. Rode: pip install pyyaml>=6.0") from e

    if not os.path.exists(regras_path):
        raise FileNotFoundError(f"regras.yaml não encontrado em: {regras_path}")

    with open(regras_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    epi_radios_base = _first_present(
        data,
        candidates=[("epi_radios_base",), ("regras", "epi_radios_base"), ("bases", "epi_radios_base")],
        default={},
    )
    epis_categoria_base = _first_present(
        data,
        candidates=[("epis_categoria_base",), ("regras", "epis_categoria_base"), ("bases", "epis_categoria_base")],
        default={},
    )
    qpt_base = _first_present(
        data,
        candidates=[("qpt_base",), ("regras", "qpt_base"), ("bases", "qpt_base")],
        default={},
    )

    apn1_regras = _first_present(
        data,
        candidates=[("apn1_regras",), ("regras", "apn1_regras")],
        default={},
    )
    if not isinstance(apn1_regras, dict):
        apn1_regras = {}

    if not isinstance(epi_radios_base, dict):
        epi_radios_base = {}
    if not isinstance(epis_categoria_base, dict):
        epis_categoria_base = {}
    if not isinstance(qpt_base, dict):
        qpt_base = {}

    return {
        "regras_path": regras_path,
        "epi_radios_base": epi_radios_base,
        "epis_categoria_base": epis_categoria_base,
        "qpt_base": qpt_base,
        "apn1_regras": apn1_regras,
    }


# =============================================================================
# Normalização
# =============================================================================

def normalizar_texto(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.upper()
    s = re.sub(r"\s+", " ", s).strip()
    return s


# =============================================================================
# Coleta descrição / características
# =============================================================================

def coletar_descricao(driver: Driver, timeout: float) -> str:
    xps = [
        "//label[contains(., 'Descrição')]/following::textarea[1]",
        "//label[contains(., 'Descricao')]/following::textarea[1]",
        "//label[contains(., 'Descrição')]/following::input[1]",
        "//label[contains(., 'Descricao')]/following::input[1]",
        "//textarea[contains(@formcontrolname,'descr')]",
        "//textarea[contains(@name,'descr')]",
    ]
    for xp in xps:
        try:
            el = safe_find_element(driver, xp, timeout)  # type: ignore[arg-type]
            if el:
                val = (el.get_attribute("value") or "").strip()
                if not val:
                    val = (el.text or "").strip()
                if val:
                    print(f"[DEBUG] Descrição encontrada (xpath): {xp}")
                    return val
        except Exception:
            pass

    try:
        container = safe_find_element(driver, "//app-dados-da-etapa", timeout)  # type: ignore[arg-type]
        if container:
            full_text = container.text or ""
            match = re.search(
                r"(Descri[cç][aã]o)\s*-\s*(.*?)(?=\n\s*\n|\n[A-ZÀ-Ú]|$)",
                full_text,
                re.DOTALL | re.IGNORECASE,
            )
            if match:
                bloco = (match.group(2) or "").strip()
                bloco = re.sub(r"[\u25b6\u25c0\u25b2\u25bc•\-\u2013\u2014]", " ", bloco).strip()
                bloco = re.sub(r"\s+", " ", bloco).strip()
                if bloco:
                    print("[DEBUG] Descrição encontrada (regex).")
                    return bloco
    except Exception:
        pass

    print("[WARN] Nenhuma descrição encontrada.")
    return ""


def coletar_caracteristicas(driver: Driver, timeout: float) -> str:
    car_list: List[str] = []

    try:
        spans = driver.find_elements(By.XPATH, "//app-input-caracteristicas//span[@class='nomecaracteristica']")
        for span in spans:
            texto = (span.text or "").strip()
            if texto and texto not in car_list:
                car_list.append(texto)
        if car_list:
            res = ", ".join(car_list)
            print(f"[DEBUG] Características (método 1): {res}")
            return res
    except Exception as e:
        print(f"[DEBUG] Características método 1 falhou: {e}")

    try:
        fieldset = safe_find_element(driver, "//fieldset[contains(., 'Características do trabalho')]", timeout)  # type: ignore[arg-type]
        if fieldset:
            texto = fieldset.text or ""
            linhas = [lin.strip() for lin in texto.splitlines() if lin.strip()]
            for lin in linhas:
                if "Características do trabalho" in lin:
                    continue
                if lin and lin not in car_list:
                    car_list.append(lin)
            if car_list:
                res = ", ".join(car_list)
                print(f"[DEBUG] Características (método 2): {res}")
                return res
    except Exception as e:
        print(f"[DEBUG] Características método 2 falhou: {e}")

    try:
        container = safe_find_element(driver, "//app-dados-da-etapa", timeout)  # type: ignore[arg-type]
        if container:
            full_text = container.text or ""
            match = re.search(
                r"Características do trabalho\s*-\s*(.*?)(?=\n\s*\n|\n[A-ZÀ-Ú]|$)",
                full_text,
                re.DOTALL | re.IGNORECASE,
            )
            if match:
                bloco = (match.group(1) or "").strip()
                bloco = re.sub(r"[\u25b6\u25c0\u25b2\u25bc•\-\u2013\u2014]", " ", bloco).strip()
                linhas = [ln.strip() for ln in bloco.splitlines() if ln.strip()]
                if linhas:
                    res = ", ".join(linhas)
                    print(f"[DEBUG] Características (método 3): {res}")
                    return res
    except Exception as e:
        print(f"[WARN] Características método 3 falhou: {e}")

    print("[WARN] Nenhuma característica do trabalho encontrada.")
    return ""


# =============================================================================
# Contexto (flags)
# =============================================================================

def montar_contexto(descricao: str, caracteristicas: str) -> Dict[str, Any]:
    texto_full = normalizar_texto(f"{descricao} {caracteristicas}")
    ctx: Dict[str, Any] = {"texto_full": texto_full}

    patterns: Dict[str, str] = {
        "tem_espaco_confinado": r"\b(ESPACO CONFINADO|ESPAÇO CONFINADO|INTERIOR DE|DENTRO DE|TANQUE|VASO|CALDEIRA)\b",
        "tem_altura": r"\b(TRABALHO EM ALTURA|NR\s*35|NR-35|ALTURA ACIMA DE 2M|ACIMA DE 2M)\b",
        "tem_acesso_cordas": r"\b(ACESSO POR CORDAS|TRABALHO POR CORDAS|ALPINISMO INDUSTRIAL)\b",
        "tem_sobre_o_mar": r"\b(SOBRE O MAR)\b",

        "tem_chama": r"\b(CHAMA ABERTA|OXICORTE|MA[ÇC]ARICO|SOLD(A|AGEM)|CORTE|ESMERIL)\b",
        "tem_trat_mec": r"\b(TRATAMENTO MECANICO|TRATAMENTO MECÂNICO|TRAT\.?\s*MEC)\b",
        "tem_lixadeira": r"\b(ESMERILHADEIRA|ESMERIL|LIXADEIRA|POLITRIZ|DESBASTE)\b",

        "tem_hidrojato": r"\b(HIDROJATEAMENTO|HIDRO JATO|HIDROJATO|JATO DE AGUA|JATO DE ÁGUA)\b",
        "tem_partes_moveis": r"\b(PARTES MOVEIS|PARTES M[ÓO]VEIS|EIXO GIRANDO|CORREIA|ENGRENAGEM)\b",
        "tem_pressurizado": r"\b(PRESSURIZAD|PRESSAO|PRESSÃO|LINHA PRESSURIZADA|VASO PRESSURIZADO|ABERTURA DE LINHA|ABERTURA DE EQUIPAMENTO)\b",
        "tem_eletricidade": r"\b(ELETRIC|EL[ÉE]TRIC|ENERGIZAD|PAINEL|QUADRO ELETRICO|QUADRO EL[ÉE]TRICO|ARCO ELETRICO|ARCO EL[ÉE]TRICO)\b",

        "tem_h2s": r"\b(H2S|SULFETO DE HIDROGENIO|SULFETO DE HIDROG[ÊE]NIO)\b",
        "tem_radiacao": r"\b(RADIACAO IONIZANTE|RADIAÇÃO IONIZANTE)\b",
        "tem_mergulho": r"\b(MERGULHO)\b",
        "tem_temperatura_extrema": r"\b(TEMPERATURA EXTREMA|SUPERFICIE QUENTE|SUPERFÍCIE QUENTE|PROTECAO TERMICA|PROTEÇÃO TÉRMICA|FRIO EXTREMO|CRIOG[ÊE]NIC)\b",

        "tem_intervencao_controle_ou_protecao_paineis": r"\b(CIRCUITO DE CONTROLE|CIRCUITO DE PROTECAO|CIRCUITO DE PROTEÇÃO|PAINEL(ES)? ELETRIC|PAIN[ÉE]IS EL[ÉE]TRIC)\b",
        "tem_intervencao_nobreak_cc_critico": r"\b(NO-?BREAK|CORRENTE CONTINUA|CORRENTE CONTÍNUA|CC CRITIC|DC CRITIC)\b",
        "tem_interferencia_outras_areas": r"\b(INTERFERIR NA SEGURANCA OPERACIONAL|INTERFERIR NA SEGURANÇA OPERACIONAL|OUTRAS AREAS|OUTRAS ÁREAS)\b",
        "tem_centelha_faisca_estatica": r"\b(CENTELH|FAISC|ESTATICA|ESTÁTICA|ELETRICIDADE ESTATICA|ELETRICIDADE ESTÁTICA)\b",

        # Novas do modelo 20:
        "tem_produtos_quimicos": r"\b(PRODUTOS QUIMICOS|PRODUTOS QUÍMICOS|SUBSTANCIA CORROSIVA|SUBSTÂNCIA CORROSIVA|TOXIC|TÓXIC|ASFIXIANTE)\b",
        "tem_co2": r"\b(CO2|DI(O|Ó)XIDO DE CARBONO|AMBIENTES PROTEGIDOS POR CO2|PROTEGID(O|A)S? POR CO2)\b",

        # Q020 (indisponibilidade do SCI) – deixo como flag separada
        "tem_sci_indisp": r"\b(INDISPONIBILIDADE.*(COMBATE A INCENDIO|COMBATE A INC[ÊE]NDIO)|PROVOCANDO SUA INDISPONIBILIDADE)\b",
    }

    for k, pat in patterns.items():
        ctx[k] = bool(re.search(pat, texto_full))

    ctx["hazard_olhos"] = bool(ctx.get("tem_chama") or ctx.get("tem_trat_mec") or ctx.get("tem_lixadeira"))
    return ctx


# =============================================================================
# Ajuste bases (QPT / EPI / categorias)
# =============================================================================

def ajustar_base_qpt(ctx: Dict[str, Any], qpt_base: Mapping[str, str]) -> Dict[str, str]:
    return dict(qpt_base)


def ajustar_base_epi_radios(ctx: Dict[str, Any], epi_radios_base: Mapping[str, str]) -> Dict[str, str]:
    base = dict(epi_radios_base)

    def set_if_present(key: str, val: str) -> None:
        if key in base:
            base[key] = val

    tem_altura = bool(ctx.get("tem_altura") or ctx.get("tem_acesso_cordas") or ctx.get("tem_sobre_o_mar"))
    tem_sobre_mar = bool(ctx.get("tem_sobre_o_mar"))
    hazard_olhos = bool(ctx.get("hazard_olhos"))

    set_if_present("Q001_CINTO", "Sim" if tem_altura else "Não")
    set_if_present("Q003_COLETE", "Sim" if tem_sobre_mar else "Não")
    set_if_present("Q006_PROT_FACIAL", "Sim" if hazard_olhos else "Não")

    return base


def ajustar_base_epis_categoria(ctx: Dict[str, Any], epis_categoria_base: Mapping[str, List[str]]) -> Dict[str, List[str]]:
    base_sets: Dict[str, Set[str]] = {}
    for cat, itens in epis_categoria_base.items():
        base_sets[cat] = set(itens) if isinstance(itens, list) else set()

    if not bool(ctx.get("hazard_olhos")):
        base_sets["Óculos"] = {"ÓCULOS SEGURANÇA CONTRA IMPACTO"}

    if bool(ctx.get("tem_chama")):
        base_sets.setdefault("Luvas", set()).update({"LUVA ARAMIDA", "LUVA DE RASPA"})

    if bool(ctx.get("tem_hidrojato")):
        base_sets.setdefault("Corpo", set()).add("AVENTAL / ROUPA IMPERMEÁVEL (HIDROJATO)")

    return {cat: sorted(list(itens)) for cat, itens in base_sets.items()}


# =============================================================================
# APN-1 dinâmico: coleta e decisão por texto
# =============================================================================

_APN1_PATTERNS: List[Tuple[str, str]] = [
    ("alteracao_condicoes_operacionais", r"(ALTERACAO|ALTERAÇÃO).*(CONDICOES OPERACIONAIS|CONDIÇÕES OPERACIONAIS)|PARADA DE SISTEMAS DE SEGURANCA|PROVOCAR EMERGENCIA"),
    ("temperatura_extrema", r"TEMPERATURA EXTREMA|PROTECAO TERMICA|PROTEÇÃO TÉRMICA"),
    ("intervencao_controle_ou_protecao_paineis", r"INTERVENCAO EM CIRCUITO DE CONTROLE|INTERVENÇÃO EM CIRCUITO DE CONTROLE|CIRCUITO DE PROTECAO.*PAINEIS ELETRICOS|CIRCUITO DE PROTEÇÃO.*PAIN[ÉE]IS EL[ÉE]TRIC"),
    ("intervencao_nobreak_cc_critico", r"NO-?BREAK|CORRENTE CONTINUA CRITIC|CORRENTE CONTÍNUA CR[ÍI]TIC"),
    ("interfere_outras_areas", r"INTERFERIR NA SEGURANCA OPERACIONAL DE OUTRAS AREAS|INTERFERIR NA SEGURANÇA OPERACIONAL DE OUTRAS ÁREAS"),
    ("espaco_confinado", r"ESPACO CONFINADO|ESPAÇO CONFINADO"),
    ("altura_nr35", r"NR-35|TRABALHO EM ALTURA|ALTURA ACIMA DE 2M|ACIMA DE 2M"),
    ("sobre_o_mar", r"SOBRE O MAR"),
    ("risco_h2s", r"\bH2S\b|PRESENCA DE H2S|PRESENÇA DE H2S"),

    # Q010 (17 e 20) – a versão 20 é mais curta, então deixei amplo:
    ("chama_aberta_area_classificada", r"CHAMA ABERTA|SOLD(A|AGEM)|CORTE|ESMERIL"),

    ("risco_centelha_faisca_estatica", r"CENTELH|FAISC|ELETRICIDADE ESTATICA|ELETRICIDADE ESTÁTICA"),
    ("radiacao_ionizante", r"RADIACAO IONIZANTE|RADIAÇÃO IONIZANTE"),
    ("abertura_linha_pressurizado", r"ABERTURA DE EQUIPAMENTO|ABERTURA DE LINHA|PRESSURIZAD"),
    ("choque_ou_arco_eletrico", r"CHOQUE ELETRICO|CHOQUE EL[ÉE]TRICO|ARCO ELETRICO|ARCO EL[ÉE]TRICO|TRABALHO ENERGIZADO|PE1PBR00213"),

    ("partes_moveis", r"PARTES MOVEIS|PARTES M[ÓO]VEIS"),

    # Novas do modelo 20:
    ("produtos_quimicos", r"PRODUTOS QUIMICOS|PRODUTOS QUÍMICOS|SUBSTANCIA CORROSIVA|SUBSTÂNCIA CORROSIVA|TOXIC|TÓXIC|ASFIXIANTE"),
    ("mergulho", r"MERGULHO"),
    ("hidrojateamento", r"HIDROJATEAMENTO|HIDROJATO"),
    ("combate_incendio_co2", r"COMBATE A INCENDIO.*CO2|COMBATE A INC[ÊE]NDIO.*CO2|AMBIENTES PROTEGIDOS POR CO2|PROTEGID(O|A)S? POR CO2"),

    # Q020 (indisponibilidade) – refinado para não pegar Q019 só por “combate a incêndio”
    ("combate_incendio_indisponibilidade", r"PROVOCANDO SUA INDISPONIBILIDADE|INDISPONIBILIDADE.*(AREAS PROTEGIDAS|ÁREAS PROTEGIDAS)"),
]


def _identificar_chave_apn1(pergunta_norm: str) -> Optional[str]:
    for key, pat in _APN1_PATTERNS:
        if re.search(pat, pergunta_norm):
            return key
    return None


def coletar_apn1_itens(driver: Driver, timeout: float) -> List[Dict[str, Any]]:
    itens: List[Dict[str, Any]] = []

    rows = driver.find_elements(
        By.XPATH,
        "//app-apn1-da-etapa//div[starts-with(@id,'questao_') and contains(@class,'row')]"
    )
    if not rows:
        rows = driver.find_elements(
            By.XPATH,
            "//app-apn1-da-etapa//app-questionario//form//div[starts-with(@id,'questao_')]"
        )

    for row in rows:
        try:
            ordem = row.find_element(By.XPATH, ".//div[contains(@class,'ordem')]").text.strip()
        except Exception:
            ordem = ""

        try:
            pergunta = row.find_element(By.XPATH, ".//div[contains(@class,'pergunta')]").text.strip()
        except Exception:
            pergunta = (row.text or "").strip()

        pergunta_norm = normalizar_texto(pergunta)

        id_sim = ""
        id_nao = ""
        try:
            lbl_sim = row.find_element(By.XPATH, ".//label[normalize-space()='Sim']")
            id_sim = (lbl_sim.get_attribute("for") or "").strip()
        except Exception:
            pass
        try:
            lbl_nao = row.find_element(By.XPATH, ".//label[normalize-space()='Não' or normalize-space()='Nao']")
            id_nao = (lbl_nao.get_attribute("for") or "").strip()
        except Exception:
            pass

        selecionado_atual: Optional[str] = None
        try:
            if id_sim:
                inp_sim = driver.find_element(By.ID, id_sim)
                if inp_sim.is_selected():
                    selecionado_atual = "Sim"
            if id_nao and selecionado_atual is None:
                inp_nao = driver.find_element(By.ID, id_nao)
                if inp_nao.is_selected():
                    selecionado_atual = "Não"
        except Exception:
            pass

        itens.append(
            {
                "ordem": ordem,
                "pergunta": pergunta,
                "pergunta_norm": pergunta_norm,
                "id_sim": id_sim,
                "id_nao": id_nao,
                "selecionado_atual": selecionado_atual,
                "row_id": row.get_attribute("id") or "",
            }
        )

    return itens


def _resolver_resposta_apn1_por_regra(ctx: Dict[str, Any], regra: Any) -> str:
    if regra is None:
        return "Não"
    if isinstance(regra, str):
        r = regra.strip()
        if r in ("Sim", "Não"):
            return r
        return "Sim" if bool(ctx.get(r)) else "Não"
    return "Não"


def decidir_respostas_apn1(ctx: Dict[str, Any], itens: List[Dict[str, Any]], apn1_regras: Dict[str, Any]) -> List[Dict[str, Any]]:
    respostas_yaml = {}
    if isinstance(apn1_regras, dict):
        respostas_yaml = apn1_regras.get("respostas") or {}
    if not isinstance(respostas_yaml, dict):
        respostas_yaml = {}

    fallback_map = {
        "alteracao_condicoes_operacionais": "Não",
        "temperatura_extrema": "tem_temperatura_extrema",
        "intervencao_controle_ou_protecao_paineis": "tem_intervencao_controle_ou_protecao_paineis",
        "intervencao_nobreak_cc_critico": "tem_intervencao_nobreak_cc_critico",
        "interfere_outras_areas": "tem_interferencia_outras_areas",
        "espaco_confinado": "tem_espaco_confinado",
        "altura_nr35": "tem_altura",
        "sobre_o_mar": "tem_sobre_o_mar",
        "risco_h2s": "tem_h2s",
        "chama_aberta_area_classificada": "tem_chama",
        "risco_centelha_faisca_estatica": "tem_centelha_faisca_estatica",
        "radiacao_ionizante": "tem_radiacao",
        "abertura_linha_pressurizado": "tem_pressurizado",
        "choque_ou_arco_eletrico": "tem_eletricidade",
        "partes_moveis": "tem_partes_moveis",
        "produtos_quimicos": "tem_produtos_quimicos",
        "mergulho": "tem_mergulho",
        "hidrojateamento": "tem_hidrojato",
        "combate_incendio_co2": "tem_co2",
        "combate_incendio_indisponibilidade": "tem_sci_indisp",
    }

    out: List[Dict[str, Any]] = []

    for it in itens:
        pergunta_norm = it.get("pergunta_norm", "")
        key = _identificar_chave_apn1(pergunta_norm)

        if key and key in respostas_yaml:
            resp = _resolver_resposta_apn1_por_regra(ctx, respostas_yaml[key])
        elif key and key in fallback_map:
            resp = _resolver_resposta_apn1_por_regra(ctx, fallback_map[key])
        else:
            resp = "Não"
            print(f"[WARN] APN-1 não reconhecida: ordem={it.get('ordem','?')} row={it.get('row_id','')} :: {pergunta_norm[:180]}")

        it2 = dict(it)
        it2["key"] = key or "desconhecida"
        it2["resposta_planejada"] = resp
        out.append(it2)

    return out


# =============================================================================
# Orquestração
# =============================================================================

def gerar_plano_trabalho_quente(driver: Driver, timeout: float, regras_path: Optional[str] = None) -> Dict[str, Any]:
    regras = carregar_regras(regras_path)

    descricao = coletar_descricao(driver, timeout)
    caracteristicas = coletar_caracteristicas(driver, timeout)

    ctx = montar_contexto(descricao, caracteristicas)

    qpt = ajustar_base_qpt(ctx, regras["qpt_base"])
    epi_radios = ajustar_base_epi_radios(ctx, regras["epi_radios_base"])
    epis_cat = ajustar_base_epis_categoria(ctx, regras["epis_categoria_base"])

    apn1_itens = coletar_apn1_itens(driver, timeout)
    apn1_itens = decidir_respostas_apn1(ctx, apn1_itens, regras.get("apn1_regras", {}))

    apn1_por_ordem: Dict[str, str] = {}
    for it in apn1_itens:
        ordem = (it.get("ordem") or "").strip()
        if ordem:
            apn1_por_ordem[ordem] = it.get("resposta_planejada", "Não")

    return {
        "regras_path": regras["regras_path"],
        "descricao": descricao,
        "caracteristicas": caracteristicas,
        "ctx": ctx,
        "qpt": qpt,
        "epi_radios": epi_radios,
        "epis_cat": epis_cat,
        "apn1_itens": apn1_itens,
        "apn1_por_ordem": apn1_por_ordem,
    }


# =============================================================================
# Aplicação do plano
# =============================================================================
def aplicar_plano(driver, plano: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    """
    Aplica o plano gerado preenchendo as abas relevantes.
    Regra operacional: cada rotina deve clicar em Confirmar e aguardar salvar antes
    de trocar de aba.
    """

    resultado: Dict[str, Any] = {
        "qpt": None,
        "analise_ambiental": None,
        "epi_radios": None,
        "epi_cat": None,
        "apn1": None,
        "warnings": [],
    }

    try:
        from aplatquente.preenchimento import (
            preencher_analise_ambiental,
            preencher_apn1,
            preencher_questionario_pt,
            preencher_epi_adicional,
        )
        from aplatquente.epi import processar_aba_epi
    except Exception as e:  # pragma: no cover - proteção de runtime
        resultado["warnings"].append(f"Imports de preenchimento/epi falharam: {e}")
        return resultado

    def _confirmar(complemento: str) -> None:
        try:
            clicar_botao_confirmar_rodape(driver, timeout)
        except Exception as e:  # pragma: no cover - robustez
            resultado["warnings"].append(f"Confirmar após {complemento} falhou: {e}")

    # 1) Questionário PT
    try:
        qpt = plano.get("qpt", {}) or plano.get("questionario_pt", {}) or {}
        if qpt:
            resultado["qpt"] = preencher_questionario_pt(driver, qpt, timeout)
            _confirmar("Questionário PT")
    except Exception as e:
        resultado["warnings"].append(f"Questionário PT não aplicado: {e}")

    # 2) Análise Ambiental
    try:
        resultado["analise_ambiental"] = preencher_analise_ambiental(driver, timeout)
        _confirmar("Análise Ambiental")
    except Exception as e:
        resultado["warnings"].append(f"Análise Ambiental não aplicada: {e}")

    # 3) EPI adicional (radios)
    try:
        epi_rad = plano.get("epi_radios", {}) or plano.get("epi_adicional", {}) or {}
        if epi_rad:
            resultado["epi_radios"] = preencher_epi_adicional(driver, epi_rad, timeout)
            _confirmar("EPI adicional")
    except Exception as e:
        resultado["warnings"].append(f"EPI adicional não aplicado: {e}")

    # 4) EPIs por categoria
    try:
        epi_cat = plano.get("epis_cat", {}) or plano.get("epi_categoria", {}) or {}
        if epi_cat:
            resultado["epi_cat"] = processar_aba_epi(driver, epi_cat, timeout)
            _confirmar("EPI por categoria")
    except Exception as e:
        resultado["warnings"].append(f"EPI por categoria não aplicada: {e}")

    # 5) APN-1
    try:
        desc = plano.get("descricao", "") or ""
        carac = plano.get("caracteristicas", "") or ""
        resultado["apn1"] = preencher_apn1(driver, timeout, desc, carac)
        _confirmar("APN-1")
    except Exception as e:
        resultado["warnings"].append(f"APN-1 não aplicada: {e}")

    return resultado


def imprimir_plano(plano: Dict[str, Any]) -> None:
    print("\n====== PLANO DE TRABALHO A QUENTE GERADO ======")
    print(f"regras.yaml: {plano.get('regras_path','')}")

    print("\nDescrição:")
    print(plano.get("descricao", "") or "(vazio)")

    print("\nCaracterísticas:")
    print(plano.get("caracteristicas", "") or "(vazio)")

    print("\nContexto (flags):")
    ctx = plano.get("ctx", {}) or {}
    for k in sorted(ctx.keys()):
        if k == "texto_full":
            continue
        print(f"  - {k}: {ctx[k]}")

    print("\nEPI Adicional (radios):")
    for k, v in (plano.get("epi_radios", {}) or {}).items():
        print(f"  - {k}: {v}")

    print("\nAPN-1 (dinâmica):")
    itens = plano.get("apn1_itens", []) or []
    if not itens:
        print("  (nenhuma questão APN-1 encontrada na tela)")
    else:
        for it in itens:
            ordem = it.get("ordem", "").strip()
            key = it.get("key", "")
            resp = it.get("resposta_planejada", "")
            print(f"  - {ordem:>3} | {key:<34} => {resp}")

    print("==============================================\n")
