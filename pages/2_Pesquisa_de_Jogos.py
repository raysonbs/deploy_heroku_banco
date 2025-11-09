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
        # Usando 'url' como a variável de ambiente para a URL do certificado, conforme o cenário.
        url = os.getenv('url') 

        if not url:
            st.error("A variável de ambiente 'url' (para o certificado) não está definida.")
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
    # Corrigido para usar os nomes de variáveis de ambiente originais, conforme o cenário.
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
# As chaves 'cert_path' e 'cert_temp_dir' são mantidas sem prefixo.

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
        # CONVERSÃO PARA DATA AQUI: Garante que 'data_sem_fuso' seja tipo date para filtros
        if 'data_sem_fuso' in temp_df.columns:
            temp_df['data_sem_fuso'] = pd.to_datetime(temp_df['data_sem_fuso'], errors='coerce').dt.date
            # Remover linhas com datas inválidas (NaT) se desejar, ou deixá-las para serem ignoradas no filtro
            # temp_df.dropna(subset=['data_sem_fuso'], inplace=True)
            
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

# --- Aplicação de Filtros e Exibição dos Dados no Streamlit ---
if current_df_page_specific is not None:
    st.subheader("Configurações de Filtro")

    # Criar uma cópia do DataFrame para aplicar os filtros
    # Isso evita modificar o DataFrame original no session_state diretamente
    filtered_df = current_df_page_specific.copy()

    # --- Filtro de Data ---
    if 'data_sem_fuso' in filtered_df.columns and not filtered_df['data_sem_fuso'].isnull().all():
        min_available_date = filtered_df['data_sem_fuso'].min()
        max_available_date = filtered_df['data_sem_fuso'].max()

        col_date1, col_date2 = st.columns(2)
        with col_date1:
            start_date_filter = st.date_input(
                "Data Inicial",
                value=min_available_date if pd.notna(min_available_date) else datetime.date.today(), # Valor padrão
                min_value=min_available_date if pd.notna(min_available_date) else datetime.date(1900, 1, 1), # Min date do seletor
                max_value=max_available_date if pd.notna(max_available_date) else datetime.date.today()  # Max date do seletor
            )
        with col_date2:
            end_date_filter = st.date_input(
                "Data Final",
                value=max_available_date if pd.notna(max_available_date) else datetime.date.today(), # Valor padrão
                min_value=min_available_date if pd.notna(min_available_date) else datetime.date(1900, 1, 1),
                max_value=max_available_date if pd.notna(max_available_date) else datetime.date.today()
            )
        
        # Aplicar filtro de data
        if start_date_filter and end_date_filter:
            # Garante que as datas de filtro são do tipo date para comparação consistente
            start_date_filter = pd.to_datetime(start_date_filter).date()
            end_date_filter = pd.to_datetime(end_date_filter).date()
            
            filtered_df = filtered_df[
                (filtered_df['data_sem_fuso'] >= start_date_filter) &
                (filtered_df['data_sem_fuso'] <= end_date_filter)
            ]
    else:
        st.warning("Coluna 'data_sem_fuso' não encontrada ou não contém datas válidas para filtrar.")


    # --- Filtro de Times (home_name) ---
    if 'home_name' in filtered_df.columns:
        # Garante que apenas valores únicos e não nulos são usados para as opções
        all_home_teams = sorted(current_df_page_specific['home_name'].dropna().unique().tolist())
        home_teams_options = ["Todos"] + all_home_teams
        selected_home_teams = st.multiselect(
            "Time da Casa",
            options=home_teams_options,
            default=["Todos"] # Por padrão, "Todos" selecionado
        )
        
        # Aplicar filtro de time da casa, a menos que "Todos" esteja selecionado (e seja a única seleção, ou se "Todos" não estiver presente, filtra pelos selecionados)
        if "Todos" not in selected_home_teams and selected_home_teams:
            filtered_df = filtered_df[filtered_df['home_name'].isin(selected_home_teams)]
        elif not selected_home_teams: # Se nada for selecionado e "Todos" não estiver lá, mostrar nada
            filtered_df = filtered_df[filtered_df['home_name'].isin([])] # Filtra para DataFrame vazio
    else:
        st.warning("Coluna 'home_name' não encontrada para filtrar.")


    # --- Filtro de Times (away_name) ---
    if 'away_name' in filtered_df.columns:
        # Garante que apenas valores únicos e não nulos são usados para as opções
        all_away_teams = sorted(current_df_page_specific['away_name'].dropna().unique().tolist())
        away_teams_options = ["Todos"] + all_away_teams
        selected_away_teams = st.multiselect(
            "Time Visitante",
            options=away_teams_options,
            default=["Todos"] # Por padrão, "Todos" selecionado
        )
        
        # Aplicar filtro de time visitante, a menos que "Todos" esteja selecionado
        if "Todos" not in selected_away_teams and selected_away_teams:
            filtered_df = filtered_df[filtered_df['away_name'].isin(selected_away_teams)]
        elif not selected_away_teams: # Se nada for selecionado e "Todos" não estiver lá, mostrar nada
            filtered_df = filtered_df[filtered_df['away_name'].isin([])] # Filtra para DataFrame vazio
    else:
        st.warning("Coluna 'away_name' não encontrada para filtrar.")

    st.subheader(f"Dados Filtrados da Tabela '{DB_TABLE_NAME}':")
    if not filtered_df.empty:
        st.dataframe(filtered_df, use_container_width=True)
        st.write(f"Total de registros filtrados: **{len(filtered_df)}**")
    else:
        st.info("Nenhum dado corresponde aos filtros selecionados.")
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
