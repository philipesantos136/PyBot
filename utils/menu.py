import asyncio
import logging
import datetime
import re
import sqlite3

class Menu:
    def __init__(self):
        self.primeira_interacao = """
Jesus te ama, sou um atendente virtual para facilitar a gestão da coordenação da missão Comunidade Obra de Maria Missão São José - Várzea.
Informe apenas o número da opção desejada:
1 - Benefício de alimentos através do novo
2 - Ata da missão
"""
        self.segunda_interacao = """
Por favor, selecione uma das opções:
1 - Verificar escala
2 - Administração
"""
        self.opcoes_validas_primeiro_menu = ['1', '2']
        self.opcoes_validas_segundo_menu = ['1', '2']
        self.mensagens_processadas_por_usuario = {}
        self.horario_envio_menu1 = {}
        self.horario_envio_menu2 = {}
        self.posicao_ultima_mensagem = {}
        self.mensagens_cache = {}

    def saudacao1(self):
        logging.debug("Exibindo o primeiro menu.")
        return self.primeira_interacao

    def saudacao2(self):
        logging.debug("Exibindo o segundo menu.")
        return self.segunda_interacao

    def validar_opcao(self, escolha, menu_atual):
        logging.debug(f"Validando opção '{escolha}' para o menu {menu_atual}.")
        if menu_atual == 1 and escolha in self.opcoes_validas_primeiro_menu:
            logging.info(f'Opção válida selecionada no primeiro menu: {escolha}')
            return True
        elif menu_atual == 2 and escolha in self.opcoes_validas_segundo_menu:
            logging.info(f'Opção válida selecionada no segundo menu: {escolha}')
            return True
        else:
            logging.warning(f"Opção inválida selecionada: {escolha}")
            return False

    async def capturar_mensagens_existentes(self, page, telefone):
        if telefone not in self.mensagens_processadas_por_usuario:
            self.mensagens_processadas_por_usuario[telefone] = set()
        mensagens_processadas = self.mensagens_processadas_por_usuario[telefone]

        # Capturar todas as mensagens recebidas na conversa atual e armazenar no cache
        mensagens = await page.query_selector_all('div.message-in')
        self.mensagens_cache[telefone] = mensagens
        for mensagem in mensagens:
            copyable_text_div = await mensagem.query_selector('div.copyable-text')
            if copyable_text_div:
                data_pre_plain_text = await copyable_text_div.get_attribute('data-pre-plain-text')
                texto_mensagem_element = await copyable_text_div.query_selector('span.selectable-text.copyable-text span')
                if texto_mensagem_element:
                    texto_mensagem = await texto_mensagem_element.inner_text()
                    mensagem_id = f"{data_pre_plain_text}_{texto_mensagem.strip()}"
                    mensagens_processadas.add((texto_mensagem.strip(), datetime.datetime.now()))
                    logging.debug(f"Mensagem existente adicionada ao histórico: '{texto_mensagem.strip()}' (ID: {mensagem_id})")

    def extrair_timestamp(self, data_pre_plain_text):
        try:
            # Extrair a parte entre colchetes usando expressão regular
            match = re.search(r'\[(.*?)\]', data_pre_plain_text)
            if match:
                data_hora_str = match.group(1)
                # Formato esperado: 'hora:minuto, dia/mês/ano'
                data_hora = datetime.datetime.strptime(data_hora_str, '%H:%M, %d/%m/%Y')
                return data_hora
            else:
                raise ValueError("Formato de data/hora não encontrado.")
        except Exception as e:
            logging.error(f"Erro ao extrair timestamp: {e}")
            # Retorna um timestamp atual como fallback
            return datetime.datetime.now()

    async def aguardar_resposta(self, page, telefone, menu_atual=1, validar_opcao=True):
        if telefone not in self.mensagens_processadas_por_usuario:
            self.mensagens_processadas_por_usuario[telefone] = set()
        mensagens_processadas = self.mensagens_processadas_por_usuario[telefone]

        # Obter a posição da última mensagem processada
        if telefone not in self.mensagens_cache:
            self.mensagens_cache[telefone] = await page.query_selector_all('div.message-in')
        posicao_inicial = self.posicao_ultima_mensagem.get(telefone, len(self.mensagens_cache[telefone]))

        # Obter o horário de envio do menu correspondente
        if menu_atual == 1:
            horario_menu = self.horario_envio_menu1.get(telefone)
        elif menu_atual == 2:
            horario_menu = self.horario_envio_menu2.get(telefone)
        else:
            horario_menu = None

        if not horario_menu:
            logging.warning(f"Horário de envio do menu {menu_atual} não encontrado para {telefone}.")
            horario_menu = datetime.datetime.now()

        logging.debug(f"Aguardando resposta do usuário {telefone} para o menu {menu_atual}.")
        while True:
            mensagens = await page.query_selector_all('div.message-in')
            self.mensagens_cache[telefone] = mensagens
            novas_mensagens = mensagens[posicao_inicial:]
            logging.debug(f"{len(novas_mensagens)} novas mensagens encontradas.")
            for mensagem in novas_mensagens:
                copyable_text_div = await mensagem.query_selector('div.copyable-text')
                if copyable_text_div:
                    data_pre_plain_text = await copyable_text_div.get_attribute('data-pre-plain-text')
                    texto_mensagem_element = await copyable_text_div.query_selector('span.selectable-text.copyable-text span')
                    if texto_mensagem_element:
                        texto_mensagem = await texto_mensagem_element.inner_text()
                        mensagem_id = f"{data_pre_plain_text}_{texto_mensagem.strip()}"
                        if (texto_mensagem.strip(), datetime.datetime.now()) not in mensagens_processadas:
                            mensagens_processadas.add(mensagem_id)
                            # Extrair o timestamp da mensagem
                            timestamp_mensagem = datetime.datetime.now()
                            if timestamp_mensagem > horario_menu:
                                logging.info(f"Nova mensagem recebida de {telefone}: '{texto_mensagem.strip()}' (ID: {mensagem_id})")
                                logging.debug(f"Processando mensagem: '{texto_mensagem.strip()}'")
                                # Validar a mensagem recebida se necessário
                                if validar_opcao and self.validar_opcao(texto_mensagem.strip(), menu_atual):
                                    logging.debug(f"Mensagem válida recebida: '{texto_mensagem.strip()}'")
                                    # Atualizar a posição inicial para a próxima mensagem
                                    posicao_inicial += 1
                                    self.posicao_ultima_mensagem[telefone] = posicao_inicial
                                    return texto_mensagem.strip()
                                elif not validar_opcao:
                                    return texto_mensagem.strip()
                                else:
                                    logging.debug(f"Mensagem inválida recebida: '{texto_mensagem.strip()}'")
                                    await self.enviar_mensagem(page, "Opção inválida. Por favor, tente novamente.")
                                    await asyncio.sleep(1)  # Use a menor duração do sleep para melhorar a responsividade
                                    break
                            else:
                                logging.debug(f"Ignorando mensagem antiga de {telefone}: '{texto_mensagem.strip()}' (Horário: {timestamp_mensagem})")
                        else:
                            logging.debug(f"Mensagem já processada: '{texto_mensagem.strip()}' (ID: {mensagem_id})")
            await asyncio.sleep(1)  # Use a menor duração do sleep para melhorar a responsividade

    async def enviar_mensagem(self, page, mensagem, telefone=None, menu_numero=None):
        """Envia uma mensagem ao usuário e registra o horário se for um menu."""
        logging.debug(f"Enviando mensagem para o usuário: '{mensagem}'")
        caixa_de_texto = page.locator('div[contenteditable="true"][aria-label="Mensagem"], div[contenteditable="true"][data-tab="10"]')
        await caixa_de_texto.click()
        await caixa_de_texto.type(mensagem)
        await page.keyboard.press('Enter')

        # Registrar o horário se for um menu
        if telefone and menu_numero:
            agora = datetime.datetime.now()
            if menu_numero == 1:
                self.horario_envio_menu1[telefone] = agora
                logging.debug(f"Horário de envio do Menu 1 para {telefone}: {agora}")
            elif menu_numero == 2:
                self.horario_envio_menu2[telefone] = agora
                logging.debug(f"Horário de envio do Menu 2 para {telefone}: {agora}")

    def buscar_informacoes_beneficiado(self, rg):
        try:
            conexao = sqlite3.connect('obra_de_maria.db')
            cursor = conexao.cursor()

            # Buscar beneficiado pelo RG
            cursor.execute("SELECT Nome, Turma FROM beneficiados WHERE RG = ?", (rg,))
            resultado = cursor.fetchone()

            if resultado:
                nome, turma = resultado

                # Buscar semana correspondente à turma
                cursor.execute("SELECT semana FROM turmas WHERE turma = ?", (turma,))
                resultado_turma = cursor.fetchone()

                if resultado_turma:
                    semana = resultado_turma[0]
                    return f"{nome}, você deve comparecer na semana {semana} ao evento."
                else:
                    return "Turma não encontrada. Por favor, entre em contato com o suporte."
            else:
                return "Beneficiado não encontrado. Por favor, verifique o RG informado."

        except sqlite3.Error as e:
            logging.error(f"Erro ao acessar o banco de dados: {e}")
            return "Erro ao acessar o banco de dados. Por favor, tente novamente mais tarde."
        finally:
            if conexao:
                conexao.close()

    async def aguardar_resposta_rg(self, page, telefone):
        rg = await self.aguardar_resposta(page, telefone, menu_atual=2, validar_opcao=False)
        mensagem_resposta = self.buscar_informacoes_beneficiado(rg)
        await self.enviar_mensagem(page, mensagem_resposta)
