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
from aplatquente.plano import (
    carregar_regras,
    coletar_apn1_itens,
    decidir_respostas_apn1,
    montar_contexto,
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


def _mark_apn1_radio(driver, row: WebElement, resp: str) -> bool:
    desired = _resp_norm(resp)

    def matches(radio: WebElement) -> bool:
        rid = (radio.get_attribute("id") or "").strip()
        if rid:
            labels = row.find_elements(By.XPATH, f".//label[@for='{rid}']")
            for lb in labels:
                if _resp_norm(lb.text or "") == desired:
                    return True
        v = _resp_norm(radio.get_attribute("value") or "")
        return v == desired

    def activate(radio: WebElement) -> bool:
        try:
            if radio.is_selected() and matches(radio):
                return True
        except Exception:
            pass

        try:
            if radio.is_enabled() and _click(driver, radio):
                return True
        except Exception:
            pass

        try:
            res = driver.execute_script(
                """
                const el = arguments[0];
                if (!el) return false;
                el.scrollIntoView({block: 'center', behavior: 'smooth'});
                el.checked = true;
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                return el.checked === true;
                """,
                radio,
            )
            if res:
                return True
        except Exception:
            pass

        try:
            driver.execute_script("arguments[0].click();", radio)
            return True
        except Exception:
            return False

    radios = row.find_elements(By.XPATH, ".//input[@type='radio']")
    if not radios:
        return False

    for r in radios:
        try:
            if matches(r) and r.is_selected():
                return True
        except Exception:
            continue

    target = None
    for r in radios:
        if matches(r):
            target = r
            break

    if target is None:
        if desired == "SIM":
            target = radios[0]
        elif desired == "NAO":
            target = radios[1] if len(radios) > 1 else radios[0]
        else:
            target = radios[-1]

    return activate(target)


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
    print("[STEP] APN-1...")
    goto_tab(driver, "APN-1", timeout)
    ensure_no_messagebox(driver, 2)

    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, "//input[@type='radio']"))
        )
    except TimeoutException:
        print("[WARN] APN-1: nenhum radio encontrado.")
        confirmar_etapa(driver, timeout)
        return {"total": 0, "ok": 0, "fail": 0, "plano": {}}

    try:
        regras = carregar_regras()
    except Exception as e:
        print(f"[WARN] Falha ao carregar regras.yaml: {e}")
        regras = {}

    ctx = montar_contexto(descricao or "", caracteristicas or "")
    apn1_regras = regras.get("apn1_regras", {}) if isinstance(regras, dict) else {}

    itens = coletar_apn1_itens(driver, timeout)
    itens = decidir_respostas_apn1(ctx, itens, apn1_regras)

    plano_por_ordem = {
        (it.get("ordem") or "").strip(): it.get("resposta_planejada", "Não")
        for it in itens
        if (it.get("ordem") or "").strip()
    }

    rows = driver.find_elements(By.XPATH, "//div[starts-with(@id,'questao_') and .//input[@type='radio']]")
    if not rows:
        rows = driver.find_elements(
            By.XPATH, "//div[contains(@class,'row') and starts-with(@id,'questao_') and .//input[@type='radio')]"
        )

    total = ok = fail = 0
    for idx, row in enumerate(rows, 1):
        total += 1
        try:
            ordem_el = row.find_element(By.XPATH, ".//div[contains(@class,'ordem')]")
            ordem = (ordem_el.text or str(idx)).strip()
        except Exception:
            ordem = str(idx)

        resp = plano_por_ordem.get(ordem, "Não")

        try:
            ensure_no_messagebox(driver, 0.5)
            if _mark_apn1_radio(driver, row, resp):
                ok += 1
            else:
                fail += 1
            print(f"[INFO] APN-1 {ordem} -> {resp}")
        except StaleElementReferenceException:
            fail += 1

    time.sleep(0.3)
    confirmar_etapa(driver, timeout)
    return {"total": total, "ok": ok, "fail": fail, "plano": plano_por_ordem}
