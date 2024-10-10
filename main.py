import asyncio
import logging
from playwright.async_api import Playwright, async_playwright
from utils.menu import Menu
import sqlite3

# Estado global para armazenar o progresso das conversas de cada usuário
conversas_ativas = {}
page_locks = {}  # Bloqueio para sincronizar o acesso ao 'page' para cada usuário
contato_cache = {}  # Cache para armazenar contatos recentemente acessados

logging.basicConfig(
    level=logging.DEBUG,  # Defina o nível de logging que desejar (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),  # Logs serão salvos no arquivo 'bot.log'
        logging.StreamHandler()          # Logs também serão exibidos no console
    ]
)

async def processar_conversa(page, telefone, menu):
    logging.info(f"Iniciando processamento da conversa com {telefone}.")

    # Selecionar a conversa do usuário
    logging.debug(f"Selecionando conversa com {telefone}.")
    selecionado = await selecionar_conversa(page, telefone)
    if not selecionado:
        logging.error(f"Não foi possível selecionar a conversa com {telefone}.")
        return

    # Capturar mensagens existentes antes de iniciar a interação
    await menu.capturar_mensagens_existentes(page, telefone)

    # Enviar mensagem inicial
    logging.debug(f'Enviando primeiro menu para {telefone}.')
    # Enviar mensagem inicial
    async with get_lock(telefone):
        await menu.enviar_mensagem(page, menu.saudacao1(), telefone=telefone, menu_numero=1)

    # Capturar a posição atual das mensagens
    total_mensagens = len(menu.mensagens_cache.get(telefone, []))
    menu.posicao_ultima_mensagem[telefone] = total_mensagens

    # Aguardar resposta do usuário para o primeiro menu
    logging.debug(f"Aguardando resposta do usuário {telefone} para o primeiro menu.")
    opcao = await menu.aguardar_resposta(page, telefone, menu_atual=1)
    logging.info(f"Opção selecionada por {telefone} no primeiro menu: {opcao}")

    # Se a opção for '1', exibir o segundo menu
    if opcao == '1':
        logging.debug(f"Enviando segundo menu para {telefone}.")
        await selecionar_conversa(page, telefone)
        async with get_lock(telefone):
            await menu.enviar_mensagem(page, menu.saudacao2(), telefone=telefone, menu_numero=2)

        # Aguardar resposta para o segundo menu
        logging.debug(f"Aguardando resposta do usuário {telefone} para o segundo menu.")
        opcao2 = await menu.aguardar_resposta(page, telefone, menu_atual=2)
        logging.info(f"Opção selecionada por {telefone} no segundo menu: {opcao2}")

        # Verificar as opções do segundo menu
        if opcao2 == '1':
            # Solicitar o RG
            await selecionar_conversa(page, telefone)
            async with get_lock(telefone):
                await menu.enviar_mensagem(page, "Por favor, preencha seu RG")

            # Aguardar a resposta do usuário (RG)
            rg = await menu.aguardar_resposta_rg(page, telefone)
            logging.info(f"RG recebido de {telefone}: {rg}")

            # Consultar o banco de dados SQLite
            conn = sqlite3.connect('obra_de_maria.db')
            cursor = conn.cursor()
            cursor.execute("SELECT Nome, Turma FROM beneficiados WHERE RG = ?", (rg,))
            resultado = cursor.fetchone()

            if resultado:
                nome, turma = resultado
                cursor.execute("SELECT semana FROM turmas WHERE turma = ?", (turma,))
                semana_result = cursor.fetchone()
                if semana_result:
                    semana = semana_result[0]
                    mensagem = f"{nome}, você deverá comparecer na semana {semana} para o evento."
                else:
                    mensagem = "Não foi possível encontrar a semana correspondente à sua turma."
            else:
                mensagem = "RG não encontrado no sistema."

            conn.close()

            # Enviar a mensagem com as informações ao usuário
            await selecionar_conversa(page, telefone)
            async with get_lock(telefone):
                await menu.enviar_mensagem(page, mensagem)

            # Fechar a conversa atual
            async with get_lock(telefone):
                await page.locator('//*[@id="side"]/header/div[2]/div/span/div[3]/div').click()

        elif opcao2 == '2':
            # Resposta "Ainda em construção"
            await selecionar_conversa(page, telefone)
            async with get_lock(telefone):
                await menu.enviar_mensagem(page, "Ainda em construção")

            # Fechar a conversa atual
            async with get_lock(telefone):
                await page.locator('//*[@id="side"]/header/div[2]/div/span/div[3]/div').click()
    elif opcao == '2':
        # Resposta "Ainda em construção" e fecha a conversa
        await selecionar_conversa(page, telefone)
        async with get_lock(telefone):
            await menu.enviar_mensagem(page, "Ainda em construção")

        # Fechar a conversa atual
        async with get_lock(telefone):
            await page.locator('//*[@id="side"]/header/div[2]/div/span/div[3]/div').click()

async def selecionar_conversa(page, telefone):
    """Seleciona a conversa do usuário com base no número de telefone."""
    if telefone in contato_cache:
        parent = contato_cache[telefone]
        try:
            # Verifica se o elemento ainda está anexado ao DOM usando JavaScript
            is_attached = await parent.evaluate("(node) => document.contains(node)")
            if is_attached:
                await parent.click()
                await asyncio.sleep(1)
                logging.debug(f"Conversa com {telefone} selecionada (usando cache).")
                return True
        except Exception as e:
            logging.error(f"Erro ao clicar no contato {telefone} (cache): {e}")
            del contato_cache[telefone]

    async with get_lock(telefone):
        # Revalida a lista de contatos antes de tentar clicar
        contatos = await page.query_selector_all('//*[@id="pane-side"]//span[@dir="auto"]')
        for contato in contatos:
            nome_contato = await contato.inner_text()
            if telefone == nome_contato:
                parent = await contato.evaluate_handle('node => node.closest("div[role=gridcell]")')
                try:
                    # Verifica se o elemento ainda está anexado ao DOM usando JavaScript
                    is_attached = await parent.evaluate("(node) => document.contains(node)")
                    if is_attached:
                        await parent.click()
                        await asyncio.sleep(1)
                        contato_cache[telefone] = parent
                        logging.debug(f"Conversa com {telefone} selecionada.")
                        return True
                except Exception as e:
                    logging.error(f"Erro ao clicar no contato {telefone}: {e}")
                    return False
        logging.warning(f"Contato {telefone} não encontrado.")
        return False

async def monitorar_mensagens(playwright: Playwright):
    menu = Menu()
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context()

    page = await context.new_page()
    page.set_default_timeout(0)

    await page.goto("https://web.whatsapp.com/")
    logging.info("Navegado para WhatsApp Web.")

    # Selecionar a aba "Tudo"
    await page.wait_for_selector('xpath=/html/body/div[1]/div/div/div[2]/div[3]/div/div[2]/button[1]/div/div/div')
    await page.locator('xpath=/html/body/div[1]/div/div/div[2]/div[3]/div/div[2]/button[1]/div/div/div').click()  # Clicar na aba "Tudo"
    logging.debug("Aba 'Tudo' selecionada.")

    while True:
        await asyncio.sleep(5)  # Verificação a cada 5 segundos para melhorar performance
        # Selecionar apenas contatos com novas mensagens (novas mensagens identificadas pelo número de mensagens não lidas)
        contatos_com_novas_mensagens = await page.query_selector_all('div._ahlk span[aria-label]')  # Seletor para o ícone de mensagem não lida
        logging.debug(f"{len(contatos_com_novas_mensagens)} contatos com novas mensagens encontrados.")
        for contato in contatos_com_novas_mensagens:
            try:
                async with get_lock(await contato.inner_text()):
                    is_attached = await contato.evaluate("(node) => document.contains(node)")
                    if is_attached:
                        await contato.click()
                    else:
                        logging.warning(f"Contato não anexado ao DOM: {contato}")
            except Exception as e:
                logging.error(f"Erro ao clicar no contato: {e}")
                continue

            # Captura o telefone do contato
            telefone = await page.locator('//*[@id="main"]/header/div[2]/div/div/div/span').inner_text()
            logging.info(f"Iniciando interação com o contato: {telefone}")

            # Verifica se já estamos conversando com esse usuário
            if telefone not in conversas_ativas:
                # Inicia uma nova conversa
                conversas_ativas[telefone] = asyncio.create_task(processar_conversa(page, telefone, menu))
            else:
                logging.info(f"Já estamos conversando com o usuário {telefone}")

            # Cancelar a tarefa se ela ainda estiver pendente (para evitar vazamento de recursos)
            if conversas_ativas[telefone].done():
                conversas_ativas[telefone].result()  # Levanta exceções, se houver
                del conversas_ativas[telefone]


def get_lock(telefone):
    if telefone not in page_locks:
        page_locks[telefone] = asyncio.Lock()
    return page_locks[telefone]

async def main() -> None:
    async with async_playwright() as playwright:
        await monitorar_mensagens(playwright)

if __name__ == "__main__":
    asyncio.run(main())