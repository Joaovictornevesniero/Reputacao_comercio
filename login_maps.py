import os
import time

from selenium import webdriver
from selenium.webdriver.edge.options import Options

PERFIL = os.path.abspath("edge_profile_maps")

options = Options()
options.add_argument(f"--user-data-dir={PERFIL}")
options.add_argument("--lang=pt-BR")
options.add_argument("--window-size=1400,1000")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

driver = webdriver.Edge(options=options)
driver.get("https://accounts.google.com/ServiceLogin?service=chromiumsync&continue=https://www.google.com/maps")

print("\n>>> Faça login na sua conta Google na janela do Edge.")
print(">>> Quando terminar, FECHE a janela do Edge. O app continua sozinho.")

# espera a pessoa fechar o navegador
while True:
    try:
        _ = driver.window_handles
        if not driver.window_handles:
            break
        time.sleep(1)
    except Exception:
        break

try:
    driver.quit()
except Exception:
    pass

print("Sessão salva.")