# aplatquente/epi.py
from __future__ import annotations

import time
import unicodedata
from typing import Dict, Iterable, Set

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from aplatquente.infra import click_like_legacy, confirmar_etapa, ensure_no_messagebox, goto_tab


def _norm(s: str) -> str:
    s = s or ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.upper().strip()
    s = " ".join(s.split())
    return s


def _click(driver, el: WebElement) -> bool:
    try:
        return click_like_legacy(driver, el, max_attempts=3, scroll=True, label="epi_click")
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            return False


# =============================================================================
# 1) EPI adicional: alias para não quebrar chamadas existentes
# =============================================================================

def aplicar_epi_adicional(driver, timeout: float, plano_epi_radios: Dict[str, str]):
    """
    Alias compatível com o resto do projeto.
    Mantém a lógica em preenchimento.py (radios).
    """
    from aplatquente.preenchimento import preencher_epi_adicional
    return preencher_epi_adicional(driver, plano_epi_radios, timeout)


# =============================================================================
# 2) EPIs por categoria (checkbox/toggle/lista)
# =============================================================================

def aplicar_epi_por_categoria(driver, epis_categorias: Dict[str, Iterable[str]], timeout: float):
    """
    Best-effort: marca itens de EPIs por categoria.
    Como o DOM real pode variar, a estratégia é:
      - entrar na aba EPI
      - para cada item: tentar achar checkbox/toggle próximo de um label com o texto do item
    Não tenta desmarcar nada.
    """
    print("[STEP] EPI por categoria...")
    goto_tab(driver, "EPI", timeout)
    ensure_no_messagebox(driver, 2)

    total = ok = fail = 0

    # garante que a aba EPI carregou algo (não rígido)
    try:
        WebDriverWait(driver, min(timeout, 10.0)).until(
            EC.presence_of_element_located((By.XPATH, "//*[self::app-epi or @id='EPI' or .//input[@type='checkbox'] or .//label]"))
        )
    except Exception:
        pass

    for categoria, itens in (epis_categorias or {}).items():
        catn = _norm(str(categoria))
        for item in (itens or []):
            total += 1
            itn = _norm(str(item))

            # 1) checkbox imediatamente associado a label contendo o item
            candidatos = [
                # 0) tabela com checkbox na primeira coluna e texto do item em <td>
                f"//tr[.//td[contains(translate(normalize-space(.), 'abcdefghijklmnopqrstuvwxyzáàâãéèêíìîóòôõúùûç', 'ABCDEFGHIJKLMNOPQRSTUVWXYZAAAAEEEIIIOOOOUUUC'), '{itn}')]]"
                f"//input[@type='checkbox']",

                f"//label[contains(translate(normalize-space(.), 'abcdefghijklmnopqrstuvwxyzáàâãéèêíìîóòôõúùûç', 'ABCDEFGHIJKLMNOPQRSTUVWXYZAAAAEEEIIIOOOOUUUC'), '{itn}')]"
                f"/preceding-sibling::input[@type='checkbox']",

                f"//label[contains(translate(normalize-space(.), 'abcdefghijklmnopqrstuvwxyzáàâãéèêíìîóòôõúùûç', 'ABCDEFGHIJKLMNOPQRSTUVWXYZAAAAEEEIIIOOOOUUUC'), '{itn}')]"
                f"/following-sibling::input[@type='checkbox']",

                # 2) label com for=ID e input checkbox com id correspondente
                f"//label[contains(translate(normalize-space(.), 'abcdefghijklmnopqrstuvwxyzáàâãéèêíìîóòôõúùûç', 'ABCDEFGHIJKLMNOPQRSTUVWXYZAAAAEEEIIIOOOOUUUC'), '{itn}') and @for]"
            ]

            marked = False

            for xp in candidatos:
                try:
                    els = driver.find_elements(By.XPATH, xp)
                    if not els:
                        continue

                    el0 = els[0]
                    # se for label[@for], resolve o input
                    if el0.tag_name.lower() == "label":
                        fid = (el0.get_attribute("for") or "").strip()
                        if fid:
                            inp = driver.find_elements(By.ID, fid)
                            if inp:
                                el0 = inp[0]

                    # se é input checkbox:
                    if el0.get_attribute("type") == "checkbox":
                        try:
                            if el0.is_selected():
                                marked = True
                                break
                        except Exception:
                            pass

                        if _click(driver, el0):
                            marked = True
                            break
                    else:
                        # às vezes clicar no label/toggle marca
                        if _click(driver, el0):
                            marked = True
                            break
                except Exception:
                    continue

            if marked:
                ok += 1
                print(f"[INFO] EPI CAT '{categoria}': marcou '{item}'")
            else:
                fail += 1
                print(f"[WARN] EPI CAT '{categoria}': não achei '{item}' (DOM pode ser diferente)")

    time.sleep(0.3)
    confirmar_etapa(driver, timeout)
    return {"total": total, "ok": ok, "fail": fail}


def processar_aba_epi(driver, epis_cat: Dict[str, Iterable[str]], timeout: float):
    """Wrapper público esperado: processa EPIs por categoria e retorna resumo."""
    try:
        return aplicar_epi_por_categoria(driver, epis_cat, timeout)
    except Exception as e:
        print(f"[WARN] Erro ao processar aba EPI: {e}")
        return None
