import streamlit as st
import pandas as pd
import os
import tempfile
import requests
from sqlalchemy import create_engine
import time
import shutil
import datetime # Importado para cálculos com tempo

# --- Configurações Globais ---
# Define o tempo de vida do cache para os dados da API em minutos
API_REFRESH_INTERVAL_MINUTES = 20
CACHE_DURATION_SECONDS = API_REFRESH_INTERVAL_MINUTES * 60

# --- Gerenciamento do Certificado SSL ---
def download_and_store_certificate():
    """
    Baixa o certificado SSL se ainda não estiver baixado e armazenado
    em st.session_state. Retorna o caminho para o arquivo do certificado.
    """
    # Verifica se o certificado já está no session_state e se o arquivo ainda existe
    # e se o caminho não está vazio (para evitar erro com None ou string vazia)
    if 'cert_path' not in st.session_state or st.session_state.cert_path is None or \
       (st.session_state.cert_path and not os.path.exists(st.session_state.cert_path)):
        
        st.info("Baixando certificado SSL...")
        url = os.getenv('url')

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
    Carrega os dados do banco de dados MySQL usando o certificado SSL.
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
        st.error("Variáveis de ambiente para conexão com o banco de dados incompletas (username, password, host, port, database).")
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
        
        # Carrega os dados da tabela para um DataFrame
        with engine.connect() as connection:
            df_jogos = pd.read_sql_table('temporadas_jogos_filtrados_2026', con=connection)
        
        st.success("Dados carregados do banco de dados com sucesso!")
        return df_jogos
    
    except Exception as e:
        st.error(f"Erro ao conectar ou carregar dados do banco de dados: {e}")
        return None

# --- Configuração da Página Streamlit ---
st.set_page_config(layout="wide")
st.title("App de Análise de Jogos ⚽")
st.write(f"Dados de jogos filtrados com cache de sessão por **{API_REFRESH_INTERVAL_MINUTES} minutos** para otimização.")

# --- Inicialização das Variáveis de Estado da Sessão ---
# Estas variáveis persistem entre os reruns e as navegações de página
if "last_loaded" not in st.session_state:
    st.session_state["last_loaded"] = 0  # Timestamp da última carga de dados (Unix timestamp)
if "data_jogos_selecionados" not in st.session_state:
    st.session_state["data_jogos_selecionados"] = None # DataFrame principal
if "cert_path" not in st.session_state:
    st.session_state["cert_path"] = None # Caminho para o certificado baixado
if "cert_temp_dir" not in st.session_state:
    st.session_state["cert_temp_dir"] = None # Diretório temporário do certificado para limpeza

# --- Lógica de Caching de Dados ---
current_df_jogos_selecionados = None # Esta variável local irá segurar o DataFrame para o rerun atual

# Verifica se os dados precisam ser carregados/recarregados
cache_expired = (time.time() - st.session_state["last_loaded"]) > CACHE_DURATION_SECONDS

if st.session_state["data_jogos_selecionados"] is None or cache_expired:
    
    if st.session_state["data_jogos_selecionados"] is None:
        st.info("Primeiro carregamento dos dados da sessão ou dados não encontrados no cache.")
    elif cache_expired:
        st.warning(f"Cache de dados expirado (última carga há {int(time.time() - st.session_state['last_loaded'])} segundos). Recarregando dados...")
    
    # Tenta carregar os dados. load_data() já lida com o certificado.
    temp_df = load_data() 
    
    if temp_df is not None:
        st.session_state["data_jogos_selecionados"] = temp_df
        st.session_state["last_loaded"] = time.time() # Atualiza o timestamp na carga bem-sucedida
        current_df_jogos_selecionados = temp_df # Atribui ao local para este rerun
        st.success("Dados carregados e atualizados no cache da sessão.")
    else:
        st.error("Falha crítica ao carregar dados do banco de dados. Por favor, verifique as mensagens de erro acima e as variáveis de ambiente.")
        current_df_jogos_selecionados = None # Garante que o local seja None se a carga falhou
else:
    # Os dados já estão no session_state e não expiraram
    time_since_last_load = int(time.time() - st.session_state['last_loaded'])
    st.info(f"Usando dados em cache da sessão (última carga há {time_since_last_load} segundos).")
    current_df_jogos_selecionados = st.session_state["data_jogos_selecionados"] # Atribui do cache ao local

# --- Exibição dos Dados no Streamlit ---
if current_df_jogos_selecionados is not None:
    st.subheader("Dados de Jogos Carregados:")
    # Exibe o DataFrame completo sem checagem de colunas
    st.dataframe(current_df_jogos_selecionados, use_container_width=True)
else:
    st.warning("Nenhum dado de jogos disponível para exibição. Verifique as mensagens de erro e carregamento acima.")

# --- Seção do Contador Decrescente ---
st.markdown("---") # Separador visual simples
st.subheader("📊 Status da Sessão de Dados") # Título mais genérico

if st.session_state["last_loaded"] > 0 and current_df_jogos_selecionados is not None:
    # Calcula quando o cache irá expirar (Unix timestamp)
    last_loaded_timestamp = st.session_state["last_loaded"]
    expiration_timestamp = last_loaded_timestamp + CACHE_DURATION_SECONDS

    # Calcula o tempo restante
    current_time = time.time()
    remaining_seconds = expiration_timestamp - current_time

    if remaining_seconds > 0:
        # Converte segundos para minutos e segundos para exibição
        minutes = int(remaining_seconds // 60)
        seconds = int(remaining_seconds % 60)
        
        # Exibe o tempo restante usando st.metric para um visual agradável
        st.metric(label=f"Próxima atualização automática em aproximadamente", value=f"{minutes:02d}m {seconds:02d}s")
        st.caption(
            f"Os dados foram carregados pela última vez em: "
            f"**{datetime.datetime.fromtimestamp(last_loaded_timestamp).strftime('%d/%m/%Y %H:%M:%S')}**."
            f" O contador atualiza a cada interação ou recarregamento da página."
        )
    else:
        st.warning("O cache dos dados expirou. Os dados serão atualizados na próxima interação ou recarregamento da página.")
else:
    st.info("O contador do cache será iniciado após o primeiro carregamento bem-sucedido dos dados.")

if st.button("Forçar Recarregamento dos Dados (Limpar Cache) 🔄"):
    st.info("Forçando a limpeza do cache de dados e recarregamento...")
    
    # Limpa as entradas de dados do cache
    if 'data_jogos_selecionados' in st.session_state:
        del st.session_state['data_jogos_selecionados']
    if 'last_loaded' in st.session_state:
        del st.session_state['last_loaded']
        
    # Tenta limpar o diretório temporário do certificado
    if st.session_state.cert_temp_dir and os.path.exists(st.session_state.cert_temp_dir):
        try:
            shutil.rmtree(st.session_state.cert_temp_dir)
            st.info(f"Diretório temporário do certificado '{st.session_state.cert_temp_dir}' limpo.")
        except Exception as e:
            st.warning(f"Não foi possível limpar o diretório temporário do certificado: {e}")
        st.session_state.cert_path = None
        st.session_state.cert_temp_dir = None
        
    st.rerun() # Dispara um rerun para que a lógica de carregamento seja reavaliada imediatamente