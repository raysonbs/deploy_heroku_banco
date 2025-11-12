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

# Define a duração das mensagens temporárias em segundos
TEMP_MESSAGE_DURATION_SECONDS = 10 

# --- Configurações Específicas da Página ---
# Nome da tabela do banco de dados para esta página
DB_TABLE_NAME = 'temporadas_todos_jogos'
# Prefixo para as chaves do session_state desta página, para evitar conflitos
PAGE_SESSION_STATE_PREFIX = f"{DB_TABLE_NAME}_"

# --- INICIALIZAÇÃO DE TODAS AS VARIÁVEIS DE ESTADO DA SESSÃO ---
# Garante que todas as chaves estejam presentes desde o início do script.
st.session_state.setdefault(f"{PAGE_SESSION_STATE_PREFIX}last_loaded", 0)
st.session_state.setdefault(f"{PAGE_SESSION_STATE_PREFIX}data", None)
st.session_state.setdefault(f"{PAGE_SESSION_STATE_PREFIX}temp_message_display", False)
st.session_state.setdefault(f"{PAGE_SESSION_STATE_PREFIX}temp_message_text", "")
st.session_state.setdefault(f"{PAGE_SESSION_STATE_PREFIX}temp_message_type", "info") # default type
st.session_state.setdefault(f"{PAGE_SESSION_STATE_PREFIX}temp_message_timestamp", 0)

# >> ALTERAÇÃO AQUI: Inicialize current_start_date e current_end_date como None
st.session_state.setdefault(f"{PAGE_SESSION_STATE_PREFIX}current_start_date", None) # Agora inicializa como None
st.session_state.setdefault(f"{PAGE_SESSION_STATE_PREFIX}current_end_date", None)   # Agora inicializa como None

st.session_state.setdefault(f"{PAGE_SESSION_STATE_PREFIX}current_home_teams", ["Todos"])
st.session_state.setdefault(f"{PAGE_SESSION_STATE_PREFIX}current_away_teams", ["Todos"])
st.session_state.setdefault(f"{PAGE_SESSION_STATE_PREFIX}current_liga", ["Todos"])


# --- Helper function to set temporary messages ---
# Define-a AGORA, depois que o session_state está garantido.
def set_temp_message(text, type="info"):
    st.session_state[f"{PAGE_SESSION_STATE_PREFIX}temp_message_display"] = True
    st.session_state[f"{PAGE_SESSION_STATE_PREFIX}temp_message_text"] = text
    st.session_state[f"{PAGE_SESSION_STATE_PREFIX}temp_message_type"] = type
    st.session_state[f"{PAGE_SESSION_STATE_PREFIX}temp_message_timestamp"] = time.time()

# --- Gerenciamento do Certificado SSL ---
def download_and_store_certificate():
    """
    Baixa o certificado SSL se ainda não estiver baixado e armazenado
    em st.session_state. Retorna o caminho para o arquivo do certificado.
    Esta função mantém as chaves 'cert_path' e 'cert_temp_dir' sem prefixo,
    assumindo que o certificado é um recurso compartilhado para conexão
    ao banco de dados em todo o aplicativo.
    """
    # Check if a certificate download is already in progress or completed and valid
    if 'cert_path' not in st.session_state or st.session_state.cert_path is None or \
       (st.session_state.cert_path and not os.path.exists(st.session_state.cert_path)):
        
        # Display temporary info message in the main area
        set_temp_message("Baixando certificado SSL...", "info") # MOVIDO DA BARRA LATERAL

        url = os.getenv('url') 

        if not url:
            st.error("A variável de ambiente 'url' (para o certificado) não está definida.")
            return None

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            temp_dir = tempfile.mkdtemp()
            cert_file_name = "certificado.crt"
            cert_full_path = os.path.join(temp_dir, cert_file_name)

            with open(cert_full_path, 'wb') as cert_file:
                cert_file.write(response.content)
            
            st.session_state.cert_path = cert_full_path
            st.session_state.cert_temp_dir = temp_dir
            # Display temporary success message in the main area
            set_temp_message("Certificado baixado e armazenado com sucesso!", "success") # MOVIDO DA BARRA LATERAL
            return cert_full_path

        except requests.exceptions.RequestException as e:
            st.error(f"Erro ao baixar o certificado: {e}. Verifique a URL e sua conexão.")
            return None
        except Exception as e:
            st.error(f"Erro inesperado no download do certificado: {e}")
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
    cert_path_for_db = download_and_store_certificate()
    if cert_path_for_db is None:
        st.error("Não foi possível obter o certificado SSL necessário para a conexão com o banco de dados.")
        return None

    username = os.getenv('username')
    password = os.getenv('password')
    host = os.getenv('host')
    port = os.getenv('port')
    database = os.getenv('database')

    if not all([username, password, host, port, database]):
        st.error("Variáveis de ambiente para conexão com o banco de dados incompletas (username, password, host, port, database).")
        return None
    
    try:
        port = int(port)
    except (ValueError, TypeError):
        st.error(f"A porta do banco de dados '{port}' não é um número válido.")
        return None

    ssl_args = {
        'ssl': {
            'ca': cert_path_for_db
        }
    }
    
    try:
        engine = create_engine(
            f'mysql+pymysql://{username}:{password}@{host}:{port}/{database}',
            connect_args=ssl_args
        )
        
        with engine.connect() as connection:
            df = pd.read_sql_table(DB_TABLE_NAME, con=connection)
        
        return df
    
    except Exception as e:
        st.error(f"Erro ao conectar ou carregar dados do banco de dados da tabela '{DB_TABLE_NAME}': {e}")
        return None

# --- Configuração da Página Streamlit ---
st.set_page_config(layout="wide")
# st.title(f"Todos os Jogos: {DB_TABLE_NAME.replace('_', ' ')} ⚽")
# st.write(f"Dados da tabela `{DB_TABLE_NAME}` com cache de sessão por **{API_REFRESH_INTERVAL_MINUTES} minutos** para otimização.")

# --- Placeholder para a mensagem temporária geral ---
# Criado antes da lógica principal para garantir que esteja sempre disponível.
temp_message_placeholder = st.empty()

# Lógica para fazer a mensagem temporária desaparecer
if st.session_state[f"{PAGE_SESSION_STATE_PREFIX}temp_message_display"]:
    if time.time() - st.session_state[f"{PAGE_SESSION_STATE_PREFIX}temp_message_timestamp"] < TEMP_MESSAGE_DURATION_SECONDS:
        message_type = st.session_state[f"{PAGE_SESSION_STATE_PREFIX}temp_message_type"]
        message_text = st.session_state[f"{PAGE_SESSION_STATE_PREFIX}temp_message_text"]
        
        if message_type == "success":
            temp_message_placeholder.success(message_text)
        elif message_type == "info":
            temp_message_placeholder.info(message_text)
        elif message_type == "warning":
            temp_message_placeholder.warning(message_text)
        elif message_type == "error":
            temp_message_placeholder.error(message_text)
        else: # Fallback para caso 'type' seja inválido
            temp_message_placeholder.write(message_text)
    else:
        st.session_state[f"{PAGE_SESSION_STATE_PREFIX}temp_message_display"] = False
        st.session_state[f"{PAGE_SESSION_STATE_PREFIX}temp_message_text"] = ""
        temp_message_placeholder.empty() # Limpa o placeholder


# --- Lógica de Caching de Dados (usando chaves prefixadas) ---
current_df_page_specific = None

cache_expired = (time.time() - st.session_state[f"{PAGE_SESSION_STATE_PREFIX}last_loaded"]) > CACHE_DURATION_SECONDS

if st.session_state[f"{PAGE_SESSION_STATE_PREFIX}data"] is None or cache_expired:
    # Ao iniciar ou recarregar dados, assegure que qualquer mensagem temporária anterior seja limpa
    # Isso é redundante com a lógica do placeholder acima, mas garante o estado limpo.
    st.session_state[f"{PAGE_SESSION_STATE_PREFIX}temp_message_display"] = False
    st.session_state[f"{PAGE_SESSION_STATE_PREFIX}temp_message_text"] = ""
    temp_message_placeholder.empty()

    if st.session_state[f"{PAGE_SESSION_STATE_PREFIX}data"] is None:
        # st.info substituído por set_temp_message
        set_temp_message(f"Primeiro carregamento dos dados da sessão para '{DB_TABLE_NAME}' ou dados não encontrados no cache.", "info")
    elif cache_expired:
        st.warning(f"Cache de dados para '{DB_TABLE_NAME}' expirado (última carga há {int(time.time() - st.session_state[f'{PAGE_SESSION_STATE_PREFIX}last_loaded'])} segundos). Recarregando dados...")
    
    temp_df = load_data() # Esta função internamente chama download_and_store_certificate, que já seta mensagens temporárias
    
    if temp_df is not None:
        # Definir o mapeamento de colunas original para novo nome
        colunas_map = {
            'liga_nome': 'liga',
            'data_sem_fuso': 'data_jogo', 
            'home_name': 'home',
            'away_name': 'away',
            'homeGoalCount': 'gols_h',
            'awayGoalCount': 'gols_a',
            'overallGoalCount':'gols_ft',
            'odds_ft_1': 'odds_h',
            'odds_ft_2': 'odds_a',
            'Media_Gols_F_H': 'M_Gols_F_H',
            'Media_Gols_F_A': 'M_Gols_F_A',
            'CV_Gols_F_H': 'CV_G_F_H',
            'CV_Gols_F_A': 'CV_G_F_A',
            'Porc_O_05FT_H': '%0V_05FT_H',
            'Porc_O_05FT_A': '%0V_05FT_A'
            # As entradas para 'nova_coluna_db_1' e 'nova_coluna_db_2' foram removidas daqui.
        }
        
        # Lista dos nomes de colunas que esperamos ter no final, na ordem desejada
        # Assumindo que você já incluiu suas colunas reais aqui.
        final_desired_column_names = [
            'liga', 'data_jogo', 'home', 'away', 'gols_h', 'gols_a','gols_ft',
            'odds_h', 'odds_a', 'M_Gols_F_H', 'M_Gols_F_A', 'CV_G_F_H', 'CV_G_F_A',
            '%0V_05FT_H','%0V_05FT_A'
            # As entradas para 'Nova Coluna 1' e 'Nova Coluna 2' foram removidas daqui.
            # CERTIFIQUE-SE que as suas novas colunas estejam na lista 'final_desired_column_names'
            # se você as adicionou e quer que apareçam.
        ]

        # Aplicar renomeamento para as colunas existentes que estão no mapeamento
        actual_rename_map = {old_name: new_name for old_name, new_name in colunas_map.items() if old_name in temp_df.columns}
        temp_df = temp_df.rename(columns=actual_rename_map)

        # Filtrar e reordenar o DataFrame para conter SOMENTE as 'final_desired_column_names'
        columns_present_and_desired = [col for col in final_desired_column_names if col in temp_df.columns]
        temp_df = temp_df[columns_present_and_desired]
            
        # Agora, a conversão de data usa o novo nome da coluna 'data_jogo'
        if 'data_jogo' in temp_df.columns:
            try:
                temp_df['data_jogo'] = pd.to_datetime(temp_df['data_jogo'], errors='coerce').dt.date
                # st.success substituído por set_temp_message
                set_temp_message(f"Dados da tabela '{DB_TABLE_NAME}' carregados e atualizados no cache da sessão.", "success")
            except Exception as e:
                st.error(f"Erro na conversão da coluna 'data_jogo': {e}")
                st.text("Exemplo de valores na coluna 'data_jogo' que causaram o erro:")
                st.dataframe(temp_df['data_jogo'].value_counts().head())
                st.stop()
        else:
            st.warning("Coluna 'data_jogo' não encontrada após renomeamento e seleção. Conversão de data ignorada.")
            
        st.session_state[f"{PAGE_SESSION_STATE_PREFIX}data"] = temp_df
        st.session_state[f"{PAGE_SESSION_STATE_PREFIX}last_loaded"] = time.time()
        current_df_page_specific = temp_df
        
        # >> ALTERAÇÃO AQUI: Inicializa os filtros de data com min/max do DataFrame, se ainda não estiverem definidos
        if 'data_jogo' in temp_df.columns and not temp_df['data_jogo'].isnull().all():
            min_date_df = temp_df['data_jogo'].min()
            max_date_df = temp_df['data_jogo'].max()

            # Apenas define se eles ainda são None (primeiro carregamento ou cache limpo)
            if st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_start_date"] is None:
                st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_start_date"] = min_date_df
            if st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_end_date"] is None:
                st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_end_date"] = max_date_df
        
    else:
        st.error(f"Falha crítica ao carregar dados da tabela '{DB_TABLE_NAME}'. Por favor, verifique as mensagens de erro acima e as variáveis de ambiente.")
        current_df_page_specific = None
else:
    time_since_last_load = int(time.time() - st.session_state[f'{PAGE_SESSION_STATE_PREFIX}last_loaded'])
    st.info(f"Usando dados em cache da sessão para '{DB_TABLE_NAME}' (última carga há {time_since_last_load} segundos).")
    current_df_page_specific = st.session_state[f"{PAGE_SESSION_STATE_PREFIX}data"]

# --- Lógica para o botão Resetar Filtros ---
if current_df_page_specific is not None:
    # Definir valores padrão para os filtros baseados no DataFrame carregado
    # Estes são usados pelo reset_filters e como min/max_value nos date_inputs
    default_start_date = (
        current_df_page_specific['data_jogo'].min()
        if 'data_jogo' in current_df_page_specific.columns and not current_df_page_specific['data_jogo'].isnull().all()
        else datetime.date.today() # Fallback se não houver data_jogo válida
    )
    default_end_date = (
        current_df_page_specific['data_jogo'].max()
        if 'data_df_page_specific' in current_df_page_specific.columns and not current_df_page_specific['data_jogo'].isnull().all()
        else datetime.date.today() # Fallback se não houver data_jogo válida
    )
    
    def reset_filters():
        # >> ALTERAÇÃO AQUI: Garante que o reset use os valores min/max do DataFrame
        st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_start_date"] = default_start_date
        st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_end_date"] = default_end_date
        st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_home_teams"] = ["Todos"] # Resetar para o padrão
        st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_away_teams"] = ["Todos"] # Resetar para o padrão
        st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_liga"] = ["Todos"]       # Resetar para o padrão
        st.rerun() 

    # Botão de Resetar Filtros na barra lateral
    st.sidebar.button("Resetar Filtros ��", on_click=reset_filters)

    st.sidebar.subheader("Configurações de Filtro")

    filtered_df = current_df_page_specific.copy() 

    # --- Filtro de Data ---
    if 'data_jogo' in filtered_df.columns and not filtered_df['data_jogo'].isnull().all():
        min_available_date = filtered_df['data_jogo'].min()
        max_available_date = filtered_df['data_jogo'].max()

        col_date1, col_date2 = st.sidebar.columns(2)
        with col_date1:
            selected_start_date = st.sidebar.date_input(
                "Data Inicial",
                value=st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_start_date"] if st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_start_date"] is not None else default_start_date, # Usar valor do session_state, ou fallback para default_start_date
                min_value=min_available_date,
                max_value=max_available_date,
                key=f"{PAGE_SESSION_STATE_PREFIX}date_input_start"
            )
        with col_date2:
            selected_end_date = st.sidebar.date_input(
                "Data Final",
                value=st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_end_date"] if st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_end_date"] is not None else default_end_date, # Usar valor do session_state, ou fallback para default_end_date
                min_value=min_available_date,
                max_value=max_available_date,
                key=f"{PAGE_SESSION_STATE_PREFIX}date_input_end"
            )
        
        # Atualiza o session_state com os valores selecionados pelo usuário
        # Esta parte permanece inalterada, pois o date_input já retorna o valor
        st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_start_date"] = selected_start_date
        st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_end_date"] = selected_end_date

        if selected_start_date and selected_end_date:
            # Garante que as datas de filtragem sejam 'date' e não 'Timestamp'
            selected_start_date = pd.to_datetime(selected_start_date).date()
            selected_end_date = pd.to_datetime(selected_end_date).date()
            
            filtered_df = filtered_df[
                (filtered_df['data_jogo'] >= selected_start_date) &
                (filtered_df['data_jogo'] <= selected_end_date)
            ]
    else:
        st.sidebar.warning("Coluna 'data_jogo' não encontrada ou não contém datas válidas para filtrar.")


    # --- Filtro de Ligas (liga) ---
    if 'liga' in filtered_df.columns:
        all_liga_names = sorted(current_df_page_specific['liga'].dropna().unique().tolist())
        liga_options = ["Todos"] + all_liga_names
        selected_liga_names_multiselect = st.sidebar.multiselect(
            "Nome da Liga",
            options=liga_options,
            default=st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_liga"],
            key=f"{PAGE_SESSION_STATE_PREFIX}multiselect_liga"
        )
        st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_liga"] = selected_liga_names_multiselect
        
        if "Todos" not in st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_liga"] and st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_liga"]:
            filtered_df = filtered_df[filtered_df['liga'].isin(st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_liga"])]
        elif not st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_liga"]:
            filtered_df = filtered_df[filtered_df['liga'].isin([])]
    else:
        st.sidebar.warning("Coluna 'liga' não encontrada para filtrar.")


    # --- Filtro de Times (home) ---
    if 'home' in filtered_df.columns:
        all_home_teams = sorted(current_df_page_specific['home'].dropna().unique().tolist())
        home_teams_options = ["Todos"] + all_home_teams
        selected_home_teams_multiselect = st.sidebar.multiselect(
            "Time da Casa",
            options=home_teams_options,
            default=st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_home_teams"],
            key=f"{PAGE_SESSION_STATE_PREFIX}multiselect_home"
        )
        st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_home_teams"] = selected_home_teams_multiselect
        
        if "Todos" not in st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_home_teams"] and st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_home_teams"]:
            filtered_df = filtered_df[filtered_df['home'].isin(st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_home_teams"])]
        elif not st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_home_teams"]:
            filtered_df = filtered_df[filtered_df['home'].isin([])]
    else:
        st.sidebar.warning("Coluna 'home' não encontrada para filtrar.")


    # --- Filtro de Times (away) ---
    if 'away' in filtered_df.columns:
        all_away_teams = sorted(current_df_page_specific['away'].dropna().unique().tolist())
        away_teams_options = ["Todos"] + all_away_teams
        selected_away_teams_multiselect = st.sidebar.multiselect(
            "Time Visitante",
            options=away_teams_options,
            default=st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_away_teams"],
            key=f"{PAGE_SESSION_STATE_PREFIX}multiselect_away"
        )
        st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_away_teams"] = selected_away_teams_multiselect
        
        if "Todos" not in st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_away_teams"] and st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_away_teams"]:
            filtered_df = filtered_df[filtered_df['away'].isin(st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_away_teams"])]
        elif not st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_away_teams"]:
            filtered_df = filtered_df[filtered_df['away'].isin([])]
    else:
        st.sidebar.warning("Coluna 'away' não encontrada para filtrar.")

    st.subheader(f"Dados Filtrados da Tabela '{DB_TABLE_NAME}':")
    if not filtered_df.empty:
        st.dataframe(filtered_df, use_container_width=True)
        st.write(f"Total de registros filtrados: **{len(filtered_df)}**")
    else:
        st.info("Nenhum dado corresponde aos filtros selecionados.")
else:
    st.warning(f"Nenhum dado da tabela '{DB_TABLE_NAME}' disponível para exibição. Verifique as mensagens de erro e carregamento acima.")


# --- Seção do Contador Decrescente (no rodapé da página principal) ---
st.markdown("---")
st.subheader("📊 Status da Sessão de Dados para esta Página")

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
        st.warning(f"O cache dos dados da tabela '{DB_TABLE_NAME}' expirou. Os dados serão atualizados na próxima interação ou recarregamento da página.")
else:
    st.info(f"O contador do cache para '{DB_TABLE_NAME}' será iniciado após o primeiro carregamento bem-sucedido dos dados.")

if st.button(f"Forçar Recarregamento dos Dados da Tabela '{DB_TABLE_NAME}' (Limpar Cache) 🔄"):
    st.info(f"Forçando a limpeza do cache de dados para '{DB_TABLE_NAME}' e recarregamento...")
    
    if f"{PAGE_SESSION_STATE_PREFIX}data" in st.session_state:
        del st.session_state[f"{PAGE_SESSION_STATE_PREFIX}data"]
    if f"{PAGE_SESSION_STATE_PREFIX}last_loaded" in st.session_state:
        del st.session_state[f"{PAGE_SESSION_STATE_PREFIX}last_loaded"]
    
    # >> ALTERAÇÃO AQUI: Ao limpar o cache, também limpe os estados das datas para que sejam reinicializados com min/max
    st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_start_date"] = None
    st.session_state[f"{PAGE_SESSION_STATE_PREFIX}current_end_date"] = None
        
    if 'cert_temp_dir' in st.session_state and st.session_state.cert_temp_dir and os.path.exists(st.session_state.cert_temp_dir):
        try:
            shutil.rmtree(st.session_state.cert_temp_dir)
            st.info(f"Diretório temporário do certificado '{st.session_state.cert_temp_dir}' limpo.")
        except Exception as e:
            st.warning(f"Não foi possível limpar o diretório temporário do certificado: {e}")
        st.session_state.cert_path = None
        st.session_state.cert_temp_dir = None
        
    st.rerun()
