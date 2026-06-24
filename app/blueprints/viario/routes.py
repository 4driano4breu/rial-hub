import io
import os
import json
import re
import shutil
import time
import glob
import uuid
from datetime import datetime
from pathlib import Path

from flask import render_template, request, Response, send_file, jsonify, current_app
from werkzeug.utils import secure_filename
import pandas as pd
import numpy as np
from PIL import Image as PILImage
import pytesseract
import openrouteservice
from openpyxl import load_workbook
from openpyxl.drawing.image import Image as XLImage

import app.storage as r2
from app.blueprints.viario import viario_bp
from app.blueprints.viario.config import (
    RODOVIAS, SERVICOS_GPS, SERVICOS_KM_FOTO, ROTAS_KM_FOTO, TAPA_BURACO,
    TESSERACT_CMD,
)

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

# Compatibilidade Pillow 9 / 10+ (LANCZOS foi movido em v10)
try:
    _LANCZOS = PILImage.Resampling.LANCZOS
except AttributeError:
    _LANCZOS = PILImage.LANCZOS

# ═══════════════════════════════════════════════════════════
#  INSTANCE PATH — resolvido em tempo de registro do blueprint
# ═══════════════════════════════════════════════════════════

_instance_viario: Path = Path("instance") / "viario"
_rodovias_runtime: dict = {}
_tapa_buraco_runtime: dict = {}


@viario_bp.record_once
def _on_register(state):
    global _instance_viario
    _instance_viario = Path(state.app.instance_path) / "viario"
    (_instance_viario / "saidas").mkdir(parents=True, exist_ok=True)
    (_instance_viario / "uploads").mkdir(parents=True, exist_ok=True)
    _carregar_config()


def _rodovias_json() -> Path:
    return _instance_viario / "rodovias_config.json"


def _api_key_path() -> str:
    return str(_instance_viario / "api_key.txt")


def _template_path() -> str:
    return str(_instance_viario / "base_gerar_relatorio.xlsm")


def _saidas_dir() -> Path:
    return _instance_viario / "saidas"


def _uploads_dir() -> Path:
    return _instance_viario / "uploads"


# Extensões aceitas no upload de fotos.
_IMG_EXTS = (".jpg", ".jpeg", ".png")


def _resolver_upload(token: str) -> Path | None:
    """Resolve um token de upload para sua pasta, barrando path traversal."""
    if not token:
        return None
    base = _uploads_dir().resolve()
    alvo = (base / token).resolve()
    if alvo.parent != base or not alvo.is_dir():
        return None
    return alvo


def _salvar_uploads(files, exts=_IMG_EXTS) -> tuple[str, Path]:
    """Salva arquivos enviados numa pasta temporária com token e retorna (token, pasta)."""
    token = uuid.uuid4().hex
    pasta = _uploads_dir() / token
    pasta.mkdir(parents=True, exist_ok=True)
    for f in files:
        nome = secure_filename(f.filename or "")
        if not nome:
            continue
        if exts and not nome.lower().endswith(exts):
            continue
        f.save(str(pasta / nome))
    return token, pasta


def _publicar_saida(pasta_dest: str) -> None:
    """Faz upload para o R2 de todos os arquivos gerados na pasta de saída."""
    base = _instance_viario
    for raiz, _dirs, arqs in os.walk(pasta_dest):
        for nome in arqs:
            caminho = Path(raiz) / nome
            key = "viario/" + str(caminho.relative_to(base)).replace("\\", "/")
            ctype = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                     if nome.lower().endswith(".xlsx")
                     else "application/octet-stream")
            try:
                r2.upload(key, caminho.read_bytes(), ctype)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════
#  CONFIG EM RUNTIME (editável via interface web)
# ═══════════════════════════════════════════════════════════

def _carregar_config():
    global _rodovias_runtime, _tapa_buraco_runtime
    j = _rodovias_json()
    if j.exists():
        try:
            data = json.loads(j.read_text(encoding="utf-8"))
            _rodovias_runtime    = data.get("rodovias",    {k: dict(v) for k, v in RODOVIAS.items()})
            _tapa_buraco_runtime = data.get("tapa_buraco", dict(TAPA_BURACO))
            return
        except Exception:
            pass
    _rodovias_runtime    = {k: dict(v) for k, v in RODOVIAS.items()}
    _tapa_buraco_runtime = dict(TAPA_BURACO)


def _salvar_config():
    j = _rodovias_json()
    j.write_text(
        json.dumps({"rodovias": _rodovias_runtime, "tapa_buraco": _tapa_buraco_runtime},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ═══════════════════════════════════════════════════════════
#  UTILITÁRIOS GERAIS
# ═══════════════════════════════════════════════════════════

def sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def listar_imagens(pasta: str):
    return sorted(
        f for f in os.listdir(pasta)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    )


def ler_api_key() -> str:
    # Variável de ambiente tem prioridade (Railway), fallback para arquivo local
    key = os.environ.get("ORS_API_KEY", "").strip()
    if key:
        return key
    with open(_api_key_path()) as f:
        return f.read().strip()


# ═══════════════════════════════════════════════════════════
#  OCR — extração de coordenadas GPS
# ═══════════════════════════════════════════════════════════

def parse_coord(val, negar: bool = True):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        pass
    s = str(val).strip()
    nums = re.findall(r'\d+(?:\.\d+)?', s)
    if len(nums) >= 3:
        dec = float(nums[0]) + float(nums[1]) / 60 + float(nums[2]) / 3600
        return -dec if negar else dec
    if len(nums) == 1:
        return -float(nums[0]) if negar else float(nums[0])
    return None


def _dms_para_decimal(graus, minutos, segundos, direcao):
    dec = int(graus) + int(minutos) / 60 + int(segundos) / 3600
    if direcao.upper() in ("S", "W", "O"):
        dec = -dec
    return round(dec, 6)


# Regex flexível para DMS — aceita variações de OCR nos separadores
_DMS_PAT = re.compile(
    r'(\d{1,3})[^\d\n]{1,5}(\d{1,2})[^\d\n]{1,5}(\d{1,2})[^\d\n]{0,4}([Ss])'
    r'[^\d\n]{1,15}'
    r'(\d{1,3})[^\d\n]{1,5}(\d{1,2})[^\d\n]{1,5}(\d{1,2})[^\d\n]{0,4}([WwOo])',
    re.DOTALL,
)


def extrair_coordenadas(img_path: str):
    try:
        img = PILImage.open(img_path)
        w, h = img.size

        if img.mode != "RGB":
            img = img.convert("RGB")

        crop_h = max(1, int(h * 0.15))
        crop = img.crop((0, h - crop_h, w, h))
        crop_big = crop.resize((w * 3, crop_h * 3), _LANCZOS)
        arr = np.array(crop_big, dtype=np.float32)
        gray = arr.mean(axis=2)

        candidatos = [
            (crop_big, "--psm 6"),
            (crop_big, "--psm 7"),
        ]
        for thresh in [200, 180, 160, 220, 140, 100]:
            binary = np.where(gray > thresh, 255, 0).astype(np.uint8)
            candidatos.append((
                PILImage.fromarray(binary),
                r"--psm 6 -c tessedit_char_whitelist=0123456789-. ",
            ))

        for pil_img, cfg in candidatos:
            text = pytesseract.image_to_string(pil_img, config=cfg)

            dms = _DMS_PAT.search(text)
            if dms:
                lat = _dms_para_decimal(dms.group(1), dms.group(2),
                                        dms.group(3), dms.group(4))
                lon = _dms_para_decimal(dms.group(5), dms.group(6),
                                        dms.group(7), dms.group(8))
                if -30 <= lat <= -10 and -65 <= lon <= -40:
                    return lat, lon, None

            text2 = re.sub(r"(\d)\s+(\d)", r"\1\2", text)
            text2 = re.sub(r"-\s+(\d)", r"-\1", text2)
            matches = re.findall(r"-?\d+\.\d+", text2)
            lat_d = next((float(m) for m in matches if -30 <= float(m) <= -10), None)
            lon_d = next((float(m) for m in matches if -65 <= float(m) <= -40), None)
            if lat_d and lon_d:
                return round(lat_d, 6), round(lon_d, 6), None

        return None, None, None

    except Exception as exc:
        return None, None, str(exc)


# ═══════════════════════════════════════════════════════════
#  OCR — extração de KM da foto (Roçada / identifica_km)
# ═══════════════════════════════════════════════════════════

def extrair_km_texto(img_path: str):
    try:
        img = PILImage.open(img_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        text = pytesseract.image_to_string(img)
        match = re.search(r"\bKM[:\s]*([0-9]{1,4})\b", text.upper())
        return (match.group(1) if match else None), None
    except Exception as exc:
        return None, str(exc)


# ═══════════════════════════════════════════════════════════
#  ORS — cálculo de distância
# ═══════════════════════════════════════════════════════════

def calcular_distancia_ors(client, origem: tuple, destino: tuple) -> float:
    time.sleep(1.6)
    rota = client.directions(
        coordinates=[[origem[1], origem[0]], [destino[1], destino[0]]],
        profile="driving-car",
        format="geojson",
    )
    return rota["features"][0]["properties"]["segments"][0]["distance"] / 1000


def calcular_km_rodovia(client, info: dict, ponto: tuple):
    modo = info["modo_calculo"]
    if modo == "simples":
        return calcular_distancia_ors(client, info["inicio"], ponto)
    elif modo == "limite_com_correcao":
        dist = calcular_distancia_ors(client, info["inicio"], ponto)
        if dist and dist > info["limite_km"]:
            dist2 = calcular_distancia_ors(client, info["inicio_corrigido"], ponto)
            if dist2:
                return dist2 + info["ajuste_km"]
        return dist
    elif modo == "fixo_com_ajuste":
        dist = calcular_distancia_ors(client, info["inicio"], ponto)
        return dist + info.get("ajuste_km", 0) if dist else None
    return None


def calcular_km_tapa_buraco(client, ponto: tuple):
    cfg = _tapa_buraco_runtime
    dist_cg = calcular_distancia_ors(client, cfg["ponto_cg"], ponto)
    if dist_cg is None:
        return None, None, None
    if dist_cg <= cfg["limite_cg"]:
        return int(dist_cg), cfg["descricao_cg"], f"KM {int(dist_cg)}"
    dist_sr = calcular_distancia_ors(client, cfg["ponto_sr"], ponto)
    if dist_sr is None:
        return None, None, None
    km = int(dist_sr + cfg["ajuste_sr"])
    return km, cfg["descricao_sr"], f"KM {km}"


# ═══════════════════════════════════════════════════════════
#  Relatório XLSM
# ═══════════════════════════════════════════════════════════

def gerar_relatorio_xlsm(df, pasta_fotos: str, pasta_destino: str,
                         timestamp: str, rodovia: str):
    if not os.path.exists(_template_path()):
        return None, "Template base_gerar_relatorio.xlsm não encontrado."

    base = os.path.basename(os.path.normpath(pasta_destino))
    partes = base.split("_")
    if (len(partes) >= 3
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", partes[0])
            and re.fullmatch(r"\d{6}", partes[-1])):
        nome_base = "_".join(partes[:-1])
    else:
        data = datetime.now().strftime("%Y-%m-%d")
        atividade_cn = canonicalizar_atividade(rodovia) or "Relatorio"
        nome_base = f"{data}_{atividade_cn}"
    nome = f"{nome_base}_relatorio-final.xlsm"
    caminho = os.path.join(pasta_destino, nome)
    pos_foto  = ["C10", "L10", "C34", "L34"]
    pos_texto = ["C32", "L32", "C56", "L56"]

    wb = load_workbook(_template_path(), keep_vba=True)
    modelo = wb["BASE"]

    for pagina, i in enumerate(range(0, len(df), 4), start=1):
        aba = wb.copy_worksheet(modelo)
        aba.title = f"Relatório_{pagina}"
        grupo = df.iloc[i:i+4].reset_index(drop=True)

        for j, row in grupo.iterrows():
            img_path = os.path.join(pasta_fotos, str(row.get("Imagem", "")))
            if os.path.isfile(img_path):
                try:
                    with PILImage.open(img_path) as img:
                        img = img.convert("RGB")
                        img = img.resize((725, 425), _LANCZOS)
                        tmp = os.path.join(pasta_destino, f"_tmp_{i}_{j}.jpg")
                        img.save(tmp)
                    xl_img = XLImage(tmp)
                    xl_img.width, xl_img.height = 725, 425
                    xl_img.anchor = pos_foto[j]
                    aba.add_image(xl_img)
                except Exception:
                    pass
            aba[pos_texto[j]] = str(row.get("Descrição", ""))

    wb.remove(modelo)
    wb.save(caminho)

    for f in glob.glob(os.path.join(pasta_destino, "_tmp_*.jpg")):
        try:
            os.remove(f)
        except Exception:
            pass

    return caminho, None


# ═══════════════════════════════════════════════════════════
#  Helpers de pipeline
# ═══════════════════════════════════════════════════════════

def _copiar_e_renomear(pasta_origem, pasta_destino):
    os.makedirs(pasta_destino, exist_ok=True)
    imagens = listar_imagens(pasta_origem)
    mapa = []
    for i, nome in enumerate(imagens):
        orig = os.path.join(pasta_origem, nome)
        novo_nome = f"foto_{i+1:03}.jpg"
        shutil.copy(orig, os.path.join(pasta_destino, novo_nome))
        mapa.append((orig, novo_nome))
    return mapa


# Mapeamento: variantes (minúsculas, sem espaço) → nome canônico da atividade.
_ATIVIDADES_CANONICAS = {
    "tapa_buraco":   "Tapa-buraco",
    "tapa-buraco":   "Tapa-buraco",
    "tapa":          "Tapa-buraco",
    "tapaburaco":    "Tapa-buraco",
    "rocada":        "Roçada",
    "roçada":        "Roçada",
    "rossada":       "Roçada",
    "caiacao":       "Caiação",
    "caiação":       "Caiação",
    "cascalho":      "Cascalho",
    "limpeza":       "Limpeza",
    "conformacao":   "Conformação",
    "conformação":   "Conformação",
    "aterro":        "Aterro",
    "raspagem":      "Raspagem",
    "raspagens":     "Raspagem",
}


def canonicalizar_atividade(nome: str) -> str:
    if not nome:
        return ""
    chave = nome.strip().lower().replace(" ", "_")
    return _ATIVIDADES_CANONICAS.get(chave, nome.strip().capitalize())


def _pasta_saida(atividade: str, rodovia: str = ""):
    now = datetime.now()
    data = now.strftime("%Y-%m-%d")
    hora = now.strftime("%H%M%S")
    ts   = now.strftime("%Y%m%d_%H%M%S")

    atividade_cn = canonicalizar_atividade(atividade) or "Saida"
    rodovia_cn   = rodovia.replace(" ", "") if rodovia else ""

    partes = [data, atividade_cn]
    if rodovia_cn:
        partes.append(rodovia_cn)
    partes.append(hora)
    nome = "_".join(partes)

    _saidas_dir().mkdir(parents=True, exist_ok=True)
    return str(_saidas_dir() / nome), ts


# ═══════════════════════════════════════════════════════════
#  ROTAS FLASK
# ═══════════════════════════════════════════════════════════

@viario_bp.route("/")
def index():
    return render_template(
        "viario/index.html",
        rodovias=list(_rodovias_runtime.keys()),
        servicos_gps=SERVICOS_GPS,
        servicos_km_foto=SERVICOS_KM_FOTO,
        rotas_km_foto=ROTAS_KM_FOTO,
    )


@viario_bp.route("/api/upload-fotos", methods=["POST"])
def api_upload_fotos():
    fotos = request.files.getlist("fotos")
    if not fotos:
        return jsonify({"error": "Nenhuma foto enviada."}), 400
    token, pasta = _salvar_uploads(fotos, _IMG_EXTS)
    n = len(listar_imagens(str(pasta)))
    if n == 0:
        shutil.rmtree(pasta, ignore_errors=True)
        return jsonify({"error": "Nenhuma imagem válida (.jpg/.jpeg/.png)."}), 400
    return jsonify({"token": token, "total": n})


@viario_bp.route("/api/upload-dados", methods=["POST"])
def api_upload_dados():
    arq = request.files.get("arquivo")
    if not arq or not (arq.filename or "").lower().endswith((".xlsx", ".xlsm")):
        return jsonify({"error": "Envie um arquivo .xlsx."}), 400
    token, pasta = _salvar_uploads([arq], (".xlsx", ".xlsm"))
    nome = secure_filename(arq.filename)
    if not (pasta / nome).is_file():
        shutil.rmtree(pasta, ignore_errors=True)
        return jsonify({"error": "Falha ao salvar o arquivo."}), 400
    return jsonify({"token": token, "nome": nome})


@viario_bp.route("/api/diagnostico")
def api_diagnostico():
    resultado = {}
    try:
        ver = pytesseract.get_tesseract_version()
        resultado["tesseract"] = {"ok": True, "versao": str(ver),
                                  "cmd": TESSERACT_CMD}
    except Exception as e:
        resultado["tesseract"] = {"ok": False, "erro": str(e),
                                  "cmd": TESSERACT_CMD}
    import PIL
    resultado["pillow"] = {"versao": PIL.__version__,
                           "lanczos": str(_LANCZOS)}
    resultado["numpy"] = {"versao": np.__version__}
    resultado["base_dir"] = str(_instance_viario)
    resultado["template_existe"] = os.path.isfile(_template_path())
    resultado["api_key_existe"] = os.path.isfile(_api_key_path())
    return jsonify(resultado)


# ── Pipeline 1: GPS (cascalho, aterro, conformação…) ────────────

@viario_bp.route("/api/pipeline-gps")
def api_pipeline_gps():
    token         = request.args.get("token", "").strip()
    rodovia       = request.args.get("rodovia", "")
    servico       = request.args.get("servico", "")
    com_relatorio = request.args.get("relatorio", "true") == "true"
    pasta_upload  = _resolver_upload(token)

    def generate():
        try:
            if pasta_upload is None:
                yield sse({"type": "error", "msg": "Fotos não encontradas — refaça o upload."}); return
            pasta_fotos = str(pasta_upload)
            if rodovia not in _rodovias_runtime:
                yield sse({"type": "error", "msg": f"Rodovia desconhecida: {rodovia}"}); return

            info = _rodovias_runtime[rodovia]
            pasta_dest, ts = _pasta_saida(servico or "Cascalho", rodovia)
            mapa = _copiar_e_renomear(pasta_fotos, pasta_dest)
            total = len(mapa)
            yield sse({"type": "info", "msg": f"{total} imagens encontradas."})

            yield sse({"type": "etapa", "etapa": 1, "msg": f"OCR — {total} imagens"})
            dados, sem_gps, erros_ocr = [], 0, 0
            for i, (orig, novo_nome) in enumerate(mapa):
                lat, lon, err = extrair_coordenadas(orig)
                if err:
                    erros_ocr += 1
                    if erros_ocr <= 3:
                        yield sse({"type": "aviso", "msg": f"OCR erro em {novo_nome}: {err}"})
                if lat is None:
                    sem_gps += 1
                dados.append({"Imagem": novo_nome, "Latitude": lat, "Longitude": lon,
                               "Distância (km)": None,
                               "Descrição": f"{servico} - {info['descricao']}"})
                pct = int((i + 1) / total * 100)
                msg = (f"{i+1}/{total} — {novo_nome} ✓ {lat:.6f}, {lon:.6f}"
                       if lat else f"{i+1}/{total} — {novo_nome} (sem GPS)")
                yield sse({"type": "progresso", "etapa": 1, "valor": pct, "msg": msg})

            df = pd.DataFrame(dados)
            arq_dados = os.path.join(pasta_dest, "dados.xlsx")
            df.to_excel(arq_dados, index=False)
            yield sse({"type": "etapa_ok", "etapa": 1,
                       "msg": f"OCR concluído — {total - sem_gps}/{total} com GPS"})

            com_coords = df[df["Latitude"].notna()]
            n_ors = len(com_coords)
            if n_ors == 0:
                yield sse({"type": "aviso", "msg": "Nenhuma foto com GPS — KM ignorado."})
            else:
                est = int(n_ors * 1.6 / 60)
                yield sse({"type": "etapa", "etapa": 2,
                           "msg": f"Calculando KM — {n_ors} pontos (~{est} min)"})
                try:
                    client = openrouteservice.Client(key=ler_api_key())
                    for i, (idx, row) in enumerate(com_coords.iterrows()):
                        try:
                            lat = parse_coord(row["Latitude"], negar=True)
                            lon = parse_coord(row["Longitude"], negar=True)
                            if lat is None or lon is None:
                                continue
                            dist = calcular_km_rodovia(client, info, (lat, lon))
                            if dist:
                                d = round(dist, 1)
                                df.at[idx, "Distância (km)"] = d
                                df.at[idx, "Descrição"] = (
                                    f"{servico} - {info['descricao']} KM {d:g}")
                        except Exception as e:
                            yield sse({"type": "aviso",
                                       "msg": f"KM erro em {row['Imagem']}: {e}"})
                        yield sse({"type": "progresso", "etapa": 2,
                                   "valor": int((i + 1) / n_ors * 100),
                                   "msg": f"{i+1}/{n_ors} pontos calculados"})
                    df.to_excel(arq_dados, index=False)
                    yield sse({"type": "etapa_ok", "etapa": 2, "msg": "KM calculado"})
                except FileNotFoundError:
                    yield sse({"type": "aviso",
                               "msg": "api_key.txt não encontrado — KM ignorado."})

            arq_rel = None
            if com_relatorio:
                yield sse({"type": "etapa", "etapa": 3, "msg": "Gerando relatório .xlsm"})
                arq_rel, err = gerar_relatorio_xlsm(df, pasta_dest, pasta_dest, ts, rodovia)
                if err:
                    yield sse({"type": "aviso", "msg": err})
                else:
                    yield sse({"type": "etapa_ok", "etapa": 3, "msg": "Relatório gerado"})

            _publicar_saida(pasta_dest)
            res = {"type": "concluido", "pasta": pasta_dest,
                   "dados": os.path.relpath(arq_dados, str(_instance_viario)).replace("\\", "/")}
            if arq_rel:
                res["relatorio"] = os.path.relpath(arq_rel, str(_instance_viario)).replace("\\", "/")
            yield sse(res)

        except Exception as e:
            yield sse({"type": "error", "msg": str(e)})
        finally:
            if pasta_upload is not None:
                shutil.rmtree(pasta_upload, ignore_errors=True)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Pipeline 2: Identificar KM da foto (Roçada) ─────────────────

@viario_bp.route("/api/pipeline-km-foto")
def api_pipeline_km_foto():
    token         = request.args.get("token", "").strip()
    tipo_servico  = request.args.get("tipo_servico", "Roçada")
    rota          = request.args.get("rota", "")
    com_relatorio = request.args.get("relatorio", "true") == "true"
    pasta_upload  = _resolver_upload(token)

    def generate():
        try:
            if pasta_upload is None:
                yield sse({"type": "error", "msg": "Fotos não encontradas — refaça o upload."}); return
            pasta_fotos = str(pasta_upload)

            prefixo_desc = f"{tipo_servico} - {rota}" if rota else tipo_servico
            nome_saida   = tipo_servico.lower().replace(" ", "_")
            rodovia_saida = rota if rota and rota.strip().upper().startswith("MS") else ""
            pasta_dest, ts = _pasta_saida(tipo_servico, rodovia_saida)
            mapa = _copiar_e_renomear(pasta_fotos, pasta_dest)
            total = len(mapa)
            yield sse({"type": "info", "msg": f"{total} imagens encontradas."})

            yield sse({"type": "etapa", "etapa": 1,
                       "msg": f"Lendo KM das fotos — {total} imagens"})
            dados, sem_km, erros_ocr = [], 0, 0
            for i, (orig, novo_nome) in enumerate(mapa):
                km, err = extrair_km_texto(orig)
                if err:
                    erros_ocr += 1
                    if erros_ocr <= 3:
                        yield sse({"type": "aviso",
                                   "msg": f"OCR erro em {novo_nome}: {err}"})
                if km is None:
                    sem_km += 1
                desc = f"{prefixo_desc} - KM {km}" if km else prefixo_desc
                dados.append({
                    "Nº":            i + 1,
                    "Imagem":        novo_nome,
                    "Latitude":      None,
                    "Longitude":     None,
                    "Distância (km)": int(km) if km else None,
                    "Descrição":     desc,
                })
                pct = int((i + 1) / total * 100)
                msg = (f"{i+1}/{total} — {novo_nome} ✓ KM {km}"
                       if km else f"{i+1}/{total} — {novo_nome} (KM não encontrado)")
                yield sse({"type": "progresso", "etapa": 1, "valor": pct, "msg": msg})

            df = pd.DataFrame(dados)
            arq_dados = os.path.join(pasta_dest, "dados.xlsx")
            df.to_excel(arq_dados, index=False)
            yield sse({"type": "etapa_ok", "etapa": 1,
                       "msg": f"OCR concluído — {total - sem_km}/{total} com KM"})

            arq_rel = None
            if com_relatorio:
                yield sse({"type": "etapa", "etapa": 2, "msg": "Gerando relatório .xlsm"})
                arq_rel, err = gerar_relatorio_xlsm(
                    df, pasta_dest, pasta_dest, ts, nome_saida)
                if err:
                    yield sse({"type": "aviso", "msg": err})
                else:
                    yield sse({"type": "etapa_ok", "etapa": 2, "msg": "Relatório gerado"})

            _publicar_saida(pasta_dest)
            res = {"type": "concluido", "pasta": pasta_dest,
                   "dados": os.path.relpath(arq_dados, str(_instance_viario)).replace("\\", "/")}
            if arq_rel:
                res["relatorio"] = os.path.relpath(arq_rel, str(_instance_viario)).replace("\\", "/")
            yield sse(res)

        except Exception as e:
            yield sse({"type": "error", "msg": str(e)})
        finally:
            if pasta_upload is not None:
                shutil.rmtree(pasta_upload, ignore_errors=True)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Pipeline 3: Tapa-Buraco ──────────────────────────────────────

@viario_bp.route("/api/pipeline-tapa-buraco")
def api_pipeline_tapa_buraco():
    token         = request.args.get("token", "").strip()
    com_relatorio = request.args.get("relatorio", "true") == "true"
    pasta_upload  = _resolver_upload(token)

    def generate():
        try:
            if pasta_upload is None:
                yield sse({"type": "error", "msg": "Fotos não encontradas — refaça o upload."}); return
            pasta_fotos = str(pasta_upload)

            pasta_dest, ts = _pasta_saida("Tapa-buraco")
            mapa = _copiar_e_renomear(pasta_fotos, pasta_dest)
            total = len(mapa)
            yield sse({"type": "info", "msg": f"{total} imagens encontradas."})

            yield sse({"type": "etapa", "etapa": 1, "msg": f"OCR — {total} imagens"})
            dados, sem_gps, erros_ocr = [], 0, 0
            for i, (orig, novo_nome) in enumerate(mapa):
                lat, lon, err = extrair_coordenadas(orig)
                if err:
                    erros_ocr += 1
                    if erros_ocr <= 3:
                        yield sse({"type": "aviso",
                                   "msg": f"OCR erro em {novo_nome}: {err}"})
                if lat is None:
                    sem_gps += 1
                dados.append({"Imagem": novo_nome, "Latitude": lat, "Longitude": lon,
                               "Distância (km)": None, "Descrição": "Tapa-Buraco"})
                pct = int((i + 1) / total * 100)
                msg = (f"{i+1}/{total} — {novo_nome} ✓ {lat:.6f}, {lon:.6f}"
                       if lat else f"{i+1}/{total} — {novo_nome} (sem GPS)")
                yield sse({"type": "progresso", "etapa": 1, "valor": pct, "msg": msg})

            df = pd.DataFrame(dados)
            arq_dados = os.path.join(pasta_dest, "dados.xlsx")
            df.to_excel(arq_dados, index=False)
            yield sse({"type": "etapa_ok", "etapa": 1,
                       "msg": f"OCR concluído — {total - sem_gps}/{total} com GPS"})

            com_coords = df[df["Latitude"].notna()]
            n_ors = len(com_coords)
            if n_ors == 0:
                yield sse({"type": "aviso", "msg": "Nenhuma foto com GPS — KM ignorado."})
            else:
                est = int(n_ors * 1.6 * 2 / 60)
                yield sse({"type": "etapa", "etapa": 2,
                           "msg": f"Calculando KM (CG/SR) — {n_ors} pontos (~{est} min)"})
                try:
                    client = openrouteservice.Client(key=ler_api_key())
                    for i, (idx, row) in enumerate(com_coords.iterrows()):
                        try:
                            lat = parse_coord(row["Latitude"], negar=True)
                            lon = parse_coord(row["Longitude"], negar=True)
                            if lat is None or lon is None:
                                continue
                            km, desc, km_str = calcular_km_tapa_buraco(client, (lat, lon))
                            if km:
                                df.at[idx, "Distância (km)"] = km
                                df.at[idx, "Descrição"] = f"{desc} - {km_str}"
                        except Exception as e:
                            yield sse({"type": "aviso",
                                       "msg": f"KM erro em {row['Imagem']}: {e}"})
                        yield sse({"type": "progresso", "etapa": 2,
                                   "valor": int((i + 1) / n_ors * 100),
                                   "msg": f"{i+1}/{n_ors} pontos calculados"})
                    df.to_excel(arq_dados, index=False)
                    yield sse({"type": "etapa_ok", "etapa": 2, "msg": "KM calculado"})
                except FileNotFoundError:
                    yield sse({"type": "aviso",
                               "msg": "api_key.txt não encontrado — KM ignorado."})

            arq_rel = None
            if com_relatorio:
                yield sse({"type": "etapa", "etapa": 3, "msg": "Gerando relatório .xlsm"})
                arq_rel, err = gerar_relatorio_xlsm(
                    df, pasta_dest, pasta_dest, ts, "tapa_buraco")
                if err:
                    yield sse({"type": "aviso", "msg": err})
                else:
                    yield sse({"type": "etapa_ok", "etapa": 3, "msg": "Relatório gerado"})

            _publicar_saida(pasta_dest)
            res = {"type": "concluido", "pasta": pasta_dest,
                   "dados": os.path.relpath(arq_dados, str(_instance_viario)).replace("\\", "/")}
            if arq_rel:
                res["relatorio"] = os.path.relpath(arq_rel, str(_instance_viario)).replace("\\", "/")
            yield sse(res)

        except Exception as e:
            yield sse({"type": "error", "msg": str(e)})
        finally:
            if pasta_upload is not None:
                shutil.rmtree(pasta_upload, ignore_errors=True)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Atualizar KM (dados.xlsx já existente) ───────────────────────

@viario_bp.route("/api/atualizar-km")
def api_atualizar_km():
    token   = request.args.get("token", "").strip()
    rodovia = request.args.get("rodovia", "")
    servico = request.args.get("servico", "")
    pasta_upload = _resolver_upload(token)

    def generate():
        try:
            if pasta_upload is None:
                yield sse({"type": "error", "msg": "Arquivo não encontrado — refaça o upload."}); return
            xlsx = sorted(pasta_upload.glob("*.xls*"))
            if not xlsx:
                yield sse({"type": "error", "msg": "Nenhuma planilha no upload."}); return
            arquivo = str(xlsx[0])
            if rodovia not in _rodovias_runtime:
                yield sse({"type": "error", "msg": f"Rodovia desconhecida: {rodovia}"}); return

            info = _rodovias_runtime[rodovia]
            df = pd.read_excel(arquivo)
            com_coords = df[df["Latitude"].notna()]
            n = len(com_coords)
            if n == 0:
                yield sse({"type": "error", "msg": "Nenhuma linha com coordenadas."}); return

            yield sse({"type": "etapa", "etapa": 1,
                       "msg": f"Calculando KM — {n} pontos (~{int(n * 1.6 / 60)} min)"})
            client = openrouteservice.Client(key=ler_api_key())
            for i, (idx, row) in enumerate(com_coords.iterrows()):
                try:
                    lat = parse_coord(row["Latitude"], negar=True)
                    lon = parse_coord(row["Longitude"], negar=True)
                    if lat is None or lon is None:
                        yield sse({"type": "aviso",
                                   "msg": f"Linha {idx}: coordenada inválida "
                                          f"(lat={row['Latitude']!r}, lon={row['Longitude']!r})"})
                        continue
                    df.at[idx, "Latitude"]  = lat
                    df.at[idx, "Longitude"] = lon
                    dist = calcular_km_rodovia(client, info, (lat, lon))
                    if dist:
                        d = round(dist, 1)
                        df.at[idx, "Distância (km)"] = d
                        df.at[idx, "Descrição"] = (
                            f"{servico} - {info['descricao']} KM {d:g}")
                except Exception as e:
                    yield sse({"type": "aviso", "msg": f"Linha {idx}: {e}"})
                yield sse({"type": "progresso", "etapa": 1,
                           "valor": int((i + 1) / n * 100),
                           "msg": f"{i+1}/{n} calculados"})

            pasta_dest, _ts = _pasta_saida(servico or "AtualizarKM", rodovia)
            os.makedirs(pasta_dest, exist_ok=True)
            arq_saida = os.path.join(pasta_dest, "dados.xlsx")
            df.to_excel(arq_saida, index=False)
            _publicar_saida(pasta_dest)
            yield sse({"type": "etapa_ok", "etapa": 1, "msg": "KM atualizado"})
            yield sse({"type": "concluido", "pasta": pasta_dest,
                       "dados": os.path.relpath(arq_saida, str(_instance_viario)).replace("\\", "/")})

        except Exception as e:
            yield sse({"type": "error", "msg": str(e)})
        finally:
            if pasta_upload is not None:
                shutil.rmtree(pasta_upload, ignore_errors=True)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Gerar só o relatório ─────────────────────────────────────────

@viario_bp.route("/api/relatorio")
def api_relatorio():
    token_dados = request.args.get("token_dados", "").strip()
    token_fotos = request.args.get("token_fotos", "").strip()
    nome        = request.args.get("nome", "") or request.args.get("rodovia", "") or "relatorio"
    up_dados    = _resolver_upload(token_dados)
    up_fotos    = _resolver_upload(token_fotos)

    def generate():
        try:
            if up_dados is None:
                yield sse({"type": "error", "msg": "Arquivo de dados não encontrado — refaça o upload."}); return
            if up_fotos is None:
                yield sse({"type": "error", "msg": "Fotos não encontradas — refaça o upload."}); return
            xlsx = sorted(up_dados.glob("*.xls*"))
            if not xlsx:
                yield sse({"type": "error", "msg": "Nenhuma planilha no upload de dados."}); return

            df = pd.read_excel(str(xlsx[0]))
            pasta_dest, ts = _pasta_saida(nome)
            os.makedirs(pasta_dest, exist_ok=True)

            yield sse({"type": "etapa", "etapa": 1, "msg": "Gerando relatório .xlsm"})
            arq_rel, err = gerar_relatorio_xlsm(
                df, str(up_fotos), pasta_dest, ts, nome)
            if err:
                yield sse({"type": "error", "msg": err}); return

            _publicar_saida(pasta_dest)
            yield sse({"type": "etapa_ok", "etapa": 1, "msg": "Relatório gerado"})
            yield sse({"type": "concluido", "pasta": pasta_dest,
                       "relatorio": os.path.relpath(arq_rel, str(_instance_viario)).replace("\\", "/")})

        except Exception as e:
            yield sse({"type": "error", "msg": str(e)})
        finally:
            for p in (up_dados, up_fotos):
                if p is not None:
                    shutil.rmtree(p, ignore_errors=True)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Download ──────────────────────────────────────────────────────

@viario_bp.route("/api/download")
def api_download():
    filepath = request.args.get("file", "")
    if not filepath:
        return jsonify({"error": "Parâmetro 'file' obrigatório"}), 400
    # R2 primeiro — persiste além do ciclo de vida do container
    data = r2.download(f"viario/{filepath}")
    if data:
        fname = os.path.basename(filepath)
        return send_file(io.BytesIO(data), as_attachment=True, download_name=fname)
    # Fallback: disco local
    full = (_instance_viario / filepath.replace("/", os.sep)).resolve()
    if not str(full).startswith(str(_instance_viario.resolve())):
        return jsonify({"error": "Caminho inválido"}), 400
    if full.is_file():
        return send_file(str(full), as_attachment=True)
    return jsonify({"error": "Arquivo não encontrado"}), 404


# ── Config: Rodovias e Tapa-Buraco ───────────────────────────────

@viario_bp.route("/api/config/rodovias", methods=["GET"])
def api_config_rodovias_get():
    return jsonify({
        "rodovias":    _rodovias_runtime,
        "tapa_buraco": _tapa_buraco_runtime,
    })


@viario_bp.route("/api/config/rodovias", methods=["POST"])
def api_config_rodovias_save():
    data   = request.get_json(force=True)
    sigla  = (data.get("sigla") or "").strip()
    if not sigla:
        return jsonify({"error": "Sigla obrigatória"}), 400

    modo = data.get("modo_calculo", "simples")
    rod  = {
        "descricao":    data.get("descricao", sigla),
        "modo_calculo": modo,
        "inicio":       [float(data["lat_inicio"]), float(data["lon_inicio"])],
    }
    if modo == "limite_com_correcao":
        rod["inicio_corrigido"] = [float(data["lat_corrigido"]), float(data["lon_corrigido"])]
        rod["limite_km"]        = float(data["limite_km"])
        rod["ajuste_km"]        = float(data["ajuste_km"])
    elif modo == "fixo_com_ajuste":
        rod["ajuste_km"] = float(data["ajuste_km"])

    _rodovias_runtime[sigla] = rod
    _salvar_config()
    return jsonify({"ok": True, "sigla": sigla})


@viario_bp.route("/api/config/rodovias/<path:sigla>", methods=["DELETE"])
def api_config_rodovias_delete(sigla):
    sigla = sigla.replace("-", " ").upper()
    if sigla not in _rodovias_runtime:
        match = next((k for k in _rodovias_runtime if k.upper() == sigla), None)
        if match:
            sigla = match
        else:
            return jsonify({"error": "Rodovia não encontrada"}), 404
    del _rodovias_runtime[sigla]
    _salvar_config()
    return jsonify({"ok": True})


@viario_bp.route("/api/config/tapa-buraco", methods=["POST"])
def api_config_tapa_buraco_save():
    data = request.get_json(force=True)
    _tapa_buraco_runtime.update({
        "ponto_cg":     [float(data["lat_cg"]),    float(data["lon_cg"])],
        "ponto_sr":     [float(data["lat_sr"]),    float(data["lon_sr"])],
        "limite_cg":    float(data["limite_cg"]),
        "ajuste_sr":    float(data["ajuste_sr"]),
        "descricao_cg": data.get("descricao_cg", _tapa_buraco_runtime.get("descricao_cg", "")),
        "descricao_sr": data.get("descricao_sr", _tapa_buraco_runtime.get("descricao_sr", "")),
    })
    _salvar_config()
    return jsonify({"ok": True})
