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


def _abrir_avaliacoes(driver):
    xpaths = [
        '//button[@role="tab"][contains(@aria-label,"Avalia") or contains(@aria-label,"Reviews")]',
        '//button[@role="tab"][contains(.,"Avalia") or contains(.,"Reviews")]',
        '//button[contains(@aria-label,"Mais avalia") or contains(@aria-label,"More reviews")]',
        '//button[contains(.,"Mais avalia") or contains(.,"More reviews")]',
        '//div[@role="tab"][contains(.,"Avalia") or contains(.,"Reviews")]',
    ]
    for xp in xpaths:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                if el.is_displayed():
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(3)
                    return True
        except Exception:
            continue
    return False


def _ordenar_por_mais_recentes(driver):
    try:
        for b in driver.find_elements(
            By.XPATH,
            '//button[contains(@aria-label,"Classificar") or contains(@aria-label,"Sort") '
            'or contains(.,"Classificar") or contains(.,"Sort")]',
        ):
            if b.is_displayed():
                driver.execute_script("arguments[0].click();", b)
                time.sleep(1.5)
                for op in driver.find_elements(By.XPATH, '//*[@role="menuitemradio"]'):
                    if re.search(r"recentes|newest", op.text, re.I):
                        driver.execute_script("arguments[0].click();", op)
                        time.sleep(3)
                        return
                return
    except Exception:
        pass


JS_SCROLL = """
const cards = document.querySelectorAll('div[data-review-id]');
if (!cards.length) return 0;
const last = cards[cards.length - 1];
last.scrollIntoView({block: 'end'});
let el = last.parentElement;
while (el) {
    const st = getComputedStyle(el);
    if ((st.overflowY === 'auto' || st.overflowY === 'scroll') && el.scrollHeight > el.clientHeight) {
        el.scrollTop = el.scrollHeight;
        break;
    }
    el = el.parentElement;
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

    # nome do autor
    nome = ""
    for sel in ["div.d4r55", ".d4r55", "button[data-href*='contrib'] div"]:
        els = card.find_elements(By.CSS_SELECTOR, sel)
        if els and els[0].text.strip():
            nome = els[0].text.strip()
            break
    if not nome and linhas:
        nome = linhas[0]

    # nota
    nota = None
    for el in card.find_elements(By.CSS_SELECTOR, '[role="img"][aria-label]'):
        label = (el.get_attribute("aria-label") or "").lower()
        m = re.search(r"(\d)", label)
        if m and ("estrela" in label or "star" in label):
            nota = int(m.group(1))
            break

    # data
    data_txt = ""
    for sel in ["span.rsqaWe", ".rsqaWe"]:
        els = card.find_elements(By.CSS_SELECTOR, sel)
        if els and els[0].text.strip():
            data_txt = els[0].text.strip()
            break
    data, _ = _parse_data_relativa(data_txt)
    if data is None:
        data, _ = _parse_data_relativa(texto_card)

    # comentário
    comentario = ""
    for sel in ["span.wiI7pd", "div.MyEned span", ".Jtu6Td", "div.MyEned"]:
        els = card.find_elements(By.CSS_SELECTOR, sel)
        if els and els[0].text.strip():
            comentario = els[0].text.strip()
            break

    if not comentario:
        ruido = re.compile(
            r"(estrela|star|atrás|ago|local guide|guia local|avaliações|reviews|fotos|photos|"
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
    avaliacoes = []
    driver = None

    try:
        driver = _criar_driver()
        driver.get(_forcar_ptbr(url))
        time.sleep(4)
        _aceitar_consentimento(driver)

        try:
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1")))
        except Exception:
            pass

        _abrir_avaliacoes(driver)
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-review-id]"))
            )
        except Exception:
            _abrir_avaliacoes(driver)
            time.sleep(3)

        _ordenar_por_mais_recentes(driver)

        sem_novos, anterior = 0, 0
        for _ in range(60):
            total = len({c.get_attribute("data-review-id")
                         for c in driver.find_elements(By.CSS_SELECTOR, "div[data-review-id]")})
            if total >= limite:
                break
            if total == anterior:
                sem_novos += 1
                if sem_novos >= 6:
                    break
            else:
                sem_novos, anterior = 0, total
            driver.execute_script(JS_SCROLL)
            time.sleep(2)

        vistos = set()
        for card in driver.find_elements(By.CSS_SELECTOR, "div[data-review-id]"):
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