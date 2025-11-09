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
DB_TABLE_NAME = 'temporadas_todos_jogos'
# Prefixo para as chaves do session_state desta página, para evitar conflitos
PAGE_SESSION_STATE_PREFIX = f"{DB_TABLE_NAME}_"

# --- Gerenciamento do Certificado SSL ---
def download_and_store_certificate():
    """
    Baixa o certificado SSL se ainda não estiver baixado e armazenado
    em st.session_state. Retorna o caminho para o arquivo do certificado.
    Esta função mantém as chaves 'cert_path' e 'cert_temp_dir' sem prefixo,
    assumindo que o certificado é um recurso compartilhado para conexão
    ao banco de dados em todo o aplicativo.
    """
    # Verifica se o certificado já está no session_state e se o arquivo ainda existe
    if 'cert_path' not in st.session_state or st.session_state.cert_path is None or \
       (st.session_state.cert_path and not os.path.exists(st.session_state.cert_path)):
        
        st.info("Baixando certificado SSL...")
        url = os.getenv('url') # Variável de ambiente para a URL do certificado

        if not url:
            st.error("A variável de ambiente 'URL_DO_CERTIFICADO' não está definida.")
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
            st.success("Certificado baixado e armazenado com sucesso!")
            return cert_full_path

        except requests.exceptions.RequestException as e:
            st.error(f"Erro ao baixar o certificado: {e}. Verifique a URL e sua conexão.")
            return None
        except Exception as e:
            st.error(f"Erro inesperado no download do certificado: {e}")
            return None
    else:
        # Certificado já foi baixado e seu caminho está no session_state
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
        st.error("Não foi possível obter o certificado SSL necessário para a conexão com o banco de dados.")
        return None

    # Informações de conexão (obtidas de variáveis de ambiente)    
    username = os.getenv('username')
    password = os.getenv('password')
    host = os.getenv('host')
    port = os.getenv('port')
    database = os.getenv('database')

    # Verifica se todas as variáveis de ambiente necessárias estão definidas
    if not all([username, password, host, port, database]):
        st.error("Variáveis de ambiente para conexão com o banco de dados incompletas (DB_USERNAME, DB_PASSWORD, DB_HOST, DB_PORT, DB_DATABASE).")
        return None
    
    # Converte a porta para inteiro
    try:
        port = int(port)
    except (ValueError, TypeError):
        st.error(f"A porta do banco de dados '{port}' não é um número válido.")
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
        
        st.success(f"Dados carregados da tabela '{DB_TABLE_NAME}' com sucesso!")
        return df
    
    except Exception as e:
        st.error(f"Erro ao conectar ou carregar dados do banco de dados da tabela '{DB_TABLE_NAME}': {e}")
        return None

# --- Configuração da Página Streamlit ---
st.set_page_config(layout="wide")
st.title(f"Todos os Jogos: {DB_TABLE_NAME.replace('_', ' ')} ⚽")
st.write(f"Dados da tabela `{DB_TABLE_NAME}` com cache de sessão por **{API_REFRESH_INTERVAL_MINUTES} minutos** para otimização.")

# --- Inicialização das Variáveis de Estado da Sessão (com prefixo) ---
if f"{PAGE_SESSION_STATE_PREFIX}last_loaded" not in st.session_state:
    st.session_state[f"{PAGE_SESSION_STATE_PREFIX}last_loaded"] = 0  # Timestamp da última carga de dados (Unix timestamp)
if f"{PAGE_SESSION_STATE_PREFIX}data" not in st.session_state:
    st.session_state[f"{PAGE_SESSION_STATE_PREFIX}data"] = None # DataFrame principal (para esta página)
# As chaves 'cert_path' e 'cert_temp_dir' são mantidas sem prefixo, como discutido.

# --- Lógica de Caching de Dados (usando chaves prefixadas) ---
current_df_page_specific = None # Esta variável local irá segurar o DataFrame para o rerun atual

# Verifica se os dados precisam ser carregados/recarregados
cache_expired = (time.time() - st.session_state[f"{PAGE_SESSION_STATE_PREFIX}last_loaded"]) > CACHE_DURATION_SECONDS

if st.session_state[f"{PAGE_SESSION_STATE_PREFIX}data"] is None or cache_expired:
    
    if st.session_state[f"{PAGE_SESSION_STATE_PREFIX}data"] is None:
        st.info(f"Primeiro carregamento dos dados da sessão para '{DB_TABLE_NAME}' ou dados não encontrados no cache.")
    elif cache_expired:
        st.warning(f"Cache de dados para '{DB_TABLE_NAME}' expirado (última carga há {int(time.time() - st.session_state[f'{PAGE_SESSION_STATE_PREFIX}last_loaded'])} segundos). Recarregando dados...")
    
    # Tenta carregar os dados. load_data() já lida com o certificado.
    temp_df = load_data() 
    
    if temp_df is not None:
        st.session_state[f"{PAGE_SESSION_STATE_PREFIX}data"] = temp_df
        st.session_state[f"{PAGE_SESSION_STATE_PREFIX}last_loaded"] = time.time() # Atualiza o timestamp na carga bem-sucedida
        current_df_page_specific = temp_df # Atribui ao local para este rerun
        st.success(f"Dados da tabela '{DB_TABLE_NAME}' carregados e atualizados no cache da sessão.")
    else:
        st.error(f"Falha crítica ao carregar dados da tabela '{DB_TABLE_NAME}'. Por favor, verifique as mensagens de erro acima e as variáveis de ambiente.")
        current_df_page_specific = None # Garante que o local seja None se a carga falhou
else:
    # Os dados já estão no session_state e não expiraram
    time_since_last_load = int(time.time() - st.session_state[f'{PAGE_SESSION_STATE_PREFIX}last_loaded'])
    st.info(f"Usando dados em cache da sessão para '{DB_TABLE_NAME}' (última carga há {time_since_last_load} segundos).")
    current_df_page_specific = st.session_state[f"{PAGE_SESSION_STATE_PREFIX}data"] # Atribui do cache ao local

# --- Exibição dos Dados no Streamlit ---
if current_df_page_specific is not None:
    st.subheader(f"Dados de '{DB_TABLE_NAME}' Carregados:")
    st.dataframe(current_df_page_specific, use_container_width=True)
else:
    st.warning(f"Nenhum dado da tabela '{DB_TABLE_NAME}' disponível para exibição. Verifique as mensagens de erro e carregamento acima.")

# --- Seção do Contador Decrescente ---
st.markdown("---") # Separador visual simples
st.subheader("📊 Status da Sessão de Dados para esta Página") # Título mais específico

if st.session_state[f"{PAGE_SESSION_STATE_PREFIX}last_loaded"] > 0 and current_df_page_specific is not None:
    # Calcula quando o cache irá expirar (Unix timestamp)
    last_loaded_timestamp = st.session_state[f"{PAGE_SESSION_STATE_PREFIX}last_loaded"]
    expiration_timestamp = last_loaded_timestamp + CACHE_DURATION_SECONDS

    # Calcula o tempo restante
    current_time = time.time()
    remaining_seconds = expiration_timestamp - current_time

    if remaining_seconds > 0:
        # Converte segundos para minutos e segundos para exibição
        minutes = int(remaining_seconds // 60)
        seconds = int(remaining_seconds % 60)
        
        # Exibe o tempo restante usando st.metric para um visual agradável
        st.metric(label=f"Próxima atualização automática da tabela '{DB_TABLE_NAME}' em aproximadamente", value=f"{minutes:02d}m {seconds:02}s")
        st.caption(
            f"Os dados da tabela '{DB_TABLE_NAME}' foram carregados pela última vez em: "
            f"**{datetime.datetime.fromtimestamp(last_loaded_timestamp).strftime('%d/%m/%Y %H:%M:%S')}**."
            f" O contador atualiza a cada interação ou recarregamento da página."
        )
    else:
        st.warning(f"O cache dos dados da tabela '{DB_TABLE_NAME}' expirou. Os dados serão atualizados na próxima interação ou recarregamento da página.")
else:
    st.info(f"O contador do cache para '{DB_TABLE_NAME}' será iniciado após o primeiro carregamento bem-sucedido dos dados.")

if st.button(f"Forçar Recarregamento dos Dados da Tabela '{DB_TABLE_NAME}' (Limpar Cache) 🔄"):
    st.info(f"Forçando a limpeza do cache de dados para '{DB_TABLE_NAME}' e recarregamento...")
    
    # Limpa as entradas de dados do cache específicas desta página
    if f"{PAGE_SESSION_STATE_PREFIX}data" in st.session_state:
        del st.session_state[f"{PAGE_SESSION_STATE_PREFIX}data"]
    if f"{PAGE_SESSION_STATE_PREFIX}last_loaded" in st.session_state:
        del st.session_state[f"{PAGE_SESSION_STATE_PREFIX}last_loaded"]
        
    # Limpeza do certificado permanece como antes, pois é um recurso mais global.
    if 'cert_temp_dir' in st.session_state and st.session_state.cert_temp_dir and os.path.exists(st.session_state.cert_temp_dir):
        try:
            shutil.rmtree(st.session_state.cert_temp_dir)
            st.info(f"Diretório temporário do certificado '{st.session_state.cert_temp_dir}' limpo.")
        except Exception as e:
            st.warning(f"Não foi possível limpar o diretório temporário do certificado: {e}")
        st.session_state.cert_path = None
        st.session_state.cert_temp_dir = None
        
    st.rerun() # Dispara um rerun para que a lógica de carregamento seja reavaliada imediatamente