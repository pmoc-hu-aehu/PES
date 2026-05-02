"""
Módulo de consulta SICOR — lê códigos do painel GAS, faz OCR do previewer
e envia resultados de volta ao painel.

Pré-requisitos:
  pip install requests pygetwindow pytesseract Pillow
  Instalar Tesseract OCR: https://github.com/UB-Mannheim/tesseract/wiki
  (marcar "Add to PATH" no instalador)

Uso:
  python consulta_codigos.py               # inicia o loop de consultas
  python consulta_codigos.py --mapear      # mapeador de coordenadas
"""

import pyautogui
import pygetwindow as gw
import pytesseract
import requests
import json
import time
import sys
import os
import re
import threading
from PIL import Image, ImageEnhance

# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================

GAS_URL = "https://script.google.com/macros/s/AKfycbz8ICSJaaOzatVagFaElGzx_odU412n_WkTve_4utiZMWdhxuA3MGaATcxriNo7MfaMHQ/exec"

COD_MATERIAL_CAMPO = (211, 254)
IMP_BOTAO          = (557,  83)
LIMPAR_BOTAO       = (217,  75)

PREVIEWER_TITULO = "CPREQ40: Previewer"
POLL_INTERVAL    = 5

HOSTNAME = os.environ.get('COMPUTERNAME', 'bot-local')

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

pyautogui.PAUSE    = 0.1
pyautogui.FAILSAFE = True

# ==============================================================================
# ABORT (ESC)
# ==============================================================================

_abortado = False

def _monitor_esc():
    import msvcrt
    global _abortado
    while not _abortado:
        if msvcrt.kbhit():
            if msvcrt.getch() == b'\x1b':
                _abortado = True
                print("\n[ESC — abortando...]\n")
        time.sleep(0.05)

def _checar_abort():
    if _abortado:
        print("[Consulta abortada]")
        sys.exit(1)

# ==============================================================================
# COMUNICAÇÃO COM GAS
# ==============================================================================

def buscar_pendentes():
    try:
        r = requests.get(GAS_URL, params={'action': 'getPending'}, timeout=15)
        data = r.json()
        return data.get('pending', []) if data.get('success') else []
    except Exception as e:
        print(f"  [GAS] Erro ao buscar pendentes: {e}")
        return []

def atualizar_status(codigo, status):
    try:
        payload = json.dumps({'action': 'updateStatus', 'codigo': codigo, 'status': status})
        requests.post(GAS_URL, data=payload, timeout=15)
    except Exception as e:
        print(f"  [GAS] Erro ao atualizar status: {e}")

def enviar_resultados(linhas):
    try:
        payload = json.dumps({'action': 'saveResults', 'results': linhas})
        r = requests.post(GAS_URL, data=payload, timeout=20)
        return r.json().get('success', False)
    except Exception as e:
        print(f"  [GAS] Erro ao enviar resultados: {e}")
        return False

def enviar_heartbeat() -> str:
    """Envia heartbeat e retorna o comando atual do GAS (RUN / STOP / IDLE)."""
    try:
        payload = json.dumps({'action': 'heartbeat', 'hostname': HOSTNAME})
        r = requests.post(GAS_URL, data=payload, timeout=10)
        return r.json().get('command', 'IDLE')
    except Exception:
        return 'IDLE'

# ==============================================================================
# CONTROLE DE TELA
# ==============================================================================

def digitar_codigo(codigo):
    _checar_abort()
    pyautogui.click(*COD_MATERIAL_CAMPO)
    time.sleep(0.3)
    pyautogui.hotkey('ctrl', 'a')
    pyautogui.write(str(codigo), interval=0.05)
    pyautogui.press('enter')
    time.sleep(0.8)

def clicar_imprimir(timeout=45):
    _checar_abort()
    pyautogui.click(*IMP_BOTAO)
    print("  Carregando relatório...", end='', flush=True)
    inicio = time.time()

    while time.time() - inicio < timeout:
        _checar_abort()
        if _encontrar_previewer():
            print(f" pronto em {time.time()-inicio:.1f}s")
            time.sleep(0.1)
            return
        time.sleep(0.5)

    raise TimeoutError(f"Previewer não abriu em {timeout}s — abortando.")

def clicar_limpar():
    _checar_abort()
    pyautogui.click(*LIMPAR_BOTAO)
    time.sleep(0.3)

# ==============================================================================
# OCR DO PREVIEWER
# ==============================================================================

def _encontrar_previewer():
    wins = [w for w in gw.getAllWindows() if PREVIEWER_TITULO in w.title]
    return wins[0] if wins else None

def _preprocessar_imagem(img: Image.Image) -> Image.Image:
    # Escala 2x: melhora significativamente OCR para texto pequeno
    w, h = img.size
    img = img.resize((w * 2, h * 2), Image.LANCZOS)
    img = img.convert('L')
    img = ImageEnhance.Contrast(img).enhance(2.5)
    img = img.point(lambda p: 255 if p > 140 else 0)
    return img

def capturar_previewer() -> dict:
    """Captura o previewer e extrai material + linhas da tabela via OCR."""
    win = _encontrar_previewer()
    if not win:
        print("  Previewer não encontrado.")
        return {}

    try:
        win.maximize()
        time.sleep(0.5)
        win.activate()
        time.sleep(0.3)
    except Exception:
        pass

    left   = win.left   + 30
    top    = win.top    + 90
    width  = win.width  - 60
    height = win.height - 130

    screenshot = pyautogui.screenshot(region=(left, top, width, height))

    debug_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_previewer.png")
    screenshot.save(debug_path)

    img_proc = _preprocessar_imagem(screenshot)
    texto = pytesseract.image_to_string(img_proc, lang='por', config='--psm 6 --oem 3')

    return _parsear_texto(texto)


# ==============================================================================
# PARSING DO TEXTO OCR
# ==============================================================================

def _normalizar_data(s: str) -> str:
    """Normaliza datas: '0502/2026' → '05/02/2026', '07/4/2026' → '07/04/2026'."""
    m = re.match(r'(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})', s)
    if m:
        return f'{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}'
    digits = re.sub(r'[^\d]', '', s)
    if len(digits) == 8:
        return f'{digits[:2]}/{digits[2:4]}/{digits[4:]}'
    return s


def _parsear_linha_robusta(linha: str) -> dict | None:
    """
    Parser campo a campo, tolerante a erros de OCR comuns.

    Distinção chave: vlr_req/vlr_emp usam VÍRGULA ("16,64"),
    C.Custo usa PONTO ("25.200", "80.409") — evita confusão entre os campos.
    Documento/OC/data/c_custo são extraídos de trás para frente (busca pelo fim),
    tornando o parse imune a espaços extras inseridos pelo OCR no meio do documento.
    """
    s = linha.strip()

    # 1. Req: 3–6 dígitos no início
    m = re.match(r'^(\d{3,6})\s+(.*)', s)
    if not m:
        return None
    req = m.group(1)
    s   = m.group(2)

    # 2. Data req: dd/mm/yyyy com variações OCR (mês pode vir com 1 dígito: 07/4/2026)
    m = re.match(r'^(\d{1,2}[/.\-]?\d{1,2}[/.\-]?\d{4}|\d{8})\s+(.*)', s)
    if not m:
        return None
    data_req = _normalizar_data(m.group(1))
    s        = m.group(2)

    # 3. Situação (1 ou 2 palavras) + Qtde (inteiro)
    m = re.match(r'^(.+?)\s+(\d{1,6})\s+(.*)', s)
    if not m:
        return None
    situacao = m.group(1).strip()
    qtde     = m.group(2)
    s        = m.group(3)

    # 4. Vlr Req: apenas vírgula-decimal (moeda). Ponto-decimal = C.Custo, não é vlr.
    m = re.match(r'^(\d+,\d+)\s*(.*)', s)
    if not m:
        m = re.match(r'^(\d{3,})\s+(.*)', s)
        if not m:
            return None
    vlr_req = m.group(1)
    s       = m.group(2)

    # 5. Vlr Emp: vírgula-decimal (opcional)
    vlr_emp = ''
    m = re.match(r'^(\d+,\d+)\s*(.*)', s)
    if m:
        vlr_emp = m.group(1)
        s       = m.group(2)

    # 6–9. Restante: [documento?] [oc?] [data_emissao?] [c_custo?]
    # Busca de trás para frente — robusto mesmo que OCR insira espaços no documento.
    documento    = ''
    oc           = ''
    data_emissao = ''
    c_custo      = ''

    s = s.strip()
    if s:
        # Padrão completo: OC  data  c_custo
        m = re.search(
            r'(\d{3,6})\s+(\d{1,2}[/.\-]\d{2}[/.\-]\d{4})\s+([\d.]+)\s*$', s)
        if m:
            oc           = m.group(1)
            data_emissao = _normalizar_data(m.group(2))
            c_custo      = m.group(3)
            documento    = s[:m.start()].strip()
        else:
            # OC  c_custo (sem data emissão)
            m = re.search(r'(\d{3,6})\s+([\d.]+)\s*$', s)
            if m:
                oc        = m.group(1)
                c_custo   = m.group(2)
                documento = s[:m.start()].strip()
            else:
                # Só c_custo ponto-decimal no fim (ex: linha "Autorizado" sem OC)
                m = re.match(r'^([\d.]+)\s*$', s)
                if m:
                    c_custo = m.group(1)
                else:
                    # Só OC no fim
                    m = re.search(r'(\d{3,6})\s*$', s)
                    if m:
                        oc        = m.group(1)
                        documento = s[:m.start()].strip()
                    else:
                        documento = s

    return {
        'req':          req,
        'data_req':     data_req,
        'situacao':     situacao,
        'qtde':         qtde,
        'vlr_req':      vlr_req,
        'vlr_emp':      vlr_emp,
        'documento':    documento,
        'oc':           oc,
        'data_emissao': data_emissao,
        'c_custo':      c_custo,
    }


def _parsear_fallback(linhas: list) -> list:
    """Parser simples por espaços — usado apenas quando o parser robusto falha em tudo."""
    dados = []
    for linha in linhas:
        partes = linha.split()
        if len(partes) >= 3 and partes[0].isdigit():
            # Detecta se situação tem 2 palavras (partes[3] não é número)
            if len(partes) > 3 and not partes[3].isdigit():
                offset = 1
            else:
                offset = 0
            dados.append({
                'req':          partes[0],
                'data_req':     partes[1] if len(partes) > 1 else '',
                'situacao':     ' '.join(partes[2:3+offset]),
                'qtde':         partes[3+offset] if len(partes) > 3+offset else '',
                'vlr_req':      partes[4+offset] if len(partes) > 4+offset else '',
                'vlr_emp':      partes[5+offset] if len(partes) > 5+offset else '',
                'documento':    partes[6+offset] if len(partes) > 6+offset else '',
                'oc':           partes[7+offset] if len(partes) > 7+offset else '',
                'data_emissao': partes[8+offset] if len(partes) > 8+offset else '',
                'c_custo':      partes[9+offset] if len(partes) > 9+offset else '',
            })
    return dados


def _completar_com_continuacao(row: dict, linha: str) -> None:
    """
    Quando o Documento é longo e quebra em duas linhas no previewer,
    o OCR produz uma 2ª linha que não parece um novo registro.
    Esta função tenta completar os campos OC / data_emissao / c_custo
    que ficaram vazios combinando o fragmento anterior com a continuação.
    """
    s = (row.get('documento', '') + ' ' + linha).strip()

    # Padrão completo: ... OC  data  c_custo
    m = re.search(
        r'(\d{3,6})\s+(\d{1,2}[/.\-]\d{2}[/.\-]\d{4})\s+([\d.]+)\s*$', s)
    if m:
        row['oc']           = m.group(1)
        row['data_emissao'] = _normalizar_data(m.group(2))
        row['c_custo']      = m.group(3)
        row['documento']    = s[:m.start()].strip()
        return

    # Padrão sem data: ... OC  c_custo
    m = re.search(r'(\d{3,6})\s+([\d.]+)\s*$', s)
    if m:
        row['oc']        = m.group(1)
        row['c_custo']   = m.group(2)
        row['documento'] = s[:m.start()].strip()
        return

    # Sem padrão reconhecível — concatena ao documento
    row['documento'] = s


def _parsear_texto(texto: str) -> dict:
    linhas   = texto.strip().splitlines()
    material = ''
    dados    = []

    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue

        if linha.lower().startswith('material'):
            material = re.sub(r'^material\s*:\s*', '', linha, flags=re.IGNORECASE).strip()
            continue

        row = _parsear_linha_robusta(linha)
        if row:
            dados.append(row)
        elif dados:
            # Possível continuação do documento da linha anterior:
            # ocorre quando o campo Documento é muito longo e quebra
            # para a próxima linha no previewer do SICOR.
            prev = dados[-1]
            if not prev['oc'] and not prev['data_emissao']:
                _completar_com_continuacao(prev, linha)

    if not dados:
        dados = _parsear_fallback(linhas)

    return {'material': material, 'linhas': dados}


def fechar_previewer():
    win = _encontrar_previewer()
    if win:
        try:
            win.close()
            time.sleep(0.2)
            return
        except Exception:
            pass
    pyautogui.hotkey('alt', 'f4')
    time.sleep(0.2)

# ==============================================================================
# LOOP PRINCIPAL
# ==============================================================================

def _sicor_aberto() -> bool:
    """Verifica se a janela CPREQ40 (tela de consulta) está aberta."""
    wins = [w for w in gw.getAllWindows() if 'CPREQ40' in w.title]
    return bool(wins)

def loop_consultas():
    if GAS_URL == "COLE_AQUI_A_URL_DO_WEB_APP":
        print("[ERRO] Configure GAS_URL em consulta_codigos.py antes de executar.")
        sys.exit(1)

    t = threading.Thread(target=_monitor_esc, daemon=True)
    t.start()

    print(f"=== Loop de Consultas SICOR | {HOSTNAME} ===")
    print("  [ESC para abortar | Ctrl+C para sair]\n")

    # Aguarda o SICOR estar aberto antes de qualquer coisa
    print("  Aguardando o SICOR (CPREQ40) estar aberto...")
    while not _sicor_aberto():
        _checar_abort()
        print("  SICOR não está aberto — abra a tela de consulta.", end='\r')
        time.sleep(3)
    print("\n  SICOR detectado. Aguardando comando RUN no painel GAS...")

    primeiro_ciclo = True
    while True:
        _checar_abort()

        # Heartbeat → recebe comando do GAS
        comando = enviar_heartbeat()

        if comando == 'STOP':
            if primeiro_ciclo:
                # STOP sobrou de sessão anterior — aguarda novo comando
                print(f"  Aguardando... (comando anterior: STOP)", end='\r')
                time.sleep(POLL_INTERVAL)
                primeiro_ciclo = False
                continue
            print("  [GAS] Comando STOP recebido — encerrando.")
            break

        primeiro_ciclo = False

        if comando == 'PAUSE':
            print(f"  [PAUSADO] aguardando retomada...", end='\r')
            time.sleep(POLL_INTERVAL)
            continue

        if comando != 'RUN':
            print(f"  Aguardando... (comando: {comando})", end='\r')
            time.sleep(POLL_INTERVAL)
            continue

        # Garante que SICOR ainda está aberto antes de processar
        if not _sicor_aberto():
            print("\n  SICOR foi fechado — pausando até reabrir...")
            while not _sicor_aberto():
                _checar_abort()
                time.sleep(3)
            print("  SICOR detectado novamente.")

        pendentes = buscar_pendentes()

        if not pendentes:
            print(f"  Fila vazia — aguardando próximo ciclo...", end='\r')
            time.sleep(POLL_INTERVAL)
            continue

        print(f"\n  {len(pendentes)} código(s) na fila")

        for item in pendentes:
            _checar_abort()
            cmd = enviar_heartbeat()
            if cmd == 'STOP':
                print("\n  [GAS] STOP recebido — interrompendo lote.")
                break
            if cmd == 'PAUSE':
                print("\n  [GAS] PAUSE recebido — interrompendo lote.")
                break
            codigo = item['codigo']
            print(f"\n  [{codigo}] Digitando...")

            atualizar_status(codigo, 'Processando')

            try:
                digitar_codigo(codigo)
                clicar_imprimir()

                print(f"  [{codigo}] Capturando previewer...")
                resultado = capturar_previewer()

                material = resultado.get('material', '')
                # Corrige código OCR errado no nome do material (ex: "3614" → "3514")
                if material:
                    mc = re.match(r'^(\d+)\s*[-–]\s*(.*)', material)
                    if mc and mc.group(1) != str(codigo):
                        material = f"{codigo} - {mc.group(2)}"
                linhas   = resultado.get('linhas', [])

                fechar_previewer()
                clicar_limpar()

                if linhas:
                    print(f"  [{codigo}] {len(linhas)} linha(s) extraída(s) — enviando...")
                    rows = [{'codigo': codigo, 'material': material, **l} for l in linhas]
                    enviar_resultados(rows)
                    # status Concluído já marcado pelo saveResults no GAS
                else:
                    print(f"  [{codigo}] Nenhum dado encontrado.")
                    atualizar_status(codigo, 'Sem dados')

            except TimeoutError as e:
                print(f"\n  [{codigo}] TIMEOUT: {e}")
                atualizar_status(codigo, 'Erro')
                fechar_previewer()
                clicar_limpar()
            except Exception as e:
                print(f"  [{codigo}] Erro: {e}")
                atualizar_status(codigo, 'Erro')
                fechar_previewer()
                clicar_limpar()

            time.sleep(0.2)

        print("\n  Lote concluído.")


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--mapear':
        import pyautogui as _pa
        print("Mapeador — mova o mouse. Ctrl+C para sair.\n")
        try:
            while True:
                x, y = _pa.position()
                print(f"  X: {x:>4}  Y: {y:>4}", end='\r')
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nEncerrado.")
    else:
        loop_consultas()
