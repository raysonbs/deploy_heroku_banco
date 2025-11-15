import streamlit as st
import pandas as pd
import os
import tempfile
import requests
from sqlalchemy import create_engine
import time
import shutil
import datetime

# --- Configurações Globais ---
# Define o tempo de vida do cache para os dados da API em minutos
API_REFRESH_INTERVAL_MINUTES = 20
CACHE_DURATION_SECONDS = API_REFRESH_INTERVAL_MINUTES * 60

# --- Configurações Específicas da Página ---
# Nome da tabela do banco de dados para esta página
DB_TABLE_NAME = 'ligas_ativas_total'
# Prefixo para as chaves do session_state desta página, para evitar conflitos
PAGE_SESSION_STATE_PREFIX = f"{DB_TABLE_NAME}_"

# --- Lista para coletar mensagens da aplicação ---
# Isso permite exibir todas as mensagens no final, após o conteúdo principal.
if 'app_messages' not in st.session_state:
    st.session_state['app_messages'] = []

# Função auxiliar para adicionar mensagens à lista global
def add_app_message(type, message):
    st.session_state['app_messages'].append({'type': type, 'message': message})

# --- Gerenciamento do Certificado SSL ---
def download_and_store_certificate():
    """
    Baixa o certificado SSL se ainda não estiver baixado e armazenado
    em st.session_state. Retorna o caminho para o arquivo do certificado.
    Esta função mantém as chaves 'cert_path' e 'cert_temp_dir' sem prefixo,
    assumindo que o certificado é um recurso compartilhado para conexão
    ao banco de dados em todo o aplicativo.
    """
    if 'cert_path' not in st.session_state or st.session_state.cert_path is None or \
       (st.session_state.cert_path and not os.path.exists(st.session_state.cert_path)):
        
        add_app_message("info", "Baixando certificado SSL...") # Adiciona à lista
        url = os.getenv('url') # Variável de ambiente para a URL do certificado

        if not url:
            add_app_message("error", "A variável de ambiente 'url' não está definida. Exemplo: url='https://seusite.com/cert.crt'") # Adiciona à lista
            return None

        try:
            response = requests.get(url, timeout=10) # Adiciona um timeout para a requisição
            response.raise_for_status() # Verifica se a requisição foi bem-sucedida

            # Cria um diretório temporário para armazenar o certificado
            temp_dir = tempfile.mkdtemp()
            cert_file_name = "certificado.crt"
            cert_full_path = os.path.join(temp_dir, cert_file_name)

            # Salva o conteúdo do certificado no arquivo temporário
            with open(cert_full_path, 'wb') as cert_file:
                cert_file.write(response.content)
            
            st.session_state.cert_path = cert_full_path
            st.session_state.cert_temp_dir = temp_dir # Armazena o diretório temporário para possível limpeza
            add_app_message("success", "Certificado baixado e armazenado com sucesso!") # Adiciona à lista
            return cert_full_path

        except requests.exceptions.RequestException as e:
            add_app_message("error", f"Erro ao baixar o certificado: {e}. Verifique a URL e sua conexão.") # Adiciona à lista
            return None
        except Exception as e:
            add_app_message("error", f"Erro inesperado no download do certificado: {e}") # Adiciona à lista
            return None
    else:
        return st.session_state.cert_path

# --- Função de Carregamento de Dados do Banco ---
def load_data():
    """
    Carrega os dados do banco de dados MySQL usando o certificado SSL,
    da tabela especificada por DB_TABLE_NAME.
    Retorna um DataFrame pandas ou None em caso de erro.
    """
    # Garante que o certificado seja baixado e seu caminho seja obtido
    cert_path_for_db = download_and_store_certificate()
    if cert_path_for_db is None:
        add_app_message("error", "Não foi possível obter o certificado SSL necessário para a conexão com o banco de dados.") # Adiciona à lista
        return None

    # Informações de conexão (obtidas de variáveis de ambiente)
    username = os.getenv('username')
    password = os.getenv('password')
    host = os.getenv('host')
    port = os.getenv('port')
    database = os.getenv('database')

    # Verifica se todas as variáveis de ambiente necessárias estão definidas
    if not all([username, password, host, port, database]):
        add_app_message("error", "Variáveis de ambiente para conexão com o banco de dados incompletas (username, password, host, port, database).") # Adiciona à lista
        return None
    
    # Converte a porta para inteiro
    try:
        port = int(port)
    except (ValueError, TypeError):
        add_app_message("error", f"A porta do banco de dados '{port}' não é um número válido.") # Adiciona à lista
        return None

    # Configurações SSL para SQLAlchemy
    ssl_args = {
        'ssl': {
            'ca': cert_path_for_db
        }
    }
    
    try:
        # Cria a engine de conexão com o banco de dados
        engine = create_engine(
            f'mysql+pymysql://{username}:{password}@{host}:{port}/{database}',
            connect_args=ssl_args
        )
        
        # Carrega os dados da tabela para um DataFrame (alterado para DB_TABLE_NAME)
        with engine.connect() as connection:
            df = pd.read_sql_table(DB_TABLE_NAME, con=connection)
        
        add_app_message("success", f"Dados carregados da tabela '{DB_TABLE_NAME}' com sucesso!") # Adiciona à lista
        return df
    
    except Exception as e:
        add_app_message("error", f"Erro ao conectar ou carregar dados do banco de dados da tabela '{DB_TABLE_NAME}': {e}") # Adiciona à lista
        return None

# --- Configuração da Página Streamlit ---
st.set_page_config(layout="wide")
st.title(f"Diagnóstico de Jogos: {DB_TABLE_NAME.replace('_', ' ')} ��")
st.write(f"Dados da tabela `{DB_TABLE_NAME}` filtrados com cache de sessão por **{API_REFRESH_INTERVAL_MINUTES} minutos** para otimização.") # Esta mensagem é intencionalmente exibida no topo

# --- CSS Personalizado para os Cartões ---
st.markdown(
    """
    <style>
    .metric-card {
        background-color: #ffffff; /* Fundo branco */
        border-radius: 10px; /* Bordas arredondadas */
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1); /* Sombra suave */
        padding: 20px; /* Espaçamento interno */
        margin-bottom: 20px; /* Margem inferior para separar cartões */
        border: 1px solid #e6e6e6; /* Borda sutil */
        text-align: center; /* Centraliza o texto dentro do cartão */
        height: 100%; /* Garante que o cartão ocupe a altura total da coluna */
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
    }
    .metric-card h3 { /* Título principal do cartão, se usado */
        font-size: 1.3em;
        color: #333333;
        margin-bottom: 10px;
        font-weight: bold;
    }
    .card-title-text { /* Novo estilo para títulos de texto específicos que você pode adicionar */
        font-size: 1.1em;
        color: #555555;
        margin-bottom: 5px;
        font-weight: normal;
    }

    /* Estilos para os componentes st.metric dentro dos cartões */
    /* ATENÇÃO: As classes com 'st-emotion-cache' são geradas dinamicamente pelo Streamlit
       e podem mudar em versões futuras. Verifique sempre no navegador (F12) se necessário. */
    .st-emotion-cache-1r6dm7m { /* Container geral da métrica */
        width: 100%;
    }
    .st-emotion-cache-1r6dm7m p { /* Valor da métrica */
        font-size: 1.8em; /* Aumentado para maior destaque */
        font-weight: bold;
        color: #007bff; /* Cor para os valores das métricas */
        margin: 0; /* Remove margem padrão */
    }
    .st-emotion-cache-1r6dm7m small { /* Label da métrica */
        font-size: 0.9em; /* Tamanho da fonte do label */
        color: #777777; /* Cor mais suave para o label */
        margin-top: 5px;
    }
    
    /* Ajuste para as colunas Streamlit para que os cards fiquem alinhados */
    .st-emotion-cache-ocqbe5 { /* Esta classe pode variar. Inspecione o elemento para confirmar */
        display: flex;
        flex-direction: column;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --- Inicialização das Variáveis de Estado da Sessão (com prefixo) ---
if f"{PAGE_SESSION_STATE_PREFIX}last_loaded" not in st.session_state:
    st.session_state[f"{PAGE_SESSION_STATE_PREFIX}last_loaded"] = 0  # Timestamp da última carga de dados (Unix timestamp)
if f"{PAGE_SESSION_STATE_PREFIX}data" not in st.session_state:
    st.session_state[f"{PAGE_SESSION_STATE_PREFIX}data"] = None # DataFrame principal (para esta página)

# --- Lógica de Caching de Dados (usando chaves prefixadas) ---
current_df_page_specific = None # Esta variável local irá segurar o DataFrame para o rerun atual

# Verifica se os dados precisam ser carregados/recarregados
cache_expired = (time.time() - st.session_state[f"{PAGE_SESSION_STATE_PREFIX}last_loaded"]) > CACHE_DURATION_SECONDS

if st.session_state[f"{PAGE_SESSION_STATE_PREFIX}data"] is None or cache_expired:
    
    if st.session_state[f"{PAGE_SESSION_STATE_PREFIX}data"] is None:
        add_app_message("info", f"Primeiro carregamento dos dados da sessão para '{DB_TABLE_NAME}' ou dados não encontrados no cache.") # Adiciona à lista
    elif cache_expired:
        add_app_message("warning", f"Cache de dados para '{DB_TABLE_NAME}' expirado (última carga há {int(time.time() - st.session_state[f'{PAGE_SESSION_STATE_PREFIX}last_loaded'])} segundos). Recarregando dados...") # Adiciona à lista
    
    temp_df = load_data() 
    
    if temp_df is not None:
        st.session_state[f"{PAGE_SESSION_STATE_PREFIX}data"] = temp_df
        st.session_state[f"{PAGE_SESSION_STATE_PREFIX}last_loaded"] = time.time() # Atualiza o timestamp na carga bem-sucedida
        current_df_page_specific = temp_df # Atribui ao local para este rerun
        add_app_message("success", f"Dados da tabela '{DB_TABLE_NAME}' carregados e atualizados no cache da sessão.") # Adiciona à lista
    else:
        add_app_message("error", f"Falha crítica ao carregar dados da tabela '{DB_TABLE_NAME}'. Por favor, verifique as mensagens de erro acima e as variáveis de ambiente.") # Adiciona à lista
        current_df_page_specific = None # Garante que o local seja None se a carga falhou
else:
    # Os dados já estão no session_state e não expiraram
    time_since_last_load = int(time.time() - st.session_state[f'{PAGE_SESSION_STATE_PREFIX}last_loaded'])
    add_app_message("info", f"Usando dados em cache da sessão para '{DB_TABLE_NAME}' (última carga há {time_since_last_load} segundos).") # Adiciona à lista
    current_df_page_specific = st.session_state[f"{PAGE_SESSION_STATE_PREFIX}data"] # Atribui do cache ao local

# --- Exibição dos Dados no Streamlit ---
if current_df_page_specific is not None:
    st.subheader(f"Dados de '{DB_TABLE_NAME}' Carregados:")
    st.dataframe(current_df_page_specific, use_container_width=True)
else:
    add_app_message("warning", f"Nenhum dado da tabela '{DB_TABLE_NAME}' disponível para exibição. Verifique as mensagens de erro e carregamento acima.") # Adiciona à lista

st.markdown("---") # Separador visual simples

# --- Seção de Métricas em Cartão ---
st.subheader("📊 Resumo das Métricas")

col1, col2, col3 = st.columns(3)

if current_df_page_specific is not None:
    # Verifica se a coluna 'Temporada' existe no DataFrame (observação: usei 'Temporada' capitalizado)
    if 'Temporada' in current_df_page_specific.columns: 
        # Mantendo filtro como string "2025" e "2026"
        count_2025 = current_df_page_specific[current_df_page_specific['Temporada'] == "2025"].shape[0]
        count_2026 = current_df_page_specific[current_df_page_specific['Temporada'] == "2026"].shape[0]

        with col1:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            # st.markdown('<p class="card-title-text">Registros por Ano</p>', unsafe_allow_html=True) 
            st.metric(label="Ligas da Temporada 2025", value=count_2025)
            st.markdown('</div>', unsafe_allow_html=True)
        with col2:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            # st.markdown('<p class="card-title-text">Registros por Ano</p>', unsafe_allow_html=True) 
            st.metric(label="Ligas da Temporada 2026", value=count_2026)
            st.markdown('</div>', unsafe_allow_html=True)
    else:
        with col1:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            # st.markdown('<p class="card-title-text">Registros por Ano</p>', unsafe_allow_html=True)
            st.metric(label="T. 2025", value="N/A")
            st.caption("Coluna 'Temporada' não encontrada.")
            st.markdown('</div>', unsafe_allow_html=True)
        with col2:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            # st.markdown('<p class="card-title-text">Registros por Ano</p>', unsafe_allow_html=True)
            st.metric(label="T. 2026", value="N/A")
            st.caption("Coluna 'Temporada' não encontrada.")
            st.markdown('</div>', unsafe_allow_html=True)
            
    with col3:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        # st.markdown('<p class="card-title-text">Visão Geral do DataFrame</p>', unsafe_allow_html=True)
        st.metric(label="Total de ligas ativas", value=current_df_page_specific.shape[0])
        st.markdown('</div>', unsafe_allow_html=True)

else:
    # Se o DataFrame não estiver disponível, exibir cartões com "N/A"
    with col1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.markdown('<p class="card-title-text">Registros por Ano</p>', unsafe_allow_html=True)
        st.metric(label="T. 2025", value="N/A")
        st.caption("Dados não disponíveis.")
        st.markdown('</div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.markdown('<p class="card-title-text">Registros por Ano</p>', unsafe_allow_html=True)
        st.metric(label="T. 2026", value="N/A")
        st.caption("Dados não disponíveis.")
        st.markdown('</div>', unsafe_allow_html=True)
    with col3:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.markdown('<p class="card-title-text">Visão Geral do DataFrame</p>', unsafe_allow_html=True)
        st.metric(label="Total Registros", value="N/A")
        st.caption("Dados não disponíveis.")
        st.markdown('</div>', unsafe_allow_html=True)
            
st.markdown("---") # Separador visual simples

# --- Seção do Contador Decrescente (Mantida no local, pois é um componente visual) ---
st.subheader("⏳ Status da Sessão de Dados para esta Página") # Título mais específico

if st.session_state[f"{PAGE_SESSION_STATE_PREFIX}last_loaded"] > 0 and current_df_page_specific is not None:
    last_loaded_timestamp = st.session_state[f"{PAGE_SESSION_STATE_PREFIX}last_loaded"]
    expiration_timestamp = last_loaded_timestamp + CACHE_DURATION_SECONDS
    current_time = time.time()
    remaining_seconds = expiration_timestamp - current_time

    if remaining_seconds > 0:
        minutes = int(remaining_seconds // 60)
        seconds = int(remaining_seconds % 60)
        st.metric(label=f"Próxima atualização automática da tabela '{DB_TABLE_NAME}' em aproximadamente", value=f"{minutes:02d}m {seconds:02}s")
        st.caption(
            f"Os dados da tabela '{DB_TABLE_NAME}' foram carregados pela última vez em: "
            f"**{datetime.datetime.fromtimestamp(last_loaded_timestamp).strftime('%d/%m/%Y %H:%M:%S')}**."
            f" O contador atualiza a cada interação ou recarregamento da página."
        )
    else:
        add_app_message("warning", f"O cache dos dados da tabela '{DB_TABLE_NAME}' expirou. Os dados serão atualizados na próxima interação ou recarregamento da página.") # Adiciona à lista
else:
    st.info(f"O contador do cache para '{DB_TABLE_NAME}' será iniciado após o primeiro carregamento bem-sucedido dos dados.") # Esta mensagem é intencional e pode aparecer antes do log, informando sobre o cache.

if st.button(f"Forçar Recarregamento dos Dados da Tabela '{DB_TABLE_NAME}' (Limpar Cache) 🔄"):
    add_app_message("info", f"Forçando a limpeza do cache de dados para '{DB_TABLE_NAME}' e recarregamento...") # Adiciona à lista
    
    if f"{PAGE_SESSION_STATE_PREFIX}data" in st.session_state:
        del st.session_state[f"{PAGE_SESSION_STATE_PREFIX}data"]
    if f"{PAGE_SESSION_STATE_PREFIX}last_loaded" in st.session_state:
        del st.session_state[f"{PAGE_SESSION_STATE_PREFIX}last_loaded"]
        
    if 'cert_temp_dir' in st.session_state and st.session_state.cert_temp_dir and os.path.exists(st.session_state.cert_temp_dir):
        try:
            shutil.rmtree(st.session_state.cert_temp_dir)
            add_app_message("info", f"Diretório temporário do certificado '{st.session_state.cert_temp_dir}' limpo.") # Adiciona à lista
        except Exception as e:
            add_app_message("warning", f"Não foi possível limpar o diretório temporário do certificado: {e}") # Adiciona à lista
        st.session_state.cert_path = None
        st.session_state.cert_temp_dir = None
        
    st.rerun()

# --- Exibir todas as mensagens coletadas no final da página ---
st.markdown("---")
st.subheader("Log de Mensagens da Aplicação:")
if st.session_state['app_messages']: # Só mostra o log se houver mensagens
    for msg in st.session_state['app_messages']:
        if msg['type'] == "info":
            st.info(msg['message'])
        elif msg['type'] == "warning":
            st.warning(msg['message'])
        elif msg['type'] == "success":
            st.success(msg['message'])
        elif msg['type'] == "error":
            st.error(msg['message'])
else:
    st.info("Nenhuma mensagem de log para exibir no momento.")

# Limpa as mensagens após a exibição para que não se acumulem em reruns (opcional, pode remover se quiser histórico)
st.session_state['app_messages'] = []