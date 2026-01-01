from __future__ import annotations

import os
import time
from typing import Optional, TypeAlias

from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.webdriver import WebDriver as EdgeDriver

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement

from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
    WebDriverException,
)

from selenium.webdriver.common.action_chains import ActionChains

Driver: TypeAlias = EdgeDriver

from aplatquente.config.xpaths import (
    MAIN_SCREEN_INDICATORS,
    SEARCH_RESULT_XPATHS,
    XPATH_BTN_EXIBIR_OPCOES,
    XPATH_CAMPO_DATA,
    XPATH_CAMPO_NUMERO,
    XPATH_BTN_PESQUISAR,
    XPATH_BTN_FECHAR,
    XPATH_BTN_CONFIRMAR,
    XPATH_BTN_OK,
)



# =============================================================================
# Configurações do Edge
# =============================================================================

EDGE_OPTIONS = [
    "--start-maximized",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--no-sandbox",
]

# =============================================================================
# Clique robusto (estilo legado), mas dentro do infra.py
# =============================================================================

def click_like_legacy(
    driver: Driver,
    element: WebElement,
    *,
    max_attempts: int = 3,
    scroll: bool = True,
    label: str = "",
) -> bool:
    """
    Clique robusto:
      1) ActionChains double_click
      2) element.click()
      3) JS click
    Retorna True se clicou sem estourar exceção relevante.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            if scroll:
                try:
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center', inline:'nearest'});",
                        element,
                    )
                    time.sleep(0.05)
                except Exception:
                    pass

            try:
                ActionChains(driver).double_click(element).perform()
                return True
            except Exception:
                pass

            try:
                element.click()
                return True
            except (ElementClickInterceptedException, Exception):
                pass

            try:
                driver.execute_script("arguments[0].click();", element)
                return True
            except Exception:
                pass

        except StaleElementReferenceException:
            if attempt == max_attempts:
                return False
            time.sleep(0.2 * attempt)

    return False




# =============================================================================
# Navegação por ABAS + CONFIRMAR (modal de etapa)
# Regras:
# - Após abrir a etapa (duplo clique), cai em "Dados da Etapa"
# - Para trabalhar em outra aba: clicar aba -> aguardar carregar -> operar
# - Ao terminar cada aba: clicar "Confirmar" (rodapé fixo) -> aguardar -> só então trocar de aba
# =============================================================================

from selenium.webdriver.support.wait import WebDriverWait  # (Pylance prefere este)
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

# --- XPaths das abas (texto é mais robusto; absolutos ficam como fallback) ---
TAB_XPATHS: dict[str, list[str]] = {
    "Questionário PT": [
        "//app-cadastrar-etapa//app-tabs//a[normalize-space()='Questionário PT']",
        "/html/body/app-root/div/app-permissao-trabalho/div/app-programacao-diaria/app-dynamic-component/app-form-etapa/app-modal/div/div/div/div[2]/div/app-cadastrar-etapa/app-tabs/ul/li[4]/a",
    ],
    "Análise Ambiental": [
        "//app-cadastrar-etapa//app-tabs//a[normalize-space()='Análise Ambiental']",
        "/html/body/app-root/div/app-permissao-trabalho/div/app-programacao-diaria/app-dynamic-component/app-form-etapa/app-modal/div/div/div/div[2]/div/app-cadastrar-etapa/app-tabs/ul/li[5]/a",
    ],
    "EPI": [
        "//app-cadastrar-etapa//app-tabs//a[normalize-space()='EPI']",
        "/html/body/app-root/div/app-permissao-trabalho/div/app-programacao-diaria/app-dynamic-component/app-form-etapa/app-modal/div/div/div/div[2]/div/app-cadastrar-etapa/app-tabs/ul/li[6]/a",
    ],
    "APN-1": [
        "//app-cadastrar-etapa//app-tabs//a[normalize-space()='APN-1']",
        "/html/body/app-root/div/app-permissao-trabalho/div/app-programacao-diaria/app-dynamic-component/app-form-etapa/app-modal/div/div/div/div[2]/div/app-cadastrar-etapa/app-tabs/ul/li[7]/a",
    ],
}

# Marcas (heurísticas) para confirmar que a aba carregou (fallbacks genéricos)
TAB_READY_XPATHS: dict[str, list[str]] = {
    "Questionário PT": [
        "//app-questionario-pt",
        "//app-questionario",
        "//div[contains(@id,'QUESTION') or contains(@id,'question')]",
    ],
    "Análise Ambiental": [
        "//app-analise-ambiental",
        "//app-analiseambiental",
        "//div[contains(@id,'ANALISE') or contains(@id,'analise')]",
    ],
    "EPI": [
        "//app-epi",
        "//div[@id='EPI']",
        "//label[contains(.,'EPI') or contains(.,'Epi')]",
    ],
    "APN-1": [
        "//app-apn1",
        "//div[@id='APN1']",
        "//input[@type='radio']",
    ],
}

# XPaths do rodapé fixo
XPATH_BTN_CONFIRMAR_FALLBACKS = [
    "//app-botoes-etapa//button[normalize-space()='Confirmar']",
    "//button[normalize-space()='Confirmar']",
]
XPATH_BTN_FECHAR_FALLBACKS = [
    "//app-botoes-etapa//button[normalize-space()='Fechar']",
    "//button[normalize-space()='Fechar']",
]


def ensure_no_messagebox(driver: Driver, timeout: float = 2.0) -> bool:
    """
    Fecha messagebox/alerta (ex.: botão OK) se aparecer.
    Retorna True se encontrou e fechou algo.
    """
    # você já tem XPATH_BTN_OK no seu config/xpaths.py; mantemos fallback
    candidatos = []
    try:
        candidatos.append(XPATH_BTN_OK)  # type: ignore[name-defined]
    except Exception:
        pass
    candidatos.extend([
        "//button[normalize-space()='OK']",
        "//button[normalize-space()='Ok']",
        "//button[contains(.,'OK')]",
    ])

    end = time.time() + timeout
    closed = False

    while time.time() < end:
        for xp in candidatos:
            try:
                btn = driver.find_elements(By.XPATH, xp)
                if btn:
                    b = btn[0]
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                    except Exception:
                        pass
                    try:
                        b.click()
                    except Exception:
                        try:
                            driver.execute_script("arguments[0].click();", b)
                        except Exception:
                            continue
                    closed = True
                    time.sleep(0.25)
                    break
            except Exception:
                continue
        if closed:
            # tenta limpar encadeamento de popups
            time.sleep(0.25)
            break

        time.sleep(0.15)

    return closed


def _tab_is_active(driver: Driver, tab_el: WebElement) -> bool:
    try:
        # às vezes o "active" fica no <li>, às vezes no <a>
        return driver.execute_script(
            """
            const a = arguments[0];
            const li = a.closest('li');
            const clsA = (a.getAttribute('class') || '');
            const clsL = li ? (li.getAttribute('class') || '') : '';
            const aria = (a.getAttribute('aria-selected') || '');
            return clsA.includes('active') || clsL.includes('active') || aria === 'true';
            """,
            tab_el,
        )
    except Exception:
        return False


def wait_tab_loaded(driver: Driver, tab_name: str, timeout: float) -> None:
    """
    Aguarda carregamento da aba (heurística):
    - aba fica ativa
    - e algum marcador do conteúdo aparece (se houver)
    - e eventuais messagebox são fechadas
    """
    ensure_no_messagebox(driver, 1.5)

    # se tiver marcador específico, espera por ele
    markers = TAB_READY_XPATHS.get(tab_name, [])
    if markers:
        def _marker_ok(d: Driver):
            for xp in markers:
                try:
                    if d.find_elements(By.XPATH, xp):
                        return True
                except Exception:
                    pass
            return False

        try:
            WebDriverWait(driver, timeout).until(_marker_ok)
        except TimeoutException:
            # fallback: não aborta, porque algumas abas não têm marcador confiável
            pass

    ensure_no_messagebox(driver, 1.5)


def goto_tab(driver: Driver, tab_name: str, timeout: float = 15.0) -> None:
    """
    Clica em uma aba e aguarda ela ficar ativa + carregar.
    IMPORTANTE: chame isso somente quando estiver "seguro" trocar de aba
    (ou seja, depois de Confirmar).
    """
    xps = TAB_XPATHS.get(tab_name)
    if not xps:
        raise ValueError(f"Tab desconhecida: {tab_name}")

    last_err: Exception | None = None

    for xp in xps:
        try:
            tab_el = WebDriverWait(driver, min(timeout, 8.0)).until(
                EC.element_to_be_clickable((By.XPATH, xp))
            )
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tab_el)
            except Exception:
                pass

            # clique robusto
            ok = click_like_legacy(driver, tab_el, max_attempts=3, scroll=False, label=f"TAB {tab_name}")
            if not ok:
                raise RuntimeError(f"Falha ao clicar aba {tab_name} via {xp}")

            # espera ficar ativa
            WebDriverWait(driver, timeout).until(lambda d: _tab_is_active(d, tab_el))

            # espera carregar conteúdo
            time.sleep(0.25)
            wait_tab_loaded(driver, tab_name, timeout)
            return

        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"Não foi possível abrir a aba '{tab_name}'. Erro: {last_err}")


def confirmar_etapa(driver: Driver, timeout: float = 20.0) -> None:
    """
    Clica no botão Confirmar (rodapé fixo), aguarda estabilizar e fecha messagebox se aparecer.
    """
    ensure_no_messagebox(driver, 1.0)

    candidatos = []
    try:
        candidatos.append(XPATH_BTN_CONFIRMAR)  # type: ignore[name-defined]
    except Exception:
        pass
    candidatos.extend(XPATH_BTN_CONFIRMAR_FALLBACKS)

    btn = None
    last_err: Exception | None = None

    for xp in candidatos:
        try:
            btn = WebDriverWait(driver, min(timeout, 8.0)).until(
                EC.element_to_be_clickable((By.XPATH, xp))
            )
            break
        except Exception as e:
            last_err = e

    if not btn:
        raise RuntimeError(f"Botão Confirmar não encontrado/clicável. Último erro: {last_err}")

    # clique robusto
    ok = click_like_legacy(driver, btn, max_attempts=3, scroll=True, label="CONFIRMAR")
    if not ok:
        raise RuntimeError("Falha ao clicar Confirmar.")

    # aguarda “acalmar” (Angular geralmente salva e reabilita UI)
    time.sleep(0.4)
    ensure_no_messagebox(driver, 3.0)

    # heurística: aguarda o próprio botão ficar clicável de novo (salvou/voltou)
    try:
        WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, XPATH_BTN_CONFIRMAR_FALLBACKS[0])))
    except Exception:
        # não é fatal; em alguns layouts o XPath muda
        pass

    time.sleep(0.2)


# =============================================================================
# Driver
# =============================================================================

def create_edge_driver() -> Driver:
    """
    Cria e retorna uma instância do WebDriver do Edge com opções configuradas.
    Procura o executável do msedgedriver em locais conhecidos.
    """
    options = EdgeOptions()
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    for arg in EDGE_OPTIONS:
        options.add_argument(arg)

    # Diretório do projeto (onde está este infra.py)
    base_dir = os.path.abspath(os.path.dirname(__file__))

    driver_paths = [
        os.path.join(base_dir, "msedgedriver.exe"),     # recomendado (na pasta do projeto)
        os.path.join(os.getcwd(), "msedgedriver.exe"),  # caso rode com outro cwd
        "msedgedriver.exe",                             # fallback: PATH
    ]

    last_error: Optional[Exception] = None

    for path in driver_paths:
        if os.path.exists(path):
            try:
                print(f"[INFO] Usando msedgedriver encontrado em: {path}")
                service = EdgeService(path)
                d = webdriver.Edge(service=service, options=options)
                try:
                    d.maximize_window()
                except Exception:
                    pass
                return d
            except Exception as e:
                last_error = e
                print(f"[WARN] Falha ao iniciar WebDriver com {path}: {e}")

    # Fallback: tentar PATH do sistema
    try:
        print("[INFO] Tentando iniciar WebDriver usando PATH do sistema.")
        d = webdriver.Edge(options=options)
        try:
            d.maximize_window()
        except Exception:
            pass
        return d
    except Exception as e:
        raise RuntimeError("Não foi possível iniciar o WebDriver Edge.") from (last_error or e)

# =============================================================================
# Funções utilitárias de espera e interação
# =============================================================================

def wait_for_document_ready(driver: Driver, timeout: float) -> None:
    """Aguarda o carregamento completo do documento (estado 'complete')."""
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

def safe_find_element(driver: Driver, xpath: str, timeout: float) -> Optional[WebElement]:
    """Localiza elemento sem lançar exceção em caso de timeout."""
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
    except TimeoutException:
        return None

def wait_and_click(driver: Driver, xpath: str, timeout: float, description: str = "") -> WebElement:
    """Espera um elemento ficar clicável e realiza o clique (fallback via JS)."""
    desc = description or xpath

    elem = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.XPATH, xpath))
    )
    try:
        elem.click()
    except (ElementClickInterceptedException, StaleElementReferenceException, Exception):
        driver.execute_script("arguments[0].click();", elem)

    print(f"[INFO] Clicou em {desc}.")
    return elem

def _get_element_rect(driver: Driver, el: WebElement):
    """Retorna retângulo (x,y,w,h) arredondado para detectar estabilidade visual."""
    return driver.execute_script(
        """
        const r = arguments[0].getBoundingClientRect();
        return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)];
        """,
        el,
    )

def wait_element_stable(
    driver: Driver,
    el: WebElement,
    timeout: float = 8.0,
    stable_for: float = 0.6,
    poll: float = 0.15,
) -> None:
    """
    Aguarda o elemento estabilizar (mesmo retângulo por stable_for segundos).
    Ajuda em Angular/SPA com repaint/reflow.
    """
    end = time.time() + timeout
    last_rect = None
    stable_since = None

    while time.time() < end:
        try:
            _ = el.is_displayed()
            rect = _get_element_rect(driver, el)

            if rect == last_rect:
                if stable_since is None:
                    stable_since = time.time()
                if (time.time() - stable_since) >= stable_for:
                    return
            else:
                last_rect = rect
                stable_since = None
        except Exception:
            last_rect = None
            stable_since = None

        time.sleep(poll)

    return

def wait_for_single_etapa_card(driver: Driver, timeout: float) -> WebElement:
    """
    Na tela intermediária, deve existir 1 card (app-etapa-row) visível.
    Retorna o primeiro visível.
    """
    def _pick(d: Driver):
        cards = d.find_elements(By.XPATH, "//app-etapa-row")
        visibles: list[WebElement] = []
        for c in cards:
            try:
                if c.is_displayed():
                    visibles.append(c)
            except Exception:
                pass
        if visibles:
            return visibles[0]
        return False

    return WebDriverWait(driver, timeout).until(_pick)

def wait_for_etapa_tabs_loaded(driver: Driver, timeout: float) -> None:
    """
    Confirma que abriu o modal/página com abas (EPI/APN-1/etc).
    """
    xps = [
        "//app-cadastrar-etapa//ul[contains(@class,'tabAplat')]",
        "//app-cadastrar-etapa//app-tabs//ul",
        "//app-cadastrar-etapa//app-tabs//a[normalize-space()='APN-1']",
        "//app-form-etapa//app-modal",
    ]

    def _ok(d: Driver):
        for xp in xps:
            try:
                if d.find_elements(By.XPATH, xp):
                    return True
            except Exception:
                pass
        return False

    WebDriverWait(driver, timeout).until(_ok)

def double_click_card_open_details(
    driver: Driver,
    timeout: float,
    max_attempts: int = 3,
) -> None:
    """
    Tela do card único:
    - espera card existir e estabilizar
    - dá double click robusto
    - aguarda abas carregarem
    """
    last_err: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            card = wait_for_single_etapa_card(driver, min(timeout, 12.0))

            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", card)
            except Exception:
                pass

            wait_element_stable(driver, card, timeout=8.0, stable_for=0.6, poll=0.15)

            # Double click via Actions
            try:
                ActionChains(driver).move_to_element(card).pause(0.05).double_click(card).perform()
            except Exception:
                # Fallback JS dblclick
                driver.execute_script(
                    """
                    const el = arguments[0];
                    el.dispatchEvent(new MouseEvent('dblclick', {bubbles:true, cancelable:true, view:window}));
                    """,
                    card,
                )

            # Aguarda abrir abas
            wait_for_etapa_tabs_loaded(driver, timeout)
            return

        except Exception as e:
            last_err = e
            time.sleep(0.6)

    raise RuntimeError(
        f"Não foi possível abrir detalhes da etapa (duplo clique no card falhou): {last_err}"
    )





# =============================================================================
# Login helpers (robustos contra "invalid element state")
# =============================================================================

def is_login_page_loaded(driver: Driver) -> bool:
    """Retorna True se existir campo de senha visível."""
    try:
        WebDriverWait(driver, 3).until(
            EC.visibility_of_element_located((By.XPATH, "//input[@type='password' and not(@disabled)]"))
        )
        return True
    except TimeoutException:
        return False


def wait_login_dom_stable(driver: Driver, timeout: float = 10.0) -> bool:
    """
    Aguarda estabilização do DOM da tela de login.
    Útil para SSO/Angular que reescrevem inputs e causam stale/invalid state.
    """
    end_time = time.time() + timeout
    last_html = ""

    while time.time() < end_time:
        try:
            html = driver.page_source
            if html == last_html:
                return True
            last_html = html
        except Exception:
            pass
        time.sleep(0.3)

    return True


def _is_editable_input(el: WebElement) -> bool:
    """Evita 'invalid element state' checando readonly/disabled/aria-disabled."""
    try:
        if not el.is_displayed() or not el.is_enabled():
            return False

        readonly = (el.get_attribute("readonly") or "").lower()
        disabled = (el.get_attribute("disabled") or "").lower()
        aria_disabled = (el.get_attribute("aria-disabled") or "").lower()

        if readonly in ("true", "readonly"):
            return False
        if disabled in ("true", "disabled"):
            return False
        if aria_disabled == "true":
            return False

        return True
    except Exception:
        return False


def _clear_and_type(driver: Driver, el: WebElement, text: str) -> bool:
    """
    Digitação robusta:
    - scroll + focus
    - Ctrl+A + Delete
    - send_keys
    - fallback JS (dispara input/change)
    """
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    except Exception:
        pass

    try:
        el.click()
    except Exception:
        pass

    # Limpeza confiável
    try:
        el.send_keys(Keys.CONTROL, "a")
        el.send_keys(Keys.DELETE)
    except Exception:
        try:
            el.clear()
        except Exception:
            pass

    # Tentativa normal
    try:
        el.send_keys(text)
        return True
    except WebDriverException:
        pass

    # Fallback JS
    try:
        driver.execute_script(
            """
            const el = arguments[0];
            const val = arguments[1];
            el.focus();
            el.value = val;
            el.dispatchEvent(new Event('input', {bubbles:true}));
            el.dispatchEvent(new Event('change', {bubbles:true}));
            """,
            el, text
        )
        return True
    except Exception:
        return False


def _wait_main_screen(driver: Driver, timeout: float) -> bool:
    """Confirma tela principal do APLAT por qualquer indicador conhecido."""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: any(d.find_elements(By.XPATH, xp) for xp in MAIN_SCREEN_INDICATORS)
        )
        return True
    except TimeoutException:
        return False


def _find_pwd_field(driver: Driver, timeout: float = 6.0) -> Optional[WebElement]:
    """Localiza campo de senha visível."""
    xps = [
        "//input[@type='password' and not(@disabled)]",
        "//input[@type='password']",
    ]
    for xp in xps:
        try:
            return WebDriverWait(driver, timeout).until(
                EC.visibility_of_element_located((By.XPATH, xp))
            )
        except TimeoutException:
            continue
    return None


def _find_user_field_near_pwd(driver: Driver, pwd_field: WebElement) -> Optional[WebElement]:
    """Localiza campo de usuário próximo ao password (mesmo form), com fallback global."""
    try:
        form = pwd_field.find_element(By.XPATH, "./ancestor::form[1]")
        candidates = form.find_elements(
            By.XPATH,
            ".//input[(not(@type) or @type='text' or @type='email') and not(@disabled)]"
        )
        for c in candidates:
            if _is_editable_input(c):
                return c
    except Exception:
        pass

    candidates = driver.find_elements(
        By.XPATH,
        "//input[(not(@type) or @type='text' or @type='email') and not(@disabled)]"
    )
    for c in candidates:
        if _is_editable_input(c):
            return c

    return None


def _perform_login(driver: Driver, username: str, password: str, timeout: float) -> bool:
    """
    Executa login robusto:
    - espera DOM estabilizar
    - ancora no campo de senha visível
    - procura usuário no mesmo form
    - digita com Ctrl+A/Delete e fallback JS
    - submete por botão ou ENTER
    - confirma tela principal
    """
    wait_login_dom_stable(driver, 8.0)

    pwd_field = _find_pwd_field(driver, 8.0)
    if not pwd_field:
        # Se não tem senha, pode estar em transição; tenta confirmar a tela principal
        return _wait_main_screen(driver, max(8.0, timeout))

    # aguarda editável
    end = time.time() + 6.0
    while time.time() < end and not _is_editable_input(pwd_field):
        time.sleep(0.2)

    if not _is_editable_input(pwd_field):
        return False

    user_field = _find_user_field_near_pwd(driver, pwd_field)
    if user_field and _is_editable_input(user_field):
        _clear_and_type(driver, user_field, username)

    ok_pwd = _clear_and_type(driver, pwd_field, password)
    if not ok_pwd:
        return False

    submit_xpaths = [
        "//button[@type='submit']",
        "//button[normalize-space()='Entrar']",
        "//button[normalize-space()='Acessar']",
        "//input[@type='submit']",
        "//button[contains(.,'Sign in') or contains(.,'Login')]",
    ]

    submitted = False
    for xp in submit_xpaths:
        try:
            btn = driver.find_element(By.XPATH, xp)
            if btn.is_displayed() and btn.is_enabled():
                try:
                    btn.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", btn)
                submitted = True
                break
        except Exception:
            continue

    if not submitted:
        try:
            pwd_field.send_keys(Keys.ENTER)
        except Exception:
            pass

    # aguarda staleness (SPA/SSO)
    try:
        WebDriverWait(driver, 6).until(EC.staleness_of(pwd_field))
    except Exception:
        pass

    return _wait_main_screen(driver, max(8.0, timeout))


def attempt_auto_login(
    driver: Driver,
    url: str,
    timeout: float,
    use_keyring: bool = False,
    user: Optional[str] = None,
    keyring_service: str = "aplat.petrobras",
    max_attempts: int = 3,
    retry_wait: float = 1.2,
) -> bool:
    """
    Abre a URL e tenta login automático com keyring.
    Você pediu para NÃO complicar com SSO pré-logado: então aqui a prioridade é
    keyring -> tentativas -> fallback manual.
    """
    print(f"[INFO] Acessando APLAT: {url}")
    driver.get(url)

    try:
        wait_for_document_ready(driver, timeout)
    except Exception:
        pass

    # Se a tela principal já apareceu, ok (não “assumimos”, nós confirmamos)
    if _wait_main_screen(driver, 4.0):
        print("[LOGIN] Tela principal já detectada. Prosseguindo.")
        return True

    if not (use_keyring and user):
        print("[LOGIN] Login automático não será usado (sem --use-keyring/--user).")
        return False

    # Keyring
    try:
        import keyring
        pwd = keyring.get_password(keyring_service, user)
    except Exception as e:
        pwd = None
        print(f"[WARN] Keyring indisponível ou erro: {e}")

    if not pwd:
        print(f"[WARN] Nenhuma senha encontrada no keyring (service='{keyring_service}', user='{user}').")
        return False

    for attempt in range(1, max_attempts + 1):
        print(f"[LOGIN] Tentando login automático (keyring) {attempt}/{max_attempts} para usuário {user}...")
        try:
            wait_login_dom_stable(driver, 8.0)
            ok = _perform_login(driver, user, pwd, timeout)
            if ok:
                print("[INFO] Login automático realizado com sucesso (keyring).")
                return True
        except Exception as e:
            msg = str(e).strip()
            print(f"[WARN] Tentativa {attempt} falhou: {msg[:180]}")

        # nova tentativa
        try:
            time.sleep(retry_wait)
            driver.refresh()
            time.sleep(0.8)
            try:
                wait_for_document_ready(driver, timeout)
            except Exception:
                pass
        except Exception:
            pass

    print("[ERROR] Todas as tentativas de login automático falharam.")
    return False


def prompt_manual_login(driver: Driver, timeout: float) -> None:
    """Login manual: usuário autentica no browser e confirma."""
    print("[INFO] Por favor, realize o login manualmente no navegador que abriu (SSO ou usuário/senha).")
    try:
        input("Após realizar o login e visualizar a tela principal do APLAT, pressione ENTER aqui...")
    except Exception:
        pass

    if _wait_main_screen(driver, timeout):
        print("[INFO] Login manual confirmado, prosseguindo.")
        return

    raise RuntimeError("Login manual não confirmado dentro do tempo esperado.")


# =============================================================================
# Pesquisa e Navegação por Abas
# =============================================================================

def perform_search(
    driver: Driver,
    data_str: str,
    numero_etapa: str,
    timeout: float,
    search_timeout: float,
    detail_wait: float,
) -> None:
    """Executa a busca da etapa no APLAT e abre a etapa até chegar no modal com abas (EPI/APN-1/etc)."""
    print(f"[INFO] Pesquisando etapa {numero_etapa} na data {data_str}...")

    wait_and_click(driver, XPATH_BTN_EXIBIR_OPCOES, timeout, "botão Exibir Opções")

    date_field = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.XPATH, XPATH_CAMPO_DATA))
    )
    date_field.clear()
    date_field.send_keys(data_str)
    print(f"[INFO] Data preenchida: {data_str}")

    num_field = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.XPATH, XPATH_CAMPO_NUMERO))
    )
    num_field.clear()
    num_field.send_keys(numero_etapa)
    print(f"[INFO] Número da etapa preenchido: {numero_etapa}")

    wait_and_click(driver, XPATH_BTN_PESQUISAR, timeout, "botão Pesquisar")

    try:
        result = WebDriverWait(driver, search_timeout).until(lambda d: _find_first_result(d))
    except TimeoutException:
        raise RuntimeError(f"Nenhum resultado encontrado para etapa {numero_etapa} na data {data_str}.")

    row_element, xpath_used = result
    try:
        row_element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", row_element)

    print(f"[INFO] Resultado da etapa {numero_etapa} aberto (XPath usado: {xpath_used}).")

    # PASSO OBRIGATÓRIO NO SEU FLUXO: card único -> double click -> abas carregadas
    double_click_card_open_details(driver, timeout=timeout, max_attempts=3)

    if detail_wait and detail_wait > 0:
        time.sleep(detail_wait)


def _find_first_result(driver: Driver):
    """Busca pelo primeiro elemento de resultado de pesquisa disponível, usando os XPaths conhecidos."""
    for xpath in SEARCH_RESULT_XPATHS:
        elements = driver.find_elements(By.XPATH, xpath)
        for elem in elements:
            try:
                if elem.is_displayed() and elem.is_enabled():
                    return (elem, xpath)
            except Exception:
                continue
    return False







# =============================================================================
# Fechar / Confirmar Etapa
# =============================================================================

def fechar_modal_etapa(driver: Driver, timeout: float) -> None:
    """Fecha o modal de etapa (após confirmar) se aberto."""
    try:
        btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, XPATH_BTN_FECHAR))
        )
        try:
            btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", btn)
        print("[INFO] Modal de etapa fechado.")
    except TimeoutException:
        pass


def clicar_botao_confirmar_rodape(driver: Driver, timeout: float) -> None:
    """Clica no botão 'Confirmar' no rodapé da etapa."""
    btn = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.XPATH, XPATH_BTN_CONFIRMAR))
    )
    try:
        btn.click()
    except Exception:
        driver.execute_script("arguments[0].click();", btn)

    # Pop-up de confirmação extra
    try:
        ok_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, XPATH_BTN_OK))
        )
        try:
            ok_btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", ok_btn)
    except TimeoutException:
        pass

    print("[INFO] Botão Confirmar acionado e confirmado (se necessário).")
