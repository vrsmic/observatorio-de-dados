import argparse
import json
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup


PASTAS_PADRAO = [
    Path("/home/lucas/scraper-linkedin/htmls-Brasil-Hibrido"),
    Path("/home/lucas/scraper-linkedin/htmls-Brasil-Presencial"),
    Path("/home/lucas/scraper-linkedin/htmls-Brasil-Remoto"),
]
SAIDA_PADRAO = Path("/home/lucas/scraper-linkedin/vagas_extraidas.csv")

LINGUAGENS = {
    "Python": [r"\bpython\b"],
    "R": [r"(?<!\w)R(?!\w)", r"\blinguagem R\b"],
    "SQL": [r"\bsql\b"],
    "Java": [r"\bjava\b(?!script)"],
    "JavaScript": [r"\bjavascript\b", r"\bjs\b"],
    "TypeScript": [r"\btypescript\b"],
    "C++": [r"(?<!\w)c\+\+(?!\w)"],
    "C#": [r"(?<!\w)c#(?!\w)", r"\bc sharp\b"],
    "Scala": [r"\bscala\b"],
    "Kotlin": [r"\bkotlin\b"],
    "Go": [r"\bgolang\b", r"\blinguagem go\b"],
    "Rust": [r"\brust\b"],
    "Ruby": [r"\bruby\b"],
    "PHP": [r"\bphp\b"],
    "Swift": [r"\bswift\b"],
    "MATLAB": [r"\bmatlab\b"],
    "SAS": [r"\bsas\b"],
    "VBA": [r"\bvba\b"],
    "Shell/Bash": [r"\bbash\b", r"\bshell script\b"],
}

SKILLS = {
    "AWS": [r"\baws\b", r"amazon web services"],
    "Azure": [r"\bazure\b"],
    "GCP": [r"\bgcp\b", r"google cloud"],
    "Power BI": [r"\bpower bi\b"],
    "Tableau": [r"\btableau\b"],
    "Excel": [r"\bexcel\b"],
    "Spark": [r"\bapache spark\b", r"\bspark\b"],
    "PySpark": [r"\bpyspark\b"],
    "Databricks": [r"\bdatabricks\b"],
    "Snowflake": [r"\bsnowflake\b"],
    "BigQuery": [r"\bbigquery\b"],
    "Airflow": [r"\bairflow\b"],
    "dbt": [r"\bdbt\b"],
    "Hadoop": [r"\bhadoop\b"],
    "Kafka": [r"\bkafka\b"],
    "Docker": [r"\bdocker\b"],
    "Kubernetes": [r"\bkubernetes\b", r"\bk8s\b"],
    "Git": [r"\bgit\b", r"\bgithub\b", r"\bgitlab\b"],
    "Pandas": [r"\bpandas\b"],
    "NumPy": [r"\bnumpy\b"],
    "Scikit-learn": [r"\bscikit-learn\b", r"\bsklearn\b"],
    "TensorFlow": [r"\btensorflow\b"],
    "PyTorch": [r"\bpytorch\b"],
    "Machine Learning": [r"\bmachine learning\b", r"aprendizado de maquina"],
    "Deep Learning": [r"\bdeep learning\b", r"aprendizado profundo"],
    "IA Generativa": [r"\bia generativa\b", r"\bgenerative ai\b", r"\bgenai\b"],
    "LLM": [r"\bllms?\b", r"large language model"],
    "RAG": [r"\brag\b", r"retrieval.augmented generation"],
    "NLP": [r"\bnlp\b", r"processamento de linguagem natural"],
    "ETL/ELT": [r"\betl\b", r"\belt\b"],
    "Data Warehouse": [r"\bdata warehouse\b", r"\bdata warehousing\b"],
    "Data Lake": [r"\bdata lake\b", r"\bdatalake\b"],
    "APIs": [r"\bapis?\b", r"\brestful\b"],
    "MongoDB": [r"\bmongodb\b"],
    "PostgreSQL": [r"\bpostgres(?:ql)?\b"],
    "MySQL": [r"\bmysql\b"],
    "Oracle": [r"\boracle\b"],
    "Scrum": [r"\bscrum\b"],
    "Agile": [r"\bagile\b", r"\bagil\b"],
    "MLOps": [r"\bmlops\b"],
    "CI/CD": [r"\bci/?cd\b"],
    "DAX": [r"\bdax\b"],
    "Looker": [r"\blooker\b"],
    "Qlik": [r"\bqlik\b"],
    "Alteryx": [r"\balteryx\b"],
    "SAP": [r"\bsap\b"],
}

BENEFICIOS = {
    "Vale-alimentação": [
        r"\bvale[\s-]+alimenta[cç][aã]o\b",
        r"\bva\b",
        r"\baux[ií]lio[\s-]+alimenta[cç][aã]o\b",
    ],
    "Vale-refeição": [
        r"\bvale[\s-]+refei[cç][aã]o\b",
        r"\bvr\b",
        r"\baux[ií]lio[\s-]+refei[cç][aã]o\b",
    ],
    "Vale-alimentação/refeição flexível": [
        r"\bvale[\s-]+alimenta[cç][aã]o e refei[cç][aã]o\b",
        r"\bvale[\s-]+refei[cç][aã]o e alimenta[cç][aã]o\b",
        r"\bbenef[ií]cio flex[ií]vel\b",
        r"\bcart[aã]o flex[ií]vel\b",
        r"\bflash\b",
        r"\bcaju\b",
        r"\balelo\b",
    ],
    "Plano de saúde": [
        r"\bplano de sa[uú]de\b",
        r"\bassist[eê]ncia m[eé]dica\b",
        r"\bconv[eê]nio m[eé]dico\b",
        r"\bseguro sa[uú]de\b",
    ],
    "Plano odontológico": [
        r"\bplano odontol[oó]gico\b",
        r"\bassist[eê]ncia odontol[oó]gica\b",
        r"\bconv[eê]nio odontol[oó]gico\b",
    ],
    "Seguro de vida": [r"\bseguro de vida\b"],
    "Vale-transporte": [r"\bvale[\s-]+transporte\b", r"\baux[ií]lio[\s-]+transporte\b"],
    "Auxílio home office": [
        r"\baux[ií]lio home office\b",
        r"\bajuda de custo.*home office\b",
        r"\baux[ií]lio remoto\b",
        r"\bstipend.*home office\b",
    ],
    "Equipamento para home office": [
        r"\bequipamento.*home office\b",
        r"\bkit home office\b",
        r"\bnotebook.*trabalho\b",
    ],
    "Wellhub/Gympass": [r"\bwellhub\b", r"\bgympass\b"],
    "TotalPass": [r"\btotalpass\b"],
    "Auxílio-creche": [r"\baux[ií]lio[\s-]+creche\b", r"\bcreche\b"],
    "Previdência privada": [r"\bprevid[eê]ncia privada\b"],
    "Participação nos lucros": [r"\bplr\b", r"\bppr\b", r"\bparticipa[cç][aã]o nos lucros\b"],
    "Bônus": [r"\bb[oô]nus\b", r"\bremunera[cç][aã]o vari[aá]vel\b"],
    "Day off": [r"\bday off\b", r"\bfolga.*anivers[aá]rio\b"],
    "Licença parental estendida": [
        r"\blicen[cç]a maternidade.*estendida\b",
        r"\blicen[cç]a paternidade.*estendida\b",
        r"\blicen[cç]a parental\b",
    ],
    "Auxílio educação": [
        r"\baux[ií]lio educa[cç][aã]o\b",
        r"\bbolsa de estudos\b",
        r"\breembolso.*curso\b",
        r"\bsubs[ií]dio.*curso\b",
    ],
    "Curso de idiomas": [r"\bcurso[s]? de idiomas\b", r"\bsubs[ií]dio.*idioma\b"],
    "Desconto em produtos/serviços": [r"\bdesconto[s]? em produtos\b", r"\bdesconto[s]? em servi[cç]os\b"],
    "Vale-cultura": [r"\bvale[\s-]+cultura\b"],
    "Pet": [r"\bpetlove\b", r"\bplano de sa[uú]de pet\b", r"\bbenef[ií]cio pet\b"],
}

INICIOS_REQUISITOS = (
    "requisitos",
    "qualificacoes",
    "qualificações",
    "requirements",
    "qualifications",
    "o que esperamos",
    "o que voce precisa",
    "o que você precisa",
    "quem buscamos",
    "perfil desejado",
)
INICIOS_DESEJAVEIS = (
    "diferenciais",
    "desejavel",
    "desejável",
    "nice to have",
    "preferred",
    "sera um diferencial",
    "será um diferencial",
)
INICIOS_BENEFICIOS = (
    "beneficios",
    "benefícios",
    "vantagens",
    "o que oferecemos",
    "oferecemos",
    "benefits",
    "perks",
)
TITULOS_SECAO = INICIOS_REQUISITOS + INICIOS_DESEJAVEIS + INICIOS_BENEFICIOS + (
    "responsabilidades",
    "atribuicoes",
    "atribuições",
    "sobre a vaga",
    "sobre nos",
    "sobre nós",
    "informacoes adicionais",
    "informações adicionais",
    "hard skills",
    "soft skills",
    "atividades",
    "modelo de trabalho",
)


def sem_acentos(texto):
    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFD", texto or "")
        if unicodedata.category(caractere) != "Mn"
    )


def limpar_texto(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def primeiro_texto(container, seletores):
    for seletor in seletores:
        elemento = container.select_one(seletor)
        if elemento:
            texto = limpar_texto(elemento.get_text(" ", strip=True))
            if texto:
                return texto
    return None


def extrair_lista(texto, catalogo):
    encontrados = []
    for nome, padroes in catalogo.items():
        if any(re.search(padrao, texto, flags=re.IGNORECASE) for padrao in padroes):
            encontrados.append(nome)
    return encontrados


def eh_titulo_secao(linha):
    normalizada = sem_acentos(linha).lower().strip(" :-")
    return len(normalizada) <= 90 and any(
        normalizada.startswith(sem_acentos(titulo).lower()) for titulo in TITULOS_SECAO
    )


def extrair_secao(linhas, inicios, max_linhas=30):
    for indice, linha in enumerate(linhas):
        normalizada = sem_acentos(linha).lower().strip(" :-")
        if not any(normalizada.startswith(sem_acentos(inicio).lower()) for inicio in inicios):
            continue

        conteudo = []
        for seguinte in linhas[indice + 1 : indice + 1 + max_linhas]:
            if conteudo and eh_titulo_secao(seguinte):
                break
            if seguinte.lower() != "sobre a vaga":
                conteudo.append(seguinte)
        return " | ".join(conteudo) or None
    return None


def inferir_nivel(titulo, descricao):
    texto_titulo = sem_acentos(titulo).lower()
    texto_descricao = sem_acentos(descricao).lower()
    niveis = [
        ("Estágio", [r"\bestagi", r"\bintern(ship)?\b"]),
        ("Trainee", [r"\btrainee\b"]),
        ("Júnior", [r"\bjunior\b", r"\bjr\.?\b"]),
        ("Pleno", [r"\bpleno\b", r"\bmid.level\b"]),
        ("Sênior", [r"\bsenior\b", r"\bsr\.?\b"]),
        ("Especialista", [r"\bespecialista\b", r"\bprincipal\b", r"\bstaff\b"]),
        ("Gerência", [r"\bgerente\b", r"\bhead of\b"]),
        ("Diretoria", [r"\bdiretor", r"\bdirector\b"]),
    ]

    encontrados_titulo = [
        nivel for nivel, padroes in niveis if any(re.search(p, texto_titulo) for p in padroes)
    ]
    if encontrados_titulo:
        return ", ".join(encontrados_titulo)

    for nivel, padroes in niveis:
        for padrao in padroes:
            if re.search(rf"\b(?:nivel|senioridade|vaga)\s*(?:de|:|-)?\s*{padrao}", texto_descricao):
                return nivel
    return None


def extrair_salario(texto):
    padroes = [
        r"R\$\s*[\d.]+(?:,\d{2})?(?:\s*(?:a|até|-)\s*R?\$?\s*[\d.]+(?:,\d{2})?)?",
        r"(?:BRL|USD)\s*[\d.,]+(?:\s*(?:a|até|-)\s*(?:BRL|USD)?\s*[\d.,]+)?",
        r"(?:sal[aá]rio|remunera[cç][aã]o|salary)\s*(?:de|:|-)?\s*(?:R\$|BRL|USD|\$)\s*[\d.,]+",
    ]
    encontrados = []
    for padrao in padroes:
        encontrados.extend(re.findall(padrao, texto, flags=re.IGNORECASE))
    encontrados = [limpar_texto(x) for x in encontrados if "r$ 0" not in x.lower()]
    return " | ".join(dict.fromkeys(encontrados[:3])) or None


def calcular_data_publicacao(texto_relativo, data_coleta):
    if not texto_relativo:
        return None
    texto = sem_acentos(texto_relativo).lower()
    if "hoje" in texto or "hora" in texto or "minuto" in texto:
        data = data_coleta
    elif "ontem" in texto:
        data = data_coleta - timedelta(days=1)
    else:
        numero = int(re.search(r"\d+", texto).group()) if re.search(r"\d+", texto) else 1
        if "dia" in texto:
            data = data_coleta - timedelta(days=numero)
        elif "semana" in texto:
            data = data_coleta - timedelta(days=numero * 7)
        elif "mes" in texto:
            data = data_coleta - timedelta(days=numero * 30)
        else:
            return None
    return data.date().isoformat()


def separar_localizacao(local, modalidade):
    if sem_acentos(modalidade).lower() == "remoto":
        return "Remoto", local
    return local, None


def extrair_vaga(caminho, modalidade_pasta):
    html = caminho.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "lxml")
    container = (
        soup.select_one(".job-view-layout.jobs-details")
        or soup.select_one(".jobs-details")
        or soup.select_one(".scaffold-layout__detail")
        or soup
    )

    titulo = primeiro_texto(
        container,
        [
            ".job-details-jobs-unified-top-card__job-title h1",
            ".job-details-jobs-unified-top-card__job-title",
            "h1",
        ],
    )
    empresa = primeiro_texto(
        container,
        [".job-details-jobs-unified-top-card__company-name", "a[href*='/company/']"],
    )
    descricao_el = container.select_one("#job-details")
    descricao = limpar_texto(descricao_el.get_text(" ", strip=True)) if descricao_el else None
    linhas_descricao = (
        [limpar_texto(x) for x in descricao_el.stripped_strings if limpar_texto(x)]
        if descricao_el
        else []
    )

    link_vaga = container.select_one(".job-details-jobs-unified-top-card__job-title a[href*='/jobs/view/']")
    job_id = None
    if link_vaga:
        match = re.search(r"/jobs/view/(\d+)", link_vaga.get("href", ""))
        job_id = match.group(1) if match else None
    if not job_id:
        match = re.search(r"urn:li:fsd_jobPosting:(\d+)", html)
        job_id = match.group(1) if match else None

    topo = primeiro_texto(
        container,
        [".job-details-jobs-unified-top-card__tertiary-description-container"],
    )
    partes_topo = [limpar_texto(x) for x in re.split(r"\s*·\s*", topo or "") if limpar_texto(x)]
    local = partes_topo[0] if partes_topo else None
    publicado_ha = next(
        (
            p
            for p in partes_topo
            if re.search(r"\b(há|ha|ontem|hoje)\b", p, flags=re.IGNORECASE)
        ),
        None,
    )

    preferencias = [
        limpar_texto(x.get_text(" ", strip=True))
        for x in container.select(".job-details-fit-level-preferences button")
    ]
    modalidade = next(
        (x for x in preferencias if sem_acentos(x).lower() in {"remoto", "hibrido", "presencial"}),
        modalidade_pasta,
    )
    tipo_contrato = next(
        (
            x
            for x in preferencias
            if any(
                termo in sem_acentos(x).lower()
                for termo in ("tempo integral", "meio periodo", "estagio", "temporario", "contrato")
            )
        ),
        None,
    )

    texto_analise = f"{titulo or ''}\n{descricao or ''}"
    linguagens = extrair_lista(texto_analise, LINGUAGENS)
    skills = list(dict.fromkeys(linguagens + extrair_lista(texto_analise, SKILLS)))
    beneficios = extrair_lista(descricao or "", BENEFICIOS)
    beneficios_texto = extrair_secao(linhas_descricao, INICIOS_BENEFICIOS, max_linhas=40)
    local_trabalho, abrangencia_remota = separar_localizacao(local, modalidade)
    data_coleta = datetime.fromtimestamp(caminho.stat().st_mtime)

    return {
        "job_id": job_id,
        "arquivo": caminho.name,
        "pasta_origem": caminho.parent.name,
        "titulo": titulo,
        "empresa": empresa,
        "local": local_trabalho,
        "local_anunciado": local,
        "abrangencia_remota": abrangencia_remota,
        "modalidade": modalidade,
        "nivel_cargo": inferir_nivel(titulo or "", descricao or ""),
        "tipo_contrato": tipo_contrato,
        "salario": extrair_salario(texto_analise),
        "data_publicacao_texto": publicado_ha,
        "data_publicacao_estimada": calcular_data_publicacao(publicado_ha, data_coleta),
        "data_coleta_html": data_coleta.date().isoformat(),
        "pre_requisitos": extrair_secao(linhas_descricao, INICIOS_REQUISITOS),
        "desejaveis": extrair_secao(linhas_descricao, INICIOS_DESEJAVEIS),
        "beneficios": ", ".join(beneficios) or None,
        "beneficios_texto": beneficios_texto,
        "skills": ", ".join(skills) or None,
        "linguagens_programacao": ", ".join(linguagens) or None,
        "descricao": descricao,
        "url_vaga": f"https://www.linkedin.com/jobs/view/{job_id}/" if job_id else None,
    }


def modalidade_da_pasta(pasta):
    nome = sem_acentos(pasta.name).lower()
    for modalidade in ("Híbrido", "Presencial", "Remoto"):
        if sem_acentos(modalidade).lower() in nome:
            return modalidade
    return None


def main():
    parser = argparse.ArgumentParser(description="Extrai dados das vagas salvas em HTML.")
    parser.add_argument("pastas", nargs="*", type=Path, default=PASTAS_PADRAO)
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    args = parser.parse_args()

    arquivos = []
    for pasta in args.pastas:
        arquivos.extend((html, modalidade_da_pasta(pasta)) for html in sorted(pasta.glob("*.html")))

    print(f"Processando {len(arquivos)} HTMLs...", flush=True)
    registros = []
    erros = []
    for indice, (arquivo, modalidade) in enumerate(arquivos, start=1):
        try:
            registros.append(extrair_vaga(arquivo, modalidade))
        except Exception as erro:
            erros.append({"arquivo": str(arquivo), "erro": str(erro)})
        if indice % 50 == 0 or indice == len(arquivos):
            print(f"{indice}/{len(arquivos)} processados", flush=True)

    df_todos = pd.DataFrame(registros)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    saida_todos = args.saida.with_name(f"{args.saida.stem}_todos_htmls{args.saida.suffix}")
    df_todos.to_csv(saida_todos, index=False, encoding="utf-8-sig")

    if not df_todos.empty:
        df_unicos = df_todos.drop_duplicates(subset=["job_id"], keep="last")
    else:
        df_unicos = df_todos
    df_unicos.to_csv(args.saida, index=False, encoding="utf-8-sig")

    saida_erros = args.saida.with_name(f"{args.saida.stem}_erros.json")
    saida_erros.write_text(json.dumps(erros, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{len(df_todos)} arquivos extraidos; {len(df_unicos)} vagas unicas; {len(erros)} erros.")
    print(f"CSV deduplicado: {args.saida}")
    print(f"CSV completo: {saida_todos}")


if __name__ == "__main__":
    main()
