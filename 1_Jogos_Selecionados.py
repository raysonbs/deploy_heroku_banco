import streamlit as st
import pandas as pd
import os
import tempfile
import requests
from sqlalchemy import create_engine
import time
import shutil # Para limpeza de diretórios temporários

# --- Gerenciamento do Certificado SSL ---
def download_and_store_certificate():
    """
    Baixa o certificado SSL se ainda não estiver baixado e armazenado
    em st.session_state. Retorna o caminho para o arquivo do certificado.
    """
    # Verifica se o certificado já está no session_state e se o arquivo ainda existe
    if 'cert_path' not in st.session_state or st.session_state.cert_path is None or \
       not os.path.exists(st.session_state.cert_path):
        
        st.info("Baixando certificado SSL...")
        url = os.getenv('url')

        if not url:
            st.error("A variável de ambiente 'URL_DO_CERTIFICADO' não está definida.")
            return None

        try:
            response = requests.get(url, timeout=10) # Adiciona um timeout para a requisição
            response.raise_for_status() # Verifica se a requisição foi bem-sucedida

            # Cria um diretório temporário para armazenar o certificado
            # Isso é mais seguro para garantir que o arquivo não será sobrescrito/apagado por outro processo
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
        # Usando 'with engine.connect() as connection:' para gerenciar a conexão
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
st.write("Dados de jogos filtrados com cache de sessão para otimização.")

# --- Inicialização das Variáveis de Estado da Sessão ---
# Estas variáveis persistem entre os reruns e as navegações de página
if "last_loaded" not in st.session_state:
    st.session_state["last_loaded"] = 0  # Timestamp da última carga de dados
if "data_jogos_selecionados" not in st.session_state:
    st.session_state["data_jogos_selecionados"] = None # DataFrame principal
if "cert_path" not in st.session_state:
    st.session_state["cert_path"] = None # Caminho para o certificado baixado
if "cert_temp_dir" not in st.session_state:
    st.session_state["cert_temp_dir"] = None # Diretório temporário do certificado para limpeza

# --- Lógica de Caching de Dados (10 minutos) ---
# Esta variável local irá segurar o DataFrame para o rerun atual
current_df_jogos_selecionados = None

# Verifica se os dados precisam ser carregados/recarregados
cache_expired = (time.time() - st.session_state["last_loaded"]) > 600 # 600 segundos = 10 minutos

if st.session_state["data_jogos_selecionados"] is None or cache_expired:
    
    if st.session_state["data_jogos_selecionados"] is None:
        st.info("Primeiro carregamento dos dados da sessão ou dados não encontrados no cache.")
    elif cache_expired:
        st.warning(f"Cache de dados expirado (última carga há {int(time.time() - st.session_state['last_loaded'])} segundos). Recarregando dados...")
    
    # Tenta carregar os dados. load_data() já lida com o certificado.
    temp_df = load_data() 
    
    if temp_df is not None:
        st.session_state["data_jogos_selecionados"] = temp_df
        st.session_state["last_loaded"] = time.time()
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

# --- Botão para Forçar Recarregamento (Limpar Cache) ---
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

# --- Exibição dos Dados no Streamlit ---
if current_df_jogos_selecionados is not None:
    # Lista de colunas esperadas
    required_cols = [
        'liga_nome','data_horario','odds_ft_over05','home_name','away_name',
        'odds_ft_1','odds_ft_2','método','Media_Gols_F_H','Media_Gols_F_A',
        'CV_Gols_F_H','CV_Gols_F_A','temporadaa'
    ]
    
    # Verifica se todas as colunas esperadas estão presentes no DataFrame carregado
    missing_cols = [col for col in required_cols if col not in current_df_jogos_selecionados.columns]
    
    if not missing_cols:
        # Se todas as colunas existirem, filtra e exibe
        df_filtered_for_display = current_df_jogos_selecionados[required_cols]
        st.subheader("Dados de Jogos Carregados:")
        st.dataframe(df_filtered_for_display, use_container_width=True)
    else:
        # Caso contrário, avisa sobre as colunas ausentes e exibe o DataFrame completo
        st.warning(f"O DataFrame carregado não possui as colunas esperadas: {', '.join(missing_cols)}. Exibindo todas as colunas disponíveis.")
        st.dataframe(current_df_jogos_selecionados, use_container_width=True)
else:
    st.warning("Nenhum dado de jogos disponível para exibição. Verifique as mensagens de erro e carregamento acima.")
