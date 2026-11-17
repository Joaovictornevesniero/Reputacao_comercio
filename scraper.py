import os
import re
import time
from datetime import date, timedelta
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

PERFIL = os.path.abspath("edge_profile_maps")  # o mesmo do login_maps.py
LIMITE_MAXIMO = 500  # teto de avaliações coletadas
MAX_ROLAGENS = 150

CARDS = "div[data-review-id]"


def _criar_driver():
    options = Options()
    options.add_argument(f"--user-data-dir={PERFIL}")
    options.add_argument("--lang=pt-BR")
    options.add_argument("--window-size=1400,1000")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Edge(options=options)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def _forcar_ptbr(url: str) -> str:
    p = urlparse(url)
    q = parse_qs(p.query)
    q["hl"] = ["pt-BR"]
    return urlunparse(p._replace(query=urlencode(q, doseq=True)))


def _aceitar_consentimento(driver):
    for t in ["Aceitar tudo", "Accept all"]:
        try:
            for b in driver.find_elements(By.XPATH, f'//button[contains(.,"{t}")]'):
                if b.is_displayed():
                    b.click()
                    time.sleep(2)
                    return
        except Exception:
            pass


# ---------- Abrir a lista completa ("Mais críticas" / "Mais avaliações") ----------
XPATHS_ABRIR = [
    '//button[contains(@aria-label,"Mais crític") or contains(@aria-label,"Mais avalia") or contains(@aria-label,"More reviews")]',
    '//button[contains(.,"Mais crític") or contains(.,"Mais avalia") or contains(.,"More reviews")]',
    '//*[@role="button"][contains(.,"Mais crític") or contains(.,"Mais avalia") or contains(.,"More reviews")]',
    '//button[contains(.,"Ver todas") or contains(.,"See all reviews")]',
    '//button[@role="tab"][contains(@aria-label,"crític") or contains(@aria-label,"Crític") or contains(@aria-label,"Avalia") or contains(@aria-label,"Reviews")]',
    '//button[@role="tab"][contains(.,"Crític") or contains(.,"Avalia") or contains(.,"Reviews")]',
    '//div[@role="tab"][contains(.,"Crític") or contains(.,"Avalia") or contains(.,"Reviews")]',
]

JS_CLICAR_TEXTO = """
const re = /(mais cr[ií]ticas|mais avalia|more reviews|todas as (cr[ií]ticas|avalia)|all reviews)/i;
const els = document.querySelectorAll('button, [role="button"], [role="tab"], a');
for (const el of els) {
    const t = (el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '');
    if (re.test(t) && el.offsetParent !== null) {
        el.scrollIntoView({block: 'center'});
        el.click();
        return t.trim().slice(0, 60);
    }
}
return null;
"""

JS_ROLAR_PAINEL = """
document.querySelectorAll('div[role="main"], div.m6QErb').forEach(e => {
    if (e.scrollHeight > e.clientHeight) e.scrollTop += 800;
});
"""


def _abrir_avaliacoes(driver):
    for _ in range(3):
        for xp in XPATHS_ABRIR:
            try:
                for el in driver.find_elements(By.XPATH, xp):
                    if not el.is_displayed():
                        continue
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(3)
                    print(f"[INFO] Cliquei em: {xp}")
                    return True
            except Exception:
                continue

        try:
            achou = driver.execute_script(JS_CLICAR_TEXTO)
            if achou:
                print(f"[INFO] Cliquei (por texto) em: {achou}")
                time.sleep(3)
                return True
        except Exception:
            pass

        driver.execute_script(JS_ROLAR_PAINEL)
        time.sleep(2)

    print("[AVISO] Não encontrei o botão 'Mais críticas'.")
    return False


def _ordenar_por_mais_recentes(driver):
    try:
        botao = WebDriverWait(driver, 8).until(EC.presence_of_element_located((
            By.XPATH,
            '//button[contains(@aria-label,"Classificar") or contains(@aria-label,"Ordenar") '
            'or contains(@aria-label,"Sort")]'
        )))
        driver.execute_script("arguments[0].click();", botao)
        time.sleep(1.5)
        for op in driver.find_elements(By.XPATH, '//*[@role="menuitemradio"]'):
            if re.search(r"recentes|newest", op.text, re.I):
                driver.execute_script("arguments[0].click();", op)
                time.sleep(3)
                return True
        print("[AVISO] Menu de ordenação abriu, mas não achei 'Mais recentes'.")
    except Exception as e:
        print(f"[AVISO] Não consegui ordenar por mais recentes: {type(e).__name__}")
    return False


# rola SÓ o painel que contém as avaliações (nunca a página inteira)
JS_SCROLL = """
const cards = document.querySelectorAll('div[data-review-id]');
if (!cards.length) return 0;
const last = cards[cards.length - 1];
let el = last.parentElement, alvo = null;
while (el) {
    const st = getComputedStyle(el);
    if ((st.overflowY === 'auto' || st.overflowY === 'scroll') && el.scrollHeight > el.clientHeight) {
        alvo = el; break;
    }
    el = el.parentElement;
}
if (alvo) {
    alvo.scrollTop = alvo.scrollHeight;
    alvo.dispatchEvent(new WheelEvent('wheel', {deltaY: 3000, bubbles: true}));
}
return cards.length;
"""

# ---------- Datas relativas ("há 2 meses") -> data aproximada ----------
_UNIDADES = r"(minutos?|horas?|dias?|semanas?|meses|mes|mês|anos?|minutes?|hours?|days?|weeks?|months?|years?)"
_NUM = r"(um|uma|a|an|\d+)"
RE_DATA_1 = re.compile(rf"h[áa]\s+{_NUM}\s+{_UNIDADES}", re.I)
RE_DATA_2 = re.compile(rf"{_NUM}\s+{_UNIDADES}\s+(?:atr[áa]s|ago)", re.I)


def _dias_da_unidade(u: str) -> int:
    u = u.lower()
    if u.startswith(("min", "hor", "hou")):
        return 0
    if u.startswith(("dia", "day")):
        return 1
    if u.startswith(("sem", "wee")):
        return 7
    if u.startswith(("mes", "mês", "mon")):
        return 30
    if u.startswith(("ano", "yea")):
        return 365
    return 0


def _parse_data_relativa(texto: str):
    if not texto:
        return None, ""
    m = RE_DATA_1.search(texto) or RE_DATA_2.search(texto)
    if not m:
        return None, ""
    n_txt, unidade = m.group(1).lower(), m.group(2)
    n = int(n_txt) if n_txt.isdigit() else 1
    dias = n * _dias_da_unidade(unidade)
    return date.today() - timedelta(days=dias), m.group(0)


def _extrair_card(driver, card):
    for btn in card.find_elements(By.TAG_NAME, "button"):
        try:
            if btn.text.strip().lower() in ("mais", "more"):
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.2)
        except Exception:
            pass

    texto_card = card.text or ""
    linhas = [l.strip() for l in texto_card.split("\n") if l.strip()]

    nome = ""
    for sel in ["div.d4r55", ".d4r55", "button[data-href*='contrib'] div"]:
        els = card.find_elements(By.CSS_SELECTOR, sel)
        if els and els[0].text.strip():
            nome = els[0].text.strip()
            break
    if not nome and linhas:
        nome = linhas[0]

    nota = None
    for el in card.find_elements(By.CSS_SELECTOR, '[role="img"][aria-label]'):
        label = (el.get_attribute("aria-label") or "").lower()
        m = re.search(r"(\d)", label)
        if m and ("estrela" in label or "star" in label):
            nota = int(m.group(1))
            break

    data_txt = ""
    for sel in ["span.rsqaWe", ".rsqaWe"]:
        els = card.find_elements(By.CSS_SELECTOR, sel)
        if els and els[0].text.strip():
            data_txt = els[0].text.strip()
            break
    data, _ = _parse_data_relativa(data_txt)
    if data is None:
        data, _ = _parse_data_relativa(texto_card)

    comentario = ""
    for sel in ["span.wiI7pd", "div.MyEned span", ".Jtu6Td", "div.MyEned"]:
        els = card.find_elements(By.CSS_SELECTOR, sel)
        if els and els[0].text.strip():
            comentario = els[0].text.strip()
            break

    if not comentario:
        ruido = re.compile(
            r"(estrela|star|atrás|ago|local guide|guia local|avaliações|críticas|reviews|fotos|photos|"
            r"^mais$|^more$|compartilhar|share|gostei|like|resposta|response)", re.I)
        cand = [l for l in linhas[1:] if not ruido.search(l) and len(l) > 25]
        comentario = max(cand, key=len) if cand else ""

    return {
        "nome": nome or "(sem nome)",
        "data": data,
        "data_texto": data_txt,
        "nota": nota if nota else 5,
        "comentario": comentario or "(Avaliação apenas com nota, sem texto)",
    }


def coletar_avaliacoes_maps(url: str, limite: int = 20) -> list[dict]:
    limite = min(limite, LIMITE_MAXIMO)
    avaliacoes = []
    driver = None

    try:
        driver = _criar_driver()
        driver.get(_forcar_ptbr(url))
        time.sleep(5)
        _aceitar_consentimento(driver)

        try:
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1")))
        except Exception:
            pass

        # 1) abre a lista completa ("Mais críticas")
        abriu = _abrir_avaliacoes(driver)
        time.sleep(2)
        if not abriu:
            abriu = _abrir_avaliacoes(driver)

        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, CARDS)))
        except Exception:
            pass

        # 2) ordena por mais recentes
        ordenou = _ordenar_por_mais_recentes(driver)
        print(f"[INFO] Lista aberta: {abriu} | Ordenado por mais recentes: {ordenou}")

        # 3) rola só o painel das avaliações
        # se não conseguiu abrir a lista, não fica rolando: desiste rápido
        paciencia = 10 if abriu else 2
        sem_novos, anterior = 0, 0
        for _ in range(MAX_ROLAGENS):
            cards_dom = driver.find_elements(By.CSS_SELECTOR, CARDS)
            total = len({c.get_attribute("data-review-id") for c in cards_dom})
            if total >= limite:
                anterior = total
                break
            if total == anterior:
                sem_novos += 1
                if sem_novos >= paciencia:
                    break
            else:
                sem_novos, anterior = 0, total

            if not cards_dom:
                break
            driver.execute_script(JS_SCROLL)
            time.sleep(2.5)

        print(f"[INFO] Cards na tela após rolar: {anterior}")

        # 4) extrai
        vistos = set()
        for card in driver.find_elements(By.CSS_SELECTOR, CARDS):
            if len(avaliacoes) >= limite:
                break
            rid = card.get_attribute("data-review-id")
            if not rid or rid in vistos:
                continue
            vistos.add(rid)
            try:
                avaliacoes.append(_extrair_card(driver, card))
            except Exception:
                continue

        print(f"[INFO] {len(avaliacoes)} avaliações coletadas.")
        if len(avaliacoes) <= 5:
            driver.save_screenshot("debug_maps.png")
            print(f"[DEBUG] Só {len(avaliacoes)} coletadas. Veja debug_maps.png | Título: {driver.title}")

    except Exception as e:
        print(f"[ERRO DO SCRAPER] {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    return avaliacoes