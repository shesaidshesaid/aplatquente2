# aplatquente/preenchimento.py
from __future__ import annotations

import time
import unicodedata
from typing import Dict, Optional, Iterable, Tuple, List

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

from aplatquente.infra import (
    goto_tab,
    safe_find_element,
    ensure_no_messagebox,
    confirmar_etapa,
    click_like_legacy,
)


# =============================================================================
# Helpers
# =============================================================================

def _norm(s: str) -> str:
    s = s or ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.upper().strip()
    s = " ".join(s.split())
    return s


def _resp_norm(resp: str) -> str:
    r = _norm(resp)
    # normaliza variantes comuns
    if r in ("NAO", "NÃO"):
        return "NAO"
    if r in ("SIM",):
        return "SIM"
    if r in ("NA", "N/A", "N A"):
        return "NA"
    return r


def _click(driver, el: WebElement) -> bool:
    try:
        return click_like_legacy(driver, el, max_attempts=3, scroll=True, label="click")
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            return False


def _find_row_by_codigo(driver, codigo: str) -> Optional[WebElement]:
    """
    Tenta localizar uma 'linha' de pergunta por código (Q001 etc.).
    Pode ser TR (tabela) ou DIV/ROW.
    """
    codigo = codigo.strip()
    if not codigo:
        return None

    candidatos = [
        # tabela
        f"//tr[.//td[contains(normalize-space(.), '{codigo}')]]",
        f"//tr[contains(normalize-space(.), '{codigo}')]",
        # div genérico
        f"//div[contains(normalize-space(.), '{codigo}') and .//input[@type='radio']][1]",
        f"//*[contains(normalize-space(.), '{codigo}') and .//input[@type='radio']][1]",
    ]
    for xp in candidatos:
        el = safe_find_element(driver, xp, timeout=1.5)
        if el:
            return el
    return None


def _find_row_by_hint_text(driver, hint: str) -> Optional[WebElement]:
    """
    Fallback: localizar linha pela parte textual (ex.: 'ACOMP', 'MUDANCA', etc.).
    """
    hint = hint.strip()
    if not hint:
        return None

    # usa só um token para não ficar rígido demais
    token = hint.split()[0]
    candidatos = [
        f"//tr[contains(normalize-space(.), '{token}')]",
        f"//*[contains(normalize-space(.), '{token}') and .//input[@type='radio']][1]",
    ]
    for xp in candidatos:
        el = safe_find_element(driver, xp, timeout=1.5)
        if el:
            return el
    return None


def _pick_radio_in_row_by_label(driver, row: WebElement, resp: str) -> Optional[WebElement]:
    """
    Estratégia preferida: achar o input cujo label (for=ID) tem texto SIM/NAO/NA.
    """
    desired = _resp_norm(resp)

    radios = row.find_elements(By.XPATH, ".//input[@type='radio' and not(@disabled)]")
    for r in radios:
        rid = (r.get_attribute("id") or "").strip()
        if not rid:
            continue
        # label associado
        lbs = row.find_elements(By.XPATH, f".//label[@for='{rid}']")
        for lb in lbs:
            t = _resp_norm(lb.text or "")
            if t == desired:
                return r
    return None


def _pick_radio_in_row_by_value(row: WebElement, resp: str) -> Optional[WebElement]:
    """
    Fallback: tenta casar pelo atributo value (varia: 'Sim', 'Não', '0/1', 'true/false', etc.)
    """
    desired = _resp_norm(resp)

    value_map = {
        "SIM": {"SIM", "0", "TRUE", "YES", "Y"},
        "NAO": {"NAO", "NÃO", "1", "FALSE", "NO", "N"},
        "NA": {"NA", "2", "N/A"},
    }
    wanted = value_map.get(desired, {desired})

    radios = row.find_elements(By.XPATH, ".//input[@type='radio' and not(@disabled)]")
    for r in radios:
        v = _norm(r.get_attribute("value") or "")
        if v in wanted:
            return r
    return None


def _mark_row_radio(driver, row: WebElement, resp: str) -> bool:
    """
    Marca uma resposta em uma row de pergunta.
    Ordem:
      1) por label
      2) por value
      3) último fallback: clicar no primeiro/segundo rádio conforme SIM/NAO/NA
    """
    desired = _resp_norm(resp)

    r = _pick_radio_in_row_by_label(driver, row, desired) or _pick_radio_in_row_by_value(row, desired)
    if r:
        return _click(driver, r)

    radios = row.find_elements(By.XPATH, ".//input[@type='radio' and not(@disabled)]")
    if not radios:
        return False

    # fallback por posição (heurístico)
    if desired == "SIM":
        return _click(driver, radios[0])
    if desired == "NAO":
        return _click(driver, radios[1] if len(radios) > 1 else radios[0])
    if desired == "NA":
        return _click(driver, radios[2] if len(radios) > 2 else radios[-1])
    return False


# =============================================================================
# Questionário PT
# =============================================================================

def preencher_questionario_pt(driver, plano_qpt: Dict[str, str], timeout: float) -> Dict[str, int]:
    """
    Marca respostas no Questionário PT conforme plano_qpt (ex.: {'Q001_ALGO': 'Não', ...})
    """
    print("[STEP] Questionário PT...")
    goto_tab(driver, "Questionário PT", timeout)
    ensure_no_messagebox(driver, 2)

    total = ok = fail = 0

    for codigo_texto, resposta in (plano_qpt or {}).items():
        total += 1

        codigo = codigo_texto.split("_")[0].strip() if "_" in codigo_texto else codigo_texto.strip()
        hint = codigo_texto.split("_", 1)[1] if "_" in codigo_texto else ""

        row = _find_row_by_codigo(driver, codigo) or _find_row_by_hint_text(driver, hint)
        if not row:
            print(f"[WARN][QPT] Não achei linha p/ '{codigo_texto}'")
            fail += 1
            continue

        try:
            ensure_no_messagebox(driver, 1)
            if _mark_row_radio(driver, row, resposta):
                ok += 1
            else:
                fail += 1
            print(f"[INFO] QPT {codigo_texto} -> {resposta}")
        except StaleElementReferenceException:
            fail += 1

    time.sleep(0.3)
    confirmar_etapa(driver, timeout)
    return {"total": total, "ok": ok, "fail": fail}


# =============================================================================
# EPI adicional (radios na aba EPI)
# =============================================================================

def preencher_epi_adicional(driver, plano_epi: Dict[str, str], timeout: float) -> Dict[str, int]:
    """
    Preenche os rádios de EPI adicional necessários (Q001_CINTO etc.) na aba EPI.
    """
    print("[STEP] EPI adicional (radios)...")
    goto_tab(driver, "EPI", timeout)
    ensure_no_messagebox(driver, 2)

    total = ok = fail = 0

    for epi_cod, resp in (plano_epi or {}).items():
        total += 1
        codigo = epi_cod.split("_")[0].strip() if "_" in epi_cod else epi_cod.strip()
        hint = epi_cod.split("_", 1)[1] if "_" in epi_cod else ""

        # tenta achar um bloco que contenha Q00X e radios
        row = _find_row_by_codigo(driver, codigo) or _find_row_by_hint_text(driver, hint)
        if not row:
            print(f"[WARN][EPI_RADIO] Não achei linha p/ '{epi_cod}'")
            fail += 1
            continue

        try:
            ensure_no_messagebox(driver, 1)
            if _mark_row_radio(driver, row, resp):
                ok += 1
            else:
                fail += 1
            print(f"[INFO] EPI adicional {epi_cod} -> {resp}")
        except StaleElementReferenceException:
            fail += 1

    time.sleep(0.3)
    confirmar_etapa(driver, timeout)
    return {"total": total, "ok": ok, "fail": fail}


# =============================================================================
# Análise Ambiental (padrão: marcar "Não" em tudo)
# =============================================================================

def preencher_analise_ambiental(driver, timeout: float, resposta_padrao: str = "Não") -> Dict[str, int]:
    """
    Marca todas as perguntas da Análise Ambiental como resposta_padrao (default: Não).
    """
    print("[STEP] Análise Ambiental...")
    goto_tab(driver, "Análise Ambiental", timeout)
    ensure_no_messagebox(driver, 2)

    desired = _resp_norm(resposta_padrao)

    # candidatos de "rows" com radios
    row_xps = [
        "//tr[.//input[@type='radio']]",
        "//div[starts-with(@id,'questao_') and .//input[@type='radio']]",
        "//*[.//input[@type='radio'] and (self::div or self::tr)][1]",
    ]

    rows: List[WebElement] = []
    for xp in row_xps:
        try:
            rows = driver.find_elements(By.XPATH, xp)
            if rows:
                break
        except Exception:
            continue

    total = ok = fail = 0
    for row in rows:
        total += 1
        try:
            if _mark_row_radio(driver, row, desired):
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1

    print(f"[INFO] Análise Ambiental: total={total} ok={ok} fail={fail} (padrao={resposta_padrao})")
    time.sleep(0.3)
    confirmar_etapa(driver, timeout)
    return {"total": total, "ok": ok, "fail": fail}


# =============================================================================
# APN-1
# Mantém o seu processador robusto (por texto/ids) – se você já tiver outro,
# você pode manter o seu e deixar só este wrapper.
# =============================================================================

def preencher_apn1(driver, timeout: float, descricao: str, caracteristicas: str):
    """
    Wrapper: se você já tem o APN1Processor robusto no seu preenchimento.py,
    mantenha-o. Se ainda não tiver, implemente aqui.
    """
    # Se você já colou o APN1Processor que usamos anteriormente, chame ele aqui.
    # Caso contrário, por enquanto apenas navega e confirma (para não travar o fluxo).
    print("[STEP] APN-1...")
    goto_tab(driver, "APN-1", timeout)
    ensure_no_messagebox(driver, 2)

    # tenta ao menos garantir que existem radios na tela
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.XPATH, "//input[@type='radio']")))
    except TimeoutException:
        print("[WARN] APN-1: nenhum radio encontrado.")
        confirmar_etapa(driver, timeout)
        return {"total": 0, "ok": 0, "skipped": 0, "failed": 0}

    # Se você já tem APN1Processor real, substitua o retorno abaixo pela chamada dele.
    # Exemplo:
    #   proc = APN1Processor(driver, timeout)
    #   res = proc.preencher(descricao, caracteristicas)
    #   return res

    # Placeholder “não quebra o fluxo”
    print("[WARN] APN-1: handler real não plugado aqui (mantendo fluxo).")
    confirmar_etapa(driver, timeout)
    return {"total": 0, "ok": 0, "skipped": 0, "failed": 0}
