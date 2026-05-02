import pyautogui
import time
import getpass
import sys
import os
import threading

pyautogui.PAUSE = 0.3
pyautogui.FAILSAFE = True

# ==============================================================================
# COORDENADAS  —  use: python automacao_sicor.py --mapear  para ajustar
# ==============================================================================

ICONE_SISTEMAS_HU = (902, 1040)
ICONE_HU_IMG      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icone_hu.png")
BOTAO_SISTEMA_UEL = (668, 761)
CHAPA_CAMPO       = (383, 265)
SENHA_CAMPO       = (362, 388)
SICOR_BOTAO       = (854, 525)
MATERIAL_BOTAO    = (338, 531)
CONSULTAS_MENU    = (245, 40)

# ==============================================================================

_abortado = False

def _monitor_esc():
    import msvcrt
    global _abortado
    while not _abortado:
        if msvcrt.kbhit():
            tecla = msvcrt.getch()
            if tecla == b'\x1b':  # ESC
                _abortado = True
                print("\n\n[ESC pressionado — abortando...]\n")
        time.sleep(0.05)

def checar_abort():
    if _abortado:
        print("[Automação abortada]")
        sys.exit(1)


def mapear_posicao_mouse():
    print("Mapeador ativo — mova o mouse. Ctrl+C para sair.\n")
    try:
        while True:
            x, y = pyautogui.position()
            print(f"  X: {x:>4}  Y: {y:>4}", end="\r")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nEncerrado.")


def capturar_icone_hu():
    x, y = ICONE_SISTEMAS_HU
    img = pyautogui.screenshot(region=(x - 30, y - 30, 60, 60))
    img.save(ICONE_HU_IMG)
    print(f"Ícone salvo em: {ICONE_HU_IMG}")


def capturar_onde_mouse():
    print("Posicione o mouse SOBRE o ícone SistemasHU e aguarde 5 segundos...")
    for i in range(5, 0, -1):
        x, y = pyautogui.position()
        print(f"  {i}s — mouse em X:{x} Y:{y}", end="\r")
        time.sleep(1)
    x, y = pyautogui.position()
    print(f"\nCapturando em X:{x} Y:{y}...")
    img = pyautogui.screenshot(region=(x - 20, y - 20, 40, 40))
    img.save(ICONE_HU_IMG)
    print(f"Ícone salvo em: {ICONE_HU_IMG}")
    print(f"Atualize ICONE_SISTEMAS_HU = ({x}, {y}) no script se necessário.")


def testar_icone():
    if not os.path.exists(ICONE_HU_IMG):
        print(f"Arquivo não encontrado: {ICONE_HU_IMG}")
        return

    screen_w, screen_h = pyautogui.size()
    print(f"Tela: {screen_w}x{screen_h}")

    taskbar = (0, screen_h - 80, screen_w, 80)
    debug_path = os.path.join(os.path.dirname(ICONE_HU_IMG), "debug_taskbar.png")
    pyautogui.screenshot(region=taskbar).save(debug_path)
    print(f"Print da taskbar salvo em: {debug_path}")

    print("\n--- Buscando na taskbar ---")
    for conf in [0.9, 0.8, 0.7, 0.6, 0.5]:
        try:
            pos = pyautogui.locateCenterOnScreen(ICONE_HU_IMG, confidence=conf, region=taskbar)
            if pos:
                print(f"  ACHEI com confidence={conf} em {pos}")
                break
            else:
                print(f"  Não encontrado com confidence={conf}")
        except Exception as e:
            import traceback
            print(f"  Erro: {e}")
            traceback.print_exc()
            break

    print("\n--- Buscando na tela toda ---")
    for conf in [0.8, 0.7, 0.6]:
        try:
            pos = pyautogui.locateCenterOnScreen(ICONE_HU_IMG, confidence=conf)
            if pos:
                print(f"  ACHEI na tela com confidence={conf} em {pos}")
                break
            else:
                print(f"  Não encontrado na tela com confidence={conf}")
        except Exception as e:
            print(f"  Erro: {e}")
            break


def passo1_abrir_sistemas_hu():
    checar_abort()
    print("Passo 1: Localizando SistemasHU...")
    if os.path.exists(ICONE_HU_IMG):
        try:
            screen_w, screen_h = pyautogui.size()
            taskbar = (0, screen_h - 80, screen_w, 80)
            pos = pyautogui.locateCenterOnScreen(ICONE_HU_IMG, confidence=0.7, region=taskbar)
            if pos:
                print(f"  Ícone encontrado em {pos}")
                pyautogui.click(pos)
                time.sleep(2)
                return
            print("  Não encontrado na taskbar, usando coordenada fixa.")
        except Exception as e:
            print(f"  Busca por imagem falhou ({e}), usando coordenada fixa.")
    print(f"  Usando coordenada fixa {ICONE_SISTEMAS_HU}")
    pyautogui.click(*ICONE_SISTEMAS_HU)
    time.sleep(2)


def passo2_abrir_sistema_uel():
    checar_abort()
    print("Passo 2: Abrindo Sistema UEL...")
    pyautogui.doubleClick(*BOTAO_SISTEMA_UEL)
    time.sleep(3)


def passo3_enter_abertura():
    checar_abort()
    print("Passo 3: Enter na tela de abertura...")
    pyautogui.press('enter')
    time.sleep(2)


def passo4_preencher_chapa(chapa):
    checar_abort()
    print("Passo 4: Preenchendo Chapa...")
    pyautogui.click(*CHAPA_CAMPO)
    pyautogui.write(chapa)
    pyautogui.press('enter')
    time.sleep(0.5)
    pyautogui.press('enter')
    time.sleep(1)


def passo5_f9_orgao():
    checar_abort()
    print("Passo 5: F9 para preencher Órgão...")
    pyautogui.press('f9')
    time.sleep(1)


def passo6_senha_login(senha):
    checar_abort()
    print("Passo 6: Digitando Senha...")
    pyautogui.write(senha)
    pyautogui.press('enter')
    time.sleep(0.5)
    pyautogui.press('enter')
    time.sleep(3)


def passo7_clicar_sicor():
    checar_abort()
    print("Passo 7: Clicando em SICOR...")
    pyautogui.click(*SICOR_BOTAO)
    time.sleep(2)


def passo8_clicar_material():
    checar_abort()
    print("Passo 8: Clicando em Material...")
    pyautogui.click(*MATERIAL_BOTAO)
    time.sleep(2)


def passo9_menu_consultas():
    checar_abort()
    print("Passo 9: Abrindo menu Consultas...")
    pyautogui.click(*CONSULTAS_MENU)
    time.sleep(0.5)


def passo10_navegar_compra():
    checar_abort()
    print("Passo 10: Navegando até Compra...")
    for _ in range(10):
        pyautogui.press('down')
        time.sleep(0.1)
    pyautogui.press('enter')
    time.sleep(0.3)
    pyautogui.press('enter')
    time.sleep(2)


def main():
    print("=== Automação RPA — Sistema UEL ===")
    print("  [ESC para abortar a qualquer momento]\n")
    chapa = input("Chapa: ")
    senha = getpass.getpass("Senha: ")

    t = threading.Thread(target=_monitor_esc, daemon=True)
    t.start()

    print("\nIniciando em 3 segundos...")
    time.sleep(3)

    passo1_abrir_sistemas_hu()
    passo2_abrir_sistema_uel()
    passo3_enter_abertura()
    passo4_preencher_chapa(chapa)
    passo5_f9_orgao()
    passo6_senha_login(senha)
    passo7_clicar_sicor()
    passo8_clicar_material()
    passo9_menu_consultas()
    passo10_navegar_compra()

    print("\n=== Automação concluída! ===")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--mapear":
        mapear_posicao_mouse()
    elif len(sys.argv) > 1 and sys.argv[1] == "--capturar-icone":
        capturar_icone_hu()
    elif len(sys.argv) > 1 and sys.argv[1] == "--capturar-mouse":
        capturar_onde_mouse()
    elif len(sys.argv) > 1 and sys.argv[1] == "--testar-icone":
        testar_icone()
    else:
        main()
