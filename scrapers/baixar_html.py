"""Baixa páginas HTML de vagas exibidas na busca do LinkedIn.

O script controla um navegador Chromium com Playwright, percorre os resultados
da busca definida em ``URL_INICIAL``, abre cada cartão de vaga e salva o HTML
completo da página enquanto os detalhes daquela vaga estão visíveis.

Os arquivos são gravados na pasta ``htmls``. O Chromium usa a pasta
``perfil_navegador`` como perfil persistente para reaproveitar cookies,
preferências e uma possível sessão autenticada entre execuções.

Como o LinkedIn carrega parte do conteúdo dinamicamente, o script combina
esperas explícitas e rolagens de página para permitir que os cartões e seus
detalhes sejam renderizados antes do salvamento.
"""

from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


# Endereço que serve de base para todas as páginas percorridas. Seus filtros,
# palavras-chave e ordenação são preservados; apenas o parâmetro ``start`` é
# alterado pela função ``montar_url_pagina``.
URL_INICIAL = (
    "https://www.linkedin.com/jobs/search/"
    "?currentJobId=4420661415&f_WT=3&geoId=106057199&keywords=ciencia%20de%20dados&origin=JOB_SEARCH_PAGE_JOB_FILTER&refresh=true&sortBy=R&start=25"
)

# Caminhos usados pelo script. ``BASE_DIR`` é a pasta que contém este arquivo,
# independentemente da pasta a partir da qual o comando Python seja executado.
BASE_DIR = Path(__file__).resolve().parent
PASTA_SAIDA = BASE_DIR / "htmls"
PASTA_PERFIL = BASE_DIR / "perfil_navegador"

# Parâmetros de paginação, espera e controle das tentativas de rolagem.
VAGAS_POR_PAGINA = 25
TEMPO_ESPERA_MS = 1500
MAX_TENTATIVAS_SEM_CRESCER = 4

# Seletores CSS alternativos para os cartões de vaga. Há mais de um porque a
# estrutura da página pode variar conforme a versão da interface do LinkedIn.
SELETORES_VAGA = [
    "li.jobs-search-results__list-item",
    ".job-card-container",
    "[data-job-id]",
]

# Seletor CSS composto para o painel que exibe os detalhes da vaga selecionada.
# As vírgulas significam "qualquer um destes seletores" em CSS.
SELETOR_DETALHES = (
    ".jobs-search__job-details--container, "
    ".jobs-details, "
    ".job-view-layout"
)


def montar_url_pagina(url: str, pagina: int) -> str:
    """Monta a URL correspondente ao número de página solicitado.

    O LinkedIn representa a paginação por meio do parâmetro ``start``, que
    indica o deslocamento do primeiro resultado. O valor originalmente contido
    na URL é usado como ponto inicial; a cada página são acrescentadas
    ``VAGAS_POR_PAGINA`` posições.

    Por exemplo, se a URL recebida contém ``start=25`` e há 25 vagas por
    página, os números 1, 2 e 3 geram respectivamente ``start=25``,
    ``start=50`` e ``start=75``.

    Args:
        url: URL base da pesquisa, incluindo filtros e parâmetros existentes.
        pagina: Número da página desejada, começando em 1.

    Returns:
        Uma nova URL com o parâmetro ``start`` atualizado.
    """
    # Separa a URL em esquema, domínio, caminho, parâmetros e fragmento.
    partes = urlparse(url)

    # Converte a query string em um dicionário. ``parse_qs`` armazena cada
    # valor em uma lista porque um parâmetro pode aparecer mais de uma vez.
    query = parse_qs(partes.query)
    start_inicial = int(query.get("start", ["0"])[0] or 0)
    query["start"] = [str(start_inicial + ((pagina - 1) * VAGAS_POR_PAGINA))]

    # Reconstrói apenas a query string e depois a URL completa, preservando
    # todos os demais componentes da URL recebida.
    nova_query = urlencode(query, doseq=True)
    return urlunparse(partes._replace(query=nova_query))


def rolar_ate_o_fim(page) -> None:
    """Rola o documento até que sua altura pare de aumentar.

    Algumas partes da página são carregadas somente quando o usuário se
    aproxima do final do documento. A função rola até o fim, espera o conteúdo
    dinâmico e compara a nova altura com a anterior. Ela encerra após
    ``MAX_TENTATIVAS_SEM_CRESCER`` verificações consecutivas sem crescimento.

    Args:
        page: Página do Playwright que está exibindo os resultados da busca.
    """
    altura_anterior = 0
    tentativas_sem_crescer = 0

    while tentativas_sem_crescer < MAX_TENTATIVAS_SEM_CRESCER:
        # Executa JavaScript dentro da página para levar a janela ao final.
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(TEMPO_ESPERA_MS)

        altura_atual = page.evaluate("document.body.scrollHeight")
        if altura_atual == altura_anterior:
            # Nenhum conteúdo novo aumentou a altura nesta tentativa.
            tentativas_sem_crescer += 1
        else:
            # Se a página cresceu, reinicia a contagem de tentativas paradas.
            tentativas_sem_crescer = 0
            altura_anterior = altura_atual


def localizar_vagas(page):
    """Localiza os cartões de vaga usando o primeiro seletor válido.

    Os seletores de ``SELETORES_VAGA`` são testados na ordem em que foram
    definidos. Isso permite que o scraper continue funcionando em diferentes
    estruturas da interface, desde que ao menos uma delas esteja presente.

    Args:
        page: Página do Playwright que contém a lista de resultados.

    Returns:
        Um ``Locator`` do Playwright que representa os cartões encontrados.
        Se nenhum seletor encontrar elementos imediatamente, retorna um
        ``Locator`` baseado no primeiro seletor para manter o tipo de retorno.
    """
    for seletor in SELETORES_VAGA:
        vagas = page.locator(seletor)
        if vagas.count() > 0:
            return vagas

    # Um Locator é uma consulta dinâmica: ele ainda poderá encontrar elementos
    # caso os cartões sejam inseridos no DOM depois desta chamada.
    return page.locator(SELETORES_VAGA[0])


def esperar_pagina_carregar(page) -> bool:
    """Espera a atividade de rede estabilizar e os cartões aparecerem.

    A espera por ``networkidle`` é apenas uma tentativa, pois aplicações como o
    LinkedIn podem manter requisições em segundo plano continuamente. A
    condição realmente necessária é a presença de pelo menos um dos seletores
    de vaga.

    Args:
        page: Página do Playwright recém-navegada para uma página da busca.

    Returns:
        ``True`` quando algum cartão de vaga aparece; ``False`` quando nenhum
        cartão é encontrado dentro do limite de 30 segundos.
    """
    try:
        # Aguarda no máximo 20 segundos por um período sem atividade de rede.
        page.wait_for_load_state("networkidle", timeout=20_000)
    except PlaywrightTimeoutError:
        # Este timeout não é fatal: o conteúdo útil pode já estar disponível.
        print("A pagina continuou fazendo requisicoes; seguindo mesmo assim.", flush=True)

    try:
        # Os seletores unidos por vírgula formam uma consulta CSS alternativa.
        page.wait_for_selector(", ".join(SELETORES_VAGA), timeout=30_000)
    except PlaywrightTimeoutError:
        print("Nenhuma vaga apareceu nesta pagina.", flush=True)
        return False

    # Pequena espera adicional para que scripts e animações terminem de
    # atualizar os elementos que acabaram de aparecer.
    page.wait_for_timeout(TEMPO_ESPERA_MS)
    return True


def rolar_lista_de_vagas(page) -> None:
    """Rola o contêiner da lista até carregar todas as vagas disponíveis.

    A lista de resultados pode ter sua própria barra de rolagem, separada da
    janela principal. O JavaScript procura, a partir do primeiro cartão, o
    ancestral rolável mais próximo. Se nenhum for encontrado, rola o documento.

    O processo termina quando encontra ``VAGAS_POR_PAGINA`` cartões ou quando a
    quantidade deixa de aumentar pelo número máximo de tentativas permitido.

    Args:
        page: Página do Playwright que contém a lista de resultados.
    """
    # Une os seletores em uma única consulta aceita por ``querySelector``.
    seletor_vagas = ", ".join(SELETORES_VAGA)
    quantidade_anterior = 0
    tentativas_sem_crescer = 0

    while tentativas_sem_crescer < MAX_TENTATIVAS_SEM_CRESCER:
        quantidade_atual = localizar_vagas(page).count()

        # Não é necessário continuar quando a quantidade esperada já apareceu.
        if quantidade_atual >= VAGAS_POR_PAGINA:
            break

        page.evaluate(
            """
            (seletorVagas) => {
                // Usa o primeiro cartão como ponto de partida para descobrir
                // qual elemento da interface possui a barra de rolagem.
                const vaga = document.querySelector(seletorVagas);
                let elemento = vaga;

                while (elemento) {
                    const estilo = window.getComputedStyle(elemento);
                    const rolagemVertical = estilo.overflowY;
                    const podeRolar = elemento.scrollHeight > elemento.clientHeight;

                    // Um elemento é rolável quando o conteúdo ultrapassa sua
                    // altura visível e o CSS habilita a rolagem vertical.
                    if (podeRolar && ["auto", "scroll"].includes(rolagemVertical)) {
                        elemento.scrollTop = elemento.scrollHeight;
                        return;
                    }

                    elemento = elemento.parentElement;
                }

                // Alternativa para páginas em que a lista não possui um
                // contêiner de rolagem próprio.
                window.scrollTo(0, document.body.scrollHeight);
            }
            """,
            seletor_vagas,
        )
        page.wait_for_timeout(TEMPO_ESPERA_MS)

        nova_quantidade = localizar_vagas(page).count()
        if nova_quantidade == quantidade_anterior:
            tentativas_sem_crescer += 1
        else:
            # Qualquer crescimento indica que a rolagem carregou novos cartões.
            tentativas_sem_crescer = 0
            quantidade_anterior = nova_quantidade


def rolar_lista_um_pouco(page) -> None:
    """Avança aproximadamente 85% da área visível da lista de vagas.

    O avanço gradual permite revelar cartões virtualizados ou carregados sob
    demanda durante o processamento. Assim como ``rolar_lista_de_vagas``, a
    função prefere o contêiner rolável da lista e usa a janela como alternativa.

    Args:
        page: Página do Playwright que contém a lista de resultados.
    """
    page.evaluate(
        """
        (seletorVagas) => {
            const vaga = document.querySelector(seletorVagas);
            let elemento = vaga;

            while (elemento) {
                const estilo = window.getComputedStyle(elemento);
                const rolagemVertical = estilo.overflowY;
                const podeRolar = elemento.scrollHeight > elemento.clientHeight;

                if (podeRolar && ["auto", "scroll"].includes(rolagemVertical)) {
                    // Avança quase uma tela, mantendo uma pequena sobreposição
                    // com a área anterior para não saltar cartões.
                    elemento.scrollTop += Math.floor(elemento.clientHeight * 0.85);
                    return;
                }

                elemento = elemento.parentElement;
            }

            // Usa a janela quando não há um contêiner rolável específico.
            window.scrollBy(0, Math.floor(window.innerHeight * 0.85));
        }
        """,
        ", ".join(SELETORES_VAGA),
    )
    page.wait_for_timeout(TEMPO_ESPERA_MS)


def rolar_lista_para_o_inicio(page) -> None:
    """Retorna a lista de vagas ao início antes de processar os cartões.

    A função de carregamento percorre a lista até o final. Este retorno ao topo
    garante que os cartões sejam visitados desde o primeiro resultado. Se a
    lista não possuir rolagem própria, a janela principal é levada ao topo.

    Args:
        page: Página do Playwright que contém a lista de resultados.
    """
    page.evaluate(
        """
        (seletorVagas) => {
            const vaga = document.querySelector(seletorVagas);
            let elemento = vaga;

            while (elemento) {
                const estilo = window.getComputedStyle(elemento);
                const rolagemVertical = estilo.overflowY;
                const podeRolar = elemento.scrollHeight > elemento.clientHeight;

                if (podeRolar && ["auto", "scroll"].includes(rolagemVertical)) {
                    elemento.scrollTop = 0;
                    return;
                }

                elemento = elemento.parentElement;
            }

            // Alternativa usada quando a rolagem pertence à página inteira.
            window.scrollTo(0, 0);
        }
        """,
        ", ".join(SELETORES_VAGA),
    )
    page.wait_for_timeout(TEMPO_ESPERA_MS)


def chave_da_vaga(vaga, indice: int) -> str:
    """Produz um identificador para evitar o processamento repetido de vagas.

    A identificação segue uma ordem de preferência:

    1. atributo ``data-job-id`` do cartão ou de um elemento relacionado;
    2. endereço do link que contém ``/jobs/view/``;
    3. os primeiros 300 caracteres do texto do cartão;
    4. uma chave baseada no índice, se as opções anteriores falharem.

    Args:
        vaga: ``Locator`` do Playwright que representa um cartão de vaga.
        indice: Posição atual do cartão na lista, usada no último fallback.

    Returns:
        Uma string não vazia usada nos conjuntos de vagas já visitadas.
    """
    try:
        chave = vaga.evaluate(
            """
            (elemento) => {
                // O ID pode estar no próprio cartão, em um ancestral ou em um
                // descendente, dependendo da estrutura atual da página.
                const comId = elemento.closest("[data-job-id]") || elemento.querySelector("[data-job-id]");
                if (comId && comId.dataset.jobId) {
                    return comId.dataset.jobId;
                }

                // O endereço da página da vaga também funciona como chave.
                const link = elemento.querySelector("a[href*='/jobs/view/']");
                if (link) {
                    return link.href;
                }

                // O texto é menos estável, mas ainda permite distinguir a
                // maioria dos cartões quando não há ID nem link disponível.
                return elemento.innerText.trim().slice(0, 300);
            }
            """
        )
        return chave or f"vaga-sem-chave-{indice}"
    except PlaywrightTimeoutError:
        # Evita interromper toda a coleta se um cartão ficar indisponível.
        return f"vaga-sem-chave-{indice}"


def texto_painel_detalhes(page) -> str:
    """Lê o texto atualmente exibido no painel de detalhes da vaga.

    O texto é capturado antes de clicar em outro cartão. Depois do clique, ele
    serve de referência para verificar se o painel realmente foi atualizado.

    Args:
        page: Página do Playwright que contém o painel de detalhes.

    Returns:
        O texto visível do primeiro painel encontrado ou uma string vazia se o
        painel ainda não existir ou não puder ser lido dentro de dois segundos.
    """
    detalhes = page.locator(SELETOR_DETALHES).first
    if detalhes.count() == 0:
        return ""

    try:
        return detalhes.inner_text(timeout=2_000)
    except PlaywrightTimeoutError:
        # A ausência do texto anterior não impede o clique na próxima vaga.
        return ""


def esperar_detalhes_da_vaga(page, texto_anterior: str) -> None:
    """Espera o painel mostrar os detalhes da vaga que acabou de ser clicada.

    Primeiro, aguarda a existência do painel. Depois, executa uma condição
    JavaScript repetidamente até que o painel tenha conteúdo e seu texto seja
    diferente daquele exibido antes do clique. Isso reduz a possibilidade de
    salvar o HTML enquanto os detalhes da vaga anterior ainda estão visíveis.

    O timeout não interrompe a coleta: nesse caso, o script emite um aviso e
    salva o estado disponível da página.

    Args:
        page: Página do Playwright na qual o cartão foi clicado.
        texto_anterior: Texto exibido no painel antes do clique.
    """
    try:
        page.wait_for_selector(SELETOR_DETALHES, timeout=20_000)
        page.wait_for_function(
            """
            ([seletor, textoAnterior]) => {
                const painel = document.querySelector(seletor);
                const textoAtual = painel ? painel.innerText.trim() : "";

                // A condição fica verdadeira somente quando há conteúdo novo.
                return textoAtual.length > 0 && textoAtual !== textoAnterior;
            }
            """,
            arg=[SELETOR_DETALHES, texto_anterior],
            timeout=20_000,
        )
    except PlaywrightTimeoutError:
        print("Nao consegui confirmar a troca do painel de detalhes; salvando mesmo assim.", flush=True)

    # Dá tempo para elementos secundários, como descrições e botões, terminarem
    # de atualizar depois que a mudança principal do painel foi detectada.
    page.wait_for_timeout(TEMPO_ESPERA_MS)


def salvar_html(page, numero_pagina: int, numero_vaga: int | None = None) -> None:
    """Salva em disco o HTML completo do estado atual da página.

    Quando ``numero_vaga`` é informado, o nome segue o padrão
    ``pagina_001_vaga_001.html``. Sem esse número, usa ``pagina_001.html``.
    Os zeros à esquerda mantêm os arquivos ordenados alfabeticamente.

    Args:
        page: Página do Playwright cujo HTML será salvo.
        numero_pagina: Número da página atual da busca.
        numero_vaga: Posição da vaga processada na página; é opcional para
            permitir o salvamento de uma página sem associação a uma vaga.
    """
    # Cria a pasta somente se necessário. ``exist_ok=True`` evita erro quando
    # ela já existe de uma execução anterior.
    PASTA_SAIDA.mkdir(exist_ok=True)

    if numero_vaga is None:
        caminho = PASTA_SAIDA / f"pagina_{numero_pagina:03}.html"
    else:
        caminho = PASTA_SAIDA / f"pagina_{numero_pagina:03}_vaga_{numero_vaga:03}.html"

    # ``page.content`` devolve o HTML atual do DOM, já com as alterações feitas
    # pelos scripts da página até este momento.
    caminho.write_text(page.content(), encoding="utf-8")
    print(f"HTML salvo em {caminho}", flush=True)


def clicar_e_salvar_vagas(page, numero_pagina: int, vagas_visitadas_global: set[str]) -> int:
    """Abre e salva cada vaga nova encontrada na página atual.

    A lista é carregada e devolvida ao início. Em seguida, cada cartão recebe
    uma chave e é ignorado caso já tenha sido processado na página atual ou em
    uma página anterior. Para uma vaga nova, a função clica no cartão, espera a
    atualização do painel de detalhes e salva o HTML completo.

    O processamento para ao atingir ``VAGAS_POR_PAGINA`` vagas ou após várias
    tentativas consecutivas de rolagem sem encontrar um cartão novo.

    Args:
        page: Página do Playwright que exibe a busca e os detalhes das vagas.
        numero_pagina: Número usado para identificar os arquivos desta página.
        vagas_visitadas_global: Conjunto compartilhado entre todas as páginas;
            ele é modificado pela função à medida que novas vagas são abertas.

    Returns:
        Quantidade de vagas novas salvas na página atual.
    """
    # Carrega tantos cartões quanto possível e volta ao primeiro resultado.
    rolar_lista_de_vagas(page)
    rolar_lista_para_o_inicio(page)

    # O conjunto local controla a quantidade e as duplicatas da página atual.
    # O contador encerra o laço se as rolagens deixarem de revelar vagas novas.
    vagas_visitadas_pagina = set()
    tentativas_sem_vaga_nova = 0

    print(f"Clicando em ate {VAGAS_POR_PAGINA} vagas da pagina {numero_pagina}.", flush=True)

    while (
        len(vagas_visitadas_pagina) < VAGAS_POR_PAGINA
        and tentativas_sem_vaga_nova < MAX_TENTATIVAS_SEM_CRESCER
    ):
        vagas = localizar_vagas(page)
        quantidade_vagas = vagas.count()
        encontrou_vaga_nova = False

        for indice in range(quantidade_vagas):
            vaga = vagas.nth(indice)
            chave = chave_da_vaga(vaga, indice)

            # Evita salvar novamente a mesma vaga, inclusive quando ela aparece
            # repetida em páginas diferentes da pesquisa.
            if chave in vagas_visitadas_pagina or chave in vagas_visitadas_global:
                continue

            # Guarda o conteúdo antigo para confirmar que o clique atualizou o
            # painel, em vez de salvar novamente os detalhes da vaga anterior.
            texto_anterior = texto_painel_detalhes(page)
            vaga.scroll_into_view_if_needed(timeout=10_000)
            page.wait_for_timeout(500)
            vaga.click(timeout=10_000)

            # Registra a chave assim que o clique é realizado para que o cartão
            # não seja processado outra vez em uma iteração posterior.
            vagas_visitadas_pagina.add(chave)
            vagas_visitadas_global.add(chave)
            encontrou_vaga_nova = True

            esperar_detalhes_da_vaga(page, texto_anterior)
            salvar_html(page, numero_pagina, len(vagas_visitadas_pagina))

            # Cada página da busca deve fornecer no máximo a quantidade
            # configurada em ``VAGAS_POR_PAGINA``.
            if len(vagas_visitadas_pagina) >= VAGAS_POR_PAGINA:
                break

        if encontrou_vaga_nova:
            # Uma vaga nova confirma que ainda vale a pena continuar procurando.
            tentativas_sem_vaga_nova = 0
        else:
            tentativas_sem_vaga_nova += 1

        # Move a lista para revelar cartões que podem não estar presentes ou
        # renderizados na região atualmente visível.
        rolar_lista_um_pouco(page)

    print(f"{len(vagas_visitadas_pagina)} vagas novas salvas na pagina {numero_pagina}.", flush=True)
    return len(vagas_visitadas_pagina)


def baixar_paginas() -> None:
    """Percorre as páginas da busca do LinkedIn e salva o HTML de cada vaga.

    O navegador usa um perfil persistente, armazenado em ``PASTA_PERFIL``.
    Dessa forma, cookies, preferências e uma possível sessão autenticada podem
    ser reaproveitados entre diferentes execuções do script.

    A busca termina em uma destas situações:
    - a página atual não apresenta nenhum cartão de vaga; ou
    - todos os cartões encontrados já haviam sido visitados.

    Esta função apenas coordena o processo. A montagem das URLs, as esperas, a
    rolagem, os cliques e o salvamento dos arquivos ficam a cargo das funções
    auxiliares definidas acima.
    """
    # Inicia a API síncrona do Playwright. O bloco ``with`` também garante que
    # os recursos internos do Playwright sejam liberados ao sair dele.
    with sync_playwright() as p:
        # Abre o Chromium usando sempre a mesma pasta de perfil. ``headless``
        # igual a False deixa a janela visível para acompanhar a automação.
        contexto = p.chromium.launch_persistent_context(
            user_data_dir=str(PASTA_PERFIL),
            headless=False,
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
        )

        # Um contexto persistente pode iniciar com uma aba aberta. Nesse caso,
        # ela é reutilizada; caso contrário, o script cria uma nova aba.
        page = contexto.pages[0] if contexto.pages else contexto.new_page()

        # ``numero_pagina`` controla a paginação da URL. O conjunto guarda as
        # chaves das vagas processadas em todas as páginas e evita duplicatas.
        numero_pagina = 1
        vagas_visitadas_global = set()

        # Não sabemos previamente quantas páginas existem. Por isso, o script
        # continua até uma das condições de parada abaixo ser atendida.
        while True:
            url = montar_url_pagina(URL_INICIAL, numero_pagina)
            print(f"Abrindo pagina {numero_pagina}: {url}", flush=True)

            # Espera o HTML inicial ser interpretado pelo navegador. Conteúdos
            # dinâmicos são aguardados separadamente em ``esperar_pagina_carregar``.
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            print(f"URL carregada: {page.url}", flush=True)

            # Se nenhum cartão de vaga aparecer, considera que a busca chegou
            # ao fim e interrompe o laço de paginação.
            if not esperar_pagina_carregar(page):
                print("Fim da busca: a pagina atual nao trouxe vagas.", flush=True)
                break

            # Aciona o carregamento de conteúdo preguiçoso, visita cada vaga
            # ainda não processada e salva o HTML após abrir seus detalhes.
            rolar_ate_o_fim(page)
            vagas_salvas = clicar_e_salvar_vagas(page, numero_pagina, vagas_visitadas_global)

            # Mesmo que existam cartões, todos podem ser repetidos. Sem vagas
            # novas, continuar para outras páginas provavelmente criaria loop.
            if vagas_salvas == 0:
                print("Fim da busca: a pagina atual nao trouxe vagas novas.", flush=True)
                break

            # Avança o deslocamento da busca em ``VAGAS_POR_PAGINA`` resultados.
            numero_pagina += 1

        # Fecha todas as abas e o processo do Chromium deste contexto.
        contexto.close()


if __name__ == "__main__":
    # Executa a coleta somente quando este arquivo é chamado diretamente.
    # Se ele for importado por outro módulo, suas funções ficam disponíveis sem
    # abrir automaticamente o navegador.
    baixar_paginas()
