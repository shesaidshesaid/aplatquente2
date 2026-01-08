# aplatquente/preenchimento.py
from __future__ import annotations

import time
import unicodedata
from typing import Dict, List, Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

from aplatquente.infra import (
    click_like_legacy,
    confirmar_etapa,
    ensure_no_messagebox,
    goto_tab,
    safe_find_element,
)
from aplatquente.plano import (
    carregar_regras,
    coletar_apn1_itens,
    decidir_respostas_apn1,
    montar_contexto,
)


import re

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


def _resp_norm(v: str) -> str:
    """
    Normaliza para: 'SIM', 'NAO', 'NA'
    """
    n = _norm(v)

    if n in ("SIM", "S", "YES", "Y", "TRUE", "1"):
        return "SIM"

    if n in ("NAO", "NÃO", "N", "NO", "FALSE", "0"):
        return "NAO"

    if n in ("NA", "N/A", "N A", "NAO APLICAVEL", "NÃO APLICÁVEL", "NAO SE APLICA", "NÃO SE APLICA"):
        return "NA"

    # fallback: mantém n (mas o resto do código espera SIM/NAO/NA)
    return n


def _click(driver, el: WebElement) -> bool:
    try:
        return click_like_legacy(driver, el, max_attempts=3, scroll=True, label="click")
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            return False


def _parse_key_to_ordem(key: str) -> tuple[Optional[str], bool, str]:
    """
    (ordem_3dig, is_ordem_explicita, hint)
      - 'Q001_MUDANCA' -> ('001', False, 'MUDANCA')
      - 'Q001'         -> ('001', False, '')
      - '001'          -> ('001', True, '')
    """
    raw = (key or "").strip()
    if not raw:
        return None, False, ""

    head, hint = (raw.split("_", 1) + [""])[:2] if "_" in raw else (raw, "")
    head_u = head.strip().upper()
    hint = hint.strip()

    m = re.match(r"^Q(\d{3})", head_u)
    if m:
        return m.group(1), False, hint

    m = re.match(r"^(\d{3})$", head_u)
    if m:
        return m.group(1), True, hint

    return None, False, hint


def _index_rows_by_ordem(driver) -> Dict[str, WebElement]:
    """
    Indexa rows com radio e uma 'ordem' (001..).
    Funciona tanto em div#questao_* quanto em tr.
    """
    # tenta divs do padrão questao_*
    rows: List[WebElement] = []
    try:
        rows = driver.find_elements(By.XPATH, "//div[starts-with(@id,'questao_') and .//input[@type='radio']]")
    except Exception:
        rows = []

    # fallback tabela
    if not rows:
        try:
            rows = driver.find_elements(By.XPATH, "//tr[.//input[@type='radio']]")
        except Exception:
            rows = []

    out: Dict[str, WebElement] = {}
    for row in rows:
        try:
            ordem_el = row.find_elements(By.XPATH, ".//*[contains(@class,'ordem')]")
            txt = (ordem_el[0].text if ordem_el else (row.text or ""))
            m = re.search(r"\b(\d{3})\b", txt)
            if m:
                out[m.group(1)] = row
        except Exception:
            continue
    return out


def _find_row_by_hint(rows: List[WebElement], hint: str) -> Optional[WebElement]:
    hintn = _norm(hint)
    if not hintn:
        return None

    for row in rows:
        try:
            pergunta = row.find_elements(By.XPATH, ".//*[contains(@class,'pergunta')]")
            base_txt = pergunta[0].text if pergunta else (row.text or "")
            if hintn in _norm(base_txt):
                return row
        except Exception:
            continue
    return None


def _click_label_safe(driver, label_el: WebElement) -> bool:
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", label_el)
    except Exception:
        pass
    try:
        label_el.click()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", label_el)
            return True
        except Exception:
            return False


def _mark_row_radio_generic(driver, row: WebElement, resposta: str) -> bool:
    """
    Marca a resposta em um row com radios. Suporta SIM/NAO/NA.
    Preferência: clicar no LABEL associado (Angular reage melhor).
    """
    desired = _resp_norm(resposta)

    def label_matches(txt: str) -> bool:
        t = _resp_norm(txt)
        if desired == "SIM":
            return t == "SIM"
        if desired == "NAO":
            return t == "NAO"
        return t == "NA"

    labels = []
    try:
        labels = row.find_elements(By.XPATH, ".//label")
    except Exception:
        labels = []

    target = None
    for lb in labels:
        try:
            if label_matches(lb.text or ""):
                target = lb
                break
        except Exception:
            continue

    if not target:
        return False

    fid = (target.get_attribute("for") or "").strip()
    if fid:
        try:
            inp = driver.find_element(By.ID, fid)
            if inp.is_selected():
                return True
        except Exception:
            pass

    if not _click_label_safe(driver, target):
        return False

    if fid:
        try:
            inp = driver.find_element(By.ID, fid)
            return bool(inp.is_selected())
        except Exception:
            return True

    return True



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
    print("[STEP] Questionário PT...")
    goto_tab(driver, "Questionário PT", timeout)
    ensure_no_messagebox(driver, 2)

    # indexa rows por ordem
    rows_by_ordem = _index_rows_by_ordem(driver)

    # lista de rows para fallback por hint
    rows_list: List[WebElement] = []
    try:
        rows_list = driver.find_elements(By.XPATH, "//div[starts-with(@id,'questao_') and .//input[@type='radio']]")
    except Exception:
        rows_list = []
    if not rows_list:
        try:
            rows_list = driver.find_elements(By.XPATH, "//tr[.//input[@type='radio']]")
        except Exception:
            rows_list = []

    # normaliza o plano para ordem -> (resp, hint, origem) com prioridade para ordem explícita "001"
    plano_por_ordem: Dict[str, tuple[str, str, str]] = {}
    for k, v in (plano_qpt or {}).items():
        ordem, is_explicit, hint = _parse_key_to_ordem(k)
        if not ordem:
            continue
        if is_explicit or ordem not in plano_por_ordem:
            plano_por_ordem[ordem] = (v, hint, k)

    total = len(plano_por_ordem)
    ok = fail = 0

    for ordem in sorted(plano_por_ordem.keys()):
        resp, hint, origem = plano_por_ordem[ordem]

        row = rows_by_ordem.get(ordem)
        if not row and hint:
            row = _find_row_by_hint(rows_list, hint)

        if not row:
            print(f"[WARN][QPT] Não achei linha p/ ordem={ordem} (origem='{origem}', hint='{hint}')")
            fail += 1
            continue

        try:
            ensure_no_messagebox(driver, 1)
            if _mark_row_radio_generic(driver, row, resp):
                ok += 1
            else:
                fail += 1
            print(f"[INFO] QPT ordem {ordem} (origem='{origem}') -> {resp}")
        except StaleElementReferenceException:
            # reindexa e tenta 1x
            try:
                rows_by_ordem = _index_rows_by_ordem(driver)
                row2 = rows_by_ordem.get(ordem)
                if row2 and _mark_row_radio_generic(driver, row2, resp):
                    ok += 1
                    print(f"[INFO] QPT ordem {ordem} (retry) -> {resp}")
                else:
                    fail += 1
                    print(f"[WARN][QPT] Falhou marcar ordem {ordem} (retry)")
            except Exception:
                fail += 1

    time.sleep(0.2)
    confirmar_etapa(driver, timeout)
    return {"total": total, "ok": ok, "fail": fail}



# =============================================================================
# EPI adicional (radios na aba EPI)
# =============================================================================
def preencher_epi_adicional(driver, plano_epi: Dict[str, str], timeout: float) -> Dict[str, int]:
    """
    Preenche os rádios de EPI adicional necessários na aba EPI.
    Aceita chaves:
      - Q001_CINTO, Q002_VENT, ...
      - Q001, Q002, ...
      - 001, 002, ...
    """
    print("[STEP] EPI adicional (radios)...")
    goto_tab(driver, "EPI", timeout)
    ensure_no_messagebox(driver, 2)

    # indexa rows por ordem (001..)
    rows_by_ordem = _index_rows_by_ordem(driver)

    # lista para fallback por hint
    rows_list: List[WebElement] = []
    try:
        rows_list = driver.find_elements(By.XPATH, "//div[starts-with(@id,'questao_') and .//input[@type='radio']]")
    except Exception:
        rows_list = []
    if not rows_list:
        try:
            rows_list = driver.find_elements(By.XPATH, "//tr[.//input[@type='radio']]")
        except Exception:
            rows_list = []

    # normaliza plano para ordem -> (resp, hint, origem), prioridade para ordem explícita
    plano_por_ordem: Dict[str, tuple[str, str, str]] = {}
    for k, v in (plano_epi or {}).items():
        ordem, is_explicit, hint = _parse_key_to_ordem(k)
        if not ordem:
            continue
        if is_explicit or ordem not in plano_por_ordem:
            plano_por_ordem[ordem] = (v, hint, k)

    if not plano_por_ordem:
        return {"total": 0, "ok": 0, "fail": 0}

    total = len(plano_por_ordem)
    ok = fail = 0

    for ordem in sorted(plano_por_ordem.keys()):
        resp, hint, origem = plano_por_ordem[ordem]

        row = rows_by_ordem.get(ordem)
        if not row and hint:
            row = _find_row_by_hint(rows_list, hint)

        if not row:
            print(f"[WARN][EPI_RADIO] Não achei linha p/ ordem={ordem} (origem='{origem}', hint='{hint}')")
            fail += 1
            continue

        try:
            ensure_no_messagebox(driver, 1)

            if _mark_row_radio_generic(driver, row, resp):
                ok += 1
                print(f"[INFO] EPI adicional ordem {ordem} (origem='{origem}') -> {resp}")
            else:
                fail += 1
                print(f"[WARN][EPI_RADIO] Falhou marcar ordem {ordem} (origem='{origem}')")

        except StaleElementReferenceException:
            # reindexa e tenta 1x
            try:
                rows_by_ordem = _index_rows_by_ordem(driver)
                row2 = rows_by_ordem.get(ordem)
                if row2 and _mark_row_radio_generic(driver, row2, resp):
                    ok += 1
                    print(f"[INFO] EPI adicional ordem {ordem} (retry) -> {resp}")
                else:
                    fail += 1
                    print(f"[WARN][EPI_RADIO] Falhou marcar ordem {ordem} (retry)")
            except Exception:
                fail += 1
                print(f"[WARN][EPI_RADIO] Falhou marcar ordem {ordem} (retry exception)")

        except Exception:
            fail += 1
            print(f"[WARN][EPI_RADIO] Falhou marcar ordem {ordem} (exception)")

    time.sleep(0.2)
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
            if _mark_row_radio_generic(driver, row, desired):
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
            By.XPATH, 
            "//div[contains(@class,'row') and starts-with(@id,'questao_') and .//input[@type='radio']]"
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
