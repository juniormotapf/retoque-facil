import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("instalador", Path(__file__).parent.parent / "instalar" / "instalador.py")
instalador = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(instalador)


def test_registrar_preserva_o_resto(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"mcpServers": {"outro": {"command": "node"}}, "tema": "escuro"}), encoding="utf-8")
    copia = instalador.registrar(cfg, "C:/py.exe", ["C:/app/server.py"])
    dados = json.loads(cfg.read_text(encoding="utf-8"))
    assert dados["tema"] == "escuro"
    assert dados["mcpServers"]["outro"] == {"command": "node"}
    assert dados["mcpServers"]["retoque-facil"] == {"command": "C:/py.exe", "args": ["C:/app/server.py"]}
    assert copia is not None and copia.exists()
    assert instalador.desregistrar(cfg)
    assert "retoque-facil" not in json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]


def test_cria_config_quando_nao_existe(tmp_path):
    cfg = tmp_path / "Claude" / "claude_desktop_config.json"
    assert instalador.registrar(cfg, "py", ["s.py"]) is None
    assert json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]["retoque-facil"]["command"] == "py"


def test_nao_estraga_config_com_defeito(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text("{ isso não é json", encoding="utf-8")
    with pytest.raises(RuntimeError):
        instalador.registrar(cfg, "py", ["s.py"])
    assert cfg.read_text(encoding="utf-8") == "{ isso não é json"


def test_skill_zip_tem_a_pasta_certa(tmp_path):
    import zipfile

    z = instalador.preparar_skill(tmp_path)
    with zipfile.ZipFile(z) as arq:
        assert "retoque-de-pele/SKILL.md" in arq.namelist()
        texto = arq.read("retoque-de-pele/SKILL.md").decode("utf-8")
    assert texto.startswith("---\nname: retoque-de-pele\n")
