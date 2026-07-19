"""Prepara os dados compactos usados pelo painel de vagas por região."""

import argparse
import csv
import json
import re
import unicodedata
from pathlib import Path


ESTADOS = {
    "AC": ("Acre", "Norte", "12"),
    "AL": ("Alagoas", "Nordeste", "27"),
    "AP": ("Amapá", "Norte", "16"),
    "AM": ("Amazonas", "Norte", "13"),
    "BA": ("Bahia", "Nordeste", "29"),
    "CE": ("Ceará", "Nordeste", "23"),
    "DF": ("Distrito Federal", "Centro-Oeste", "53"),
    "ES": ("Espírito Santo", "Sudeste", "32"),
    "GO": ("Goiás", "Centro-Oeste", "52"),
    "MA": ("Maranhão", "Nordeste", "21"),
    "MT": ("Mato Grosso", "Centro-Oeste", "51"),
    "MS": ("Mato Grosso do Sul", "Centro-Oeste", "50"),
    "MG": ("Minas Gerais", "Sudeste", "31"),
    "PA": ("Pará", "Norte", "15"),
    "PB": ("Paraíba", "Nordeste", "25"),
    "PR": ("Paraná", "Sul", "41"),
    "PE": ("Pernambuco", "Nordeste", "26"),
    "PI": ("Piauí", "Nordeste", "22"),
    "RJ": ("Rio de Janeiro", "Sudeste", "33"),
    "RN": ("Rio Grande do Norte", "Nordeste", "24"),
    "RS": ("Rio Grande do Sul", "Sul", "43"),
    "RO": ("Rondônia", "Norte", "11"),
    "RR": ("Roraima", "Norte", "14"),
    "SC": ("Santa Catarina", "Sul", "42"),
    "SP": ("São Paulo", "Sudeste", "35"),
    "SE": ("Sergipe", "Nordeste", "28"),
    "TO": ("Tocantins", "Norte", "17"),
}

# Localidades que aparecem no CSV somente como "cidade e região".
ALIASES_CIDADES = {
    "belo horizonte": "MG",
    "belem": "PA",
    "brasilia": "DF",
    "campinas": "SP",
    "florianopolis": "SC",
    "fortaleza": "CE",
    "goiania": "GO",
    "joao pessoa": "PB",
    "londrina": "PR",
    "natal": "RN",
    "porto alegre": "RS",
    "recife": "PE",
    "ribeirao preto": "SP",
    "rio de janeiro": "RJ",
    "sao luis": "MA",
    "sao paulo": "SP",
    "vitoria": "ES",
}


def normalizar(texto):
    texto = unicodedata.normalize("NFD", texto or "")
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto).strip().lower()


def localizar_uf(local):
    texto = normalizar(local)
    # Nomes maiores primeiro evita que Mato Grosso capture Mato Grosso do Sul.
    for uf, (nome, _, _) in sorted(ESTADOS.items(), key=lambda item: -len(item[1][0])):
        if normalizar(nome) in texto:
            return uf
    for cidade, uf in ALIASES_CIDADES.items():
        if cidade in texto:
            return uf
    return None


def limpar(valor):
    return (valor or "").strip()


def preparar(csv_origem):
    vagas = []
    with csv_origem.open(encoding="utf-8-sig", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            modalidade = limpar(linha.get("modalidade")) or "Não informada"
            remoto = normalizar(modalidade) == "remoto"
            local_anunciado = limpar(linha.get("local_anunciado"))
            abrangencia = limpar(linha.get("abrangencia_remota"))

            if remoto:
                uf = ""
                estado = "Remoto"
                regiao = "Remoto"
                local_exibicao = abrangencia or local_anunciado or "Abrangência não informada"
            else:
                uf = localizar_uf(local_anunciado) or ""
                if uf:
                    estado, regiao, _ = ESTADOS[uf]
                else:
                    estado = "Local não identificado"
                    regiao = "Local não identificado"
                local_exibicao = local_anunciado or "Local não informado"

            vagas.append(
                {
                    "id": limpar(linha.get("job_id")),
                    "titulo": limpar(linha.get("titulo")) or "Título não informado",
                    "empresa": limpar(linha.get("empresa")) or "Empresa não informada",
                    "modalidade": modalidade,
                    "regiao": regiao,
                    "uf": uf,
                    "estado": estado,
                    "local": local_exibicao,
                    "nivel": limpar(linha.get("nivel_cargo")) or "Não informado",
                    "contrato": limpar(linha.get("tipo_contrato")) or "Não informado",
                    "url": limpar(linha.get("url_vaga")),
                }
            )
    return vagas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("--geojson", type=Path, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    args = parser.parse_args()

    args.saida.mkdir(parents=True, exist_ok=True)
    vagas = preparar(args.csv)
    geojson = json.loads(args.geojson.read_text(encoding="utf-8"))

    (args.saida / "dados-vagas.js").write_text(
        "window.VAGAS_DATA=" + json.dumps(vagas, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    (args.saida / "brasil-ufs.js").write_text(
        "window.BRASIL_UFS=" + json.dumps(geojson, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )

    sem_local = sum(vaga["regiao"] == "Local não identificado" for vaga in vagas)
    remotas = sum(vaga["regiao"] == "Remoto" for vaga in vagas)
    print(f"{len(vagas)} vagas preparadas; {remotas} remotas; {sem_local} sem UF.")


if __name__ == "__main__":
    main()
