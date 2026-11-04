"""Instalador do Retoque Fácil (só usa a biblioteca padrão do Python).

Rodado pelos atalhos "Instalar no Windows.bat" / "Instalar no Mac.command":
  1. copia o programa para uma pasta fixa do usuário;
  2. baixa as dependências com o uv e testa os modelos;
  3. cria as pastas de fotos em Documentos;
  4. registra o servidor no Claude Desktop (com cópia de segurança da configuração);
  5. prepara o arquivo da skill para enviar no Claude.

Uso: python instalador.py [--desinstalar] [--sem-claude]
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

NOME = "retoque-facil"
RAIZ = Path(__file__).resolve().parent.parent
ITENS_DO_APP = ["server.py", "pyproject.toml", "uv.lock", ".python-version", "src", "LICENSE", "THIRD_PARTY_NOTICES.md"]


def falar(texto: str = "") -> None:
    print(texto, flush=True)


def pasta_app() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "RetoqueFacil"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "RetoqueFacil"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "retoque-facil"


def configs_do_claude(criar: bool) -> list[Path]:
    """Arquivos claude_desktop_config.json que existem (ou o principal, se nenhum existir)."""
    candidatos: list[Path] = []
    principal: Path
    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        principal = appdata / "Claude" / "claude_desktop_config.json"
        candidatos.append(principal)
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        pacotes = local / "Packages"
        if pacotes.is_dir():  # versão da Microsoft Store guarda a configuração aqui
            for pac in pacotes.glob("Claude_*"):
                candidatos.append(pac / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json")
    elif sys.platform == "darwin":
        principal = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        candidatos.append(principal)
    else:
        principal = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "Claude" / "claude_desktop_config.json"
        candidatos.append(principal)

    existentes = [c for c in candidatos if c.is_file()]
    if existentes or not criar:
        return existentes
    alvos = [principal]
    for c in candidatos[1:]:
        if c.parent.parent.is_dir():  # pasta do pacote da Store existe
            alvos.append(c)
    return alvos


def _ler_json(caminho: Path) -> dict:
    if not caminho.exists() or not caminho.read_text(encoding="utf-8-sig").strip():
        return {}
    dados = json.loads(caminho.read_text(encoding="utf-8-sig"))
    if not isinstance(dados, dict):
        raise ValueError("formato inesperado")
    return dados


def registrar(caminho: Path, comando: str, args: list[str], env: dict | None = None) -> Path | None:
    """Acrescenta (ou atualiza) o servidor no arquivo do Claude, sem mexer no resto."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    try:
        dados = _ler_json(caminho)
    except (ValueError, json.JSONDecodeError) as e:
        raise RuntimeError(
            f"o arquivo de configuração do Claude está com defeito ({caminho}): {e}. "
            "Nada foi alterado. Peça ajuda para corrigi-lo e rode o instalador de novo."
        ) from e
    copia = None
    if caminho.exists():
        carimbo = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        copia = caminho.with_name(f"{caminho.name}.bak-{carimbo}")
        shutil.copy2(caminho, copia)
    servidores = dados.setdefault("mcpServers", {})
    if not isinstance(servidores, dict):
        raise RuntimeError("a configuração do Claude tem 'mcpServers' num formato inesperado; nada foi alterado")
    entrada = {"command": comando, "args": args}
    if env:
        entrada["env"] = env
    servidores[NOME] = entrada
    temporario = caminho.with_suffix(".tmp-retoque")
    temporario.write_text(json.dumps(dados, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporario.replace(caminho)
    return copia


def desregistrar(caminho: Path) -> bool:
    try:
        dados = _ler_json(caminho)
    except (ValueError, json.JSONDecodeError):
        return False
    if NOME not in dados.get("mcpServers", {}):
        return False
    carimbo = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(caminho, caminho.with_name(f"{caminho.name}.bak-{carimbo}"))
    del dados["mcpServers"][NOME]
    caminho.write_text(json.dumps(dados, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def achar_uv() -> str:
    for c in (os.environ.get("UV"), shutil.which("uv"),
              str(Path.home() / ".local" / "bin" / ("uv.exe" if sys.platform == "win32" else "uv")),
              str(Path.home() / ".cargo" / "bin" / ("uv.exe" if sys.platform == "win32" else "uv"))):
        if c and Path(c).is_file():
            return c
    raise RuntimeError("não encontrei o 'uv'. Rode o instalador pelo atalho (ele instala o uv sozinho).")


def python_do_app(app: Path) -> Path:
    if sys.platform == "win32":
        return app / ".venv" / "Scripts" / "python.exe"
    return app / ".venv" / "bin" / "python"


def copiar_programa(destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    for item in ITENS_DO_APP:
        origem = RAIZ / item
        if not origem.exists():
            continue
        alvo = destino / item
        if origem.is_dir():
            if alvo.exists():
                shutil.rmtree(alvo)
            shutil.copytree(origem, alvo, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(origem, alvo)


def preparar_skill(destino: Path) -> Path:
    pasta = RAIZ / "skill" / "retoque-de-pele"
    zipado = destino / "retoque-de-pele.zip"
    with zipfile.ZipFile(zipado, "w", zipfile.ZIP_DEFLATED) as z:
        for arq in pasta.rglob("*"):
            if arq.is_file():
                z.write(arq, Path("retoque-de-pele") / arq.relative_to(pasta))
    return zipado


def abrir(caminho: Path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(str(caminho))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(caminho)])
    except Exception:
        pass


def instalar(registrar_no_claude: bool = True) -> int:
    falar("=" * 60)
    falar("  Retoque Fácil - instalação")
    falar("=" * 60)
    app = pasta_app() / "app"
    falar(f"\n[1/5] Copiando o programa para {app} ...")
    copiar_programa(app)

    falar("\n[2/5] Baixando os componentes (só na primeira vez; pode levar alguns minutos) ...")
    uv = achar_uv()
    r = subprocess.run([uv, "sync", "--frozen", "--no-dev", "--directory", str(app)])
    if r.returncode != 0:
        if sys.platform == "darwin" and os.uname().machine == "x86_64":
            falar("\nEste Mac tem processador Intel. O Retoque Fácil precisa de Mac com chip Apple (M1 ou mais novo).")
        else:
            falar("\nNão consegui baixar os componentes. Confira a internet e rode o instalador de novo.")
        return 1

    py = python_do_app(app)
    falar("\n[3/5] Testando os modelos de inteligência artificial ...")
    teste = (
        "import sys; sys.path.insert(0, 'src');"
        "import numpy as np;"
        "from retoque_facil import analise, config;"
        "analise.analisar(np.full((256, 256, 3), 0.5, np.float32));"
        "analise.modelos.fechar();"
        "e, s = config.pastas(); print(e); print(s)"
    )
    r = subprocess.run([str(py), "-c", teste], cwd=app, capture_output=True, text=True)
    if r.returncode != 0:
        falar(r.stderr[-1500:])
        falar("\nO teste falhou. Tire um print desta janela e mande para quem te passou o programa.")
        return 1
    linhas = [x for x in r.stdout.strip().splitlines() if x.strip()]
    entrada, saida = linhas[-2], linhas[-1]
    falar("      tudo certo.")

    falar("\n[4/5] Ligando o Retoque Fácil no Claude Desktop ...")
    if registrar_no_claude:
        alvos = configs_do_claude(criar=True)
        for alvo in alvos:
            copia = registrar(alvo, str(py), [str(app / "server.py")])
            falar(f"      configurado em {alvo}")
            if copia:
                falar(f"      (cópia de segurança: {copia.name})")
    else:
        falar("      (pulado)")

    falar("\n[5/5] Preparando a skill ...")
    skill = preparar_skill(pasta_app())
    falar(f"      arquivo da skill: {skill}")

    falar("\n" + "=" * 60)
    falar("  PRONTO! Agora faça só isto:")
    falar("=" * 60)
    falar("  1. Feche o Claude de vez e abra de novo.")
    if sys.platform == "win32":
        falar("     (botão direito no ícone do Claude perto do relógio > Sair)")
    falar("  2. No Claude, vá em Personalizar (Customize) > Skills > + >")
    falar("     Criar skill (Create skill) > Enviar skill (Upload a skill)")
    falar(f"     e escolha o arquivo: {skill}")
    falar("     (vou abrir a pasta dele para você)")
    falar(f"  3. Coloque as fotos em: {entrada}")
    falar("  4. No Claude, escreva: Retoque minhas fotos")
    falar(f"\n  As fotos prontas vão aparecer em: {saida}\n")
    abrir(skill.parent)
    return 0


def desinstalar() -> int:
    falar("Removendo o Retoque Fácil do Claude Desktop ...")
    for alvo in configs_do_claude(criar=False):
        if desregistrar(alvo):
            falar(f"  removido de {alvo}")
    app = pasta_app()
    if app.exists():
        shutil.rmtree(app, ignore_errors=True)
        falar(f"  programa apagado de {app}")
    falar("\nPronto. Suas fotos em Documentos > Retoque Facil NÃO foram apagadas.")
    falar("Feche o Claude de vez e abra de novo. Se quiser, apague a skill em Personalizar (Customize) > Skills.")
    return 0


if __name__ == "__main__":
    if "--desinstalar" in sys.argv:
        sys.exit(desinstalar())
    sys.exit(instalar(registrar_no_claude="--sem-claude" not in sys.argv))
