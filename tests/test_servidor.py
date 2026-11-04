"""Teste ponta a ponta: inicia o servidor MCP de verdade (stdio) e usa as ferramentas."""

import json
import os
import shutil
import sys
from pathlib import Path

import anyio
import pytest

RAIZ = Path(__file__).parent.parent


def test_fluxo_completo(tmp_path, foto_estudio):
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    from retoque_facil import tiff_camadas

    entrada = tmp_path / "1 - Fotos para retocar"
    entrada.mkdir(parents=True)
    shutil.copy(foto_estudio, entrada / "Retrato Ação.png")
    env = dict(os.environ, RETOQUE_PASTA=str(tmp_path))
    params = StdioServerParameters(command=sys.executable, args=[str(RAIZ / "server.py")], env=env)

    async def rodar():
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            nomes = {t.name for t in (await s.list_tools()).tools}
            assert {"listar_fotos", "analisar_foto", "aplicar_retoque", "salvar_tiff"} <= nomes

            lista = json.loads((await s.call_tool("listar_fotos", {})).content[0].text)
            assert lista["total"] == 1

            res = await s.call_tool("analisar_foto", {"foto": "retrato acao"})
            info = json.loads(res.content[0].text)
            assert info["rostos_encontrados"] == 1
            assert res.content[1].type == "image"

            res = await s.call_tool("aplicar_retoque", {"sessao": info["sessao"], "limpar_fundo": "leve"})
            assert json.loads(res.content[0].text)["limpar_fundo"] == "leve"

            res = await s.call_tool("ver_detalhe", {"sessao": info["sessao"], "celula": "C3"})
            assert res.content[1].type == "image"

            res = await s.call_tool("salvar_tiff", {"sessao": info["sessao"]})
            return json.loads(res.content[0].text)

    salvo = anyio.run(rodar)
    tif = Path(salvo["tiff"])
    assert tif.exists() and tif.parent.name == "2 - Fotos prontas"
    assert [n for n, _ in tiff_camadas.ler_camadas(tif)] == ["Original", "Retocada"]


@pytest.mark.parametrize("versao", ["2024-11-05", "2025-06-18"])
def test_protocolo_antigo(versao):
    """O Claude Desktop pode falar versões mais antigas do protocolo MCP."""
    import subprocess

    proc = subprocess.Popen([sys.executable, str(RAIZ / "server.py")], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8")

    def enviar(msg):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    def receber(id_):
        while True:
            linha = proc.stdout.readline()
            assert linha, "o servidor fechou sem responder"
            d = json.loads(linha)
            if d.get("id") == id_:
                return d

    try:
        enviar({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": versao, "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}})
        assert receber(1)["result"]["protocolVersion"] == versao
        enviar({"jsonrpc": "2.0", "method": "notifications/initialized"})
        enviar({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert len(receber(2)["result"]["tools"]) == 9
    finally:
        proc.stdin.close()
        proc.wait(timeout=30)
