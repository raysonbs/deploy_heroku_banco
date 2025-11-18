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

# --- Configurações Específicas das Páginas ---
# Para 'ligas_ativas_total'
DB_TABLE_NAME_ATIVAS = 'ligas_ativas_total'
PAGE_SESSION_STATE_PREFIX_ATIVAS = f"{DB_TABLE_NAME_ATIVAS}_"

# Para 'ligas_inativas' (NOVO)
DB_TABLE_NAME_INATIVAS = 'ligas_inativas'
PAGE_SESSION_STATE_PREFIX_INATIVAS = f"{DB_TABLE_NAME_INATIVAS}_"

# --- Lista para coletar mensagens da aplicação ---
if 'app_messages' not in st.session_state:
    st.session_state['app_messages'] = []

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
        
        add_app_message("info", "Baixando certificado SSL...")
        url = os.getenv('url') # Variável de ambiente para a URL do certificado

        if not url:
            add_app_message("error", "A variável de ambiente 'url' não está definida. Exemplo: url='https://seusite.com/cert.crt'")
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
            add_app_message("success", "Certificado baixado e armazenado com sucesso!")
            return cert_full_path

        except requests.exceptions.RequestException as e:
            add_app_message("error", f"Erro ao baixar o certificado: {e}. Verifique a URL e sua conexão.")
            return None
        except Exception as e:
            add_app_message("error", f"Erro inesperado no download do certificado: {e}")
            return None
    else:
        return st.session_state.cert_path

# --- Função de Carregamento de Dados do Banco (AGORA GENÉRICA) ---
@st.cache_resource # Pode ser útil para não reconectar a cada rerun, mas a engine é criada dentro da função
def get_db_engine(cert_path):
    username = os.getenv('username')
    password = os.getenv('password')
    host = os.getenv('host')
    port = os.getenv('port')
    database = os.getenv('database')

    if not all([username, password, host, port, database]):
        raise ValueError("Variáveis de ambiente para conexão com o banco de dados incompletas (username, password, host, port, database).")
    
    try:
        port = int(port)
    except (ValueError, TypeError):
        raise ValueError(f"A porta do banco de dados '{port}' não é um número válido.")

    ssl_args = {'ssl': {'ca': cert_path}}
    return create_engine(f'mysql+pymysql://{username}:{password}@{host}:{port}/{database}', connect_args=ssl_args)

def load_data(table_name, page_session_state_prefix):
    """
    Carrega os dados do banco de dados MySQL usando o certificado SSL,
    da tabela especificada.
    Retorna um DataFrame pandas ou None em caso de erro.
    """
    cert_path_for_db = download_and_store_certificate()
    if cert_path_for_db is None:
        add_app_message("error", f"Não foi possível obter o certificado SSL necessário para a conexão com o banco de dados para a tabela '{table_name}'.")
        return None

    try:
        engine = get_db_engine(cert_path_for_db)
        with engine.connect() as connection:
            df = pd.read_sql_table(table_name, con=connection)
        
        add_app_message("success", f"Dados carregados da tabela '{table_name}' com sucesso!")
        return df
    
    except Exception as e:
        add_app_message("error", f"Erro ao conectar ou carregar dados do banco de dados da tabela '{table_name}': {e}")
        return None

# --- Função para carregar e cachear dados de uma tabela específica ---
def get_cached_dataframe(table_name, session_state_prefix):
    current_df = None
    cache_expired = (time.time() - st.session_state.get(f"{session_state_prefix}last_loaded", 0)) > CACHE_DURATION_SECONDS

    if st.session_state.get(f"{session_state_prefix}data") is None or cache_expired:
        if st.session_state.get(f"{session_state_prefix}data") is None:
            add_app_message("info", f"Primeiro carregamento dos dados da sessão para '{table_name}' ou dados não encontrados no cache.")
        elif cache_expired:
            time_since_last_load = int(time.time() - st.session_state.get(f"{session_state_prefix}last_loaded", 0))
            add_app_message("warning", f"Cache de dados para '{table_name}' expirado (última carga há {time_since_last_load} segundos). Recarregando dados...")
        
        temp_df = load_data(table_name, session_state_prefix) 
        
        if temp_df is not None:
            st.session_state[f"{session_state_prefix}data"] = temp_df
            st.session_state[f"{session_state_prefix}last_loaded"] = time.time()
            current_df = temp_df
            add_app_message("success", f"Dados da tabela '{table_name}' carregados e atualizados no cache da sessão.")
        else:
            add_app_message("error", f"Falha crítica ao carregar dados da tabela '{table_name}'. Por favor, verifique as mensagens de erro acima e as variáveis de ambiente.")
            current_df = None
    else:
        time_since_last_load = int(time.time() - st.session_state[f'{session_state_prefix}last_loaded'])
        add_app_message("info", f"Usando dados em cache da sessão para '{table_name}' (última carga há {time_since_last_load} segundos).")
        current_df = st.session_state[f"{session_state_prefix}data"]
    
    return current_df

# --- Configuração da Página Streamlit ---
st.set_page_config(layout="wide")
st.title(f"Diagnóstico de Jogos: Ligas Ativas e Inativas 📊")
st.write(f"Dados das tabelas `{DB_TABLE_NAME_ATIVAS}` e `{DB_TABLE_NAME_INATIVAS}` filtrados com cache de sessão por **{API_REFRESH_INTERVAL_MINUTES} minutos** para otimização.")


# --- CSS Personalizado para os Cartões (Sem Alterações, exceto na lista de ligas) ---
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
    .league-list { /* Estilo para a lista de ligas */
        text-align: left; /* Alinha a lista à esquerda dentro do card */
        list-style-position: inside; /* Garante que o número esteja dentro do padding */
        padding-left: 0; /* Remove o padding padrão da UL/OL */
        margin-top: 10px;
        font-size: 0.9em;
        /* A cor padrão da lista (se não for sobrescrita nos LI) */
        color: #666666; 
    }
    .league-list li {
        margin-bottom: 5px;
        list-style-type: decimal; /* Garante numeração */
        color: #333333; /* Cor mais escura para melhor legibilidade na lista */
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

# --- Carregamento e cache dos DataFrames ---
current_df_ativas = get_cached_dataframe(DB_TABLE_NAME_ATIVAS, PAGE_SESSION_STATE_PREFIX_ATIVAS)
current_df_inativas = get_cached_dataframe(DB_TABLE_NAME_INATIVAS, PAGE_SESSION_STATE_PREFIX_INATIVAS)

# --- Exibição dos Dados no Streamlit ---
if current_df_ativas is not None:
    st.subheader(f"Dados de '{DB_TABLE_NAME_ATIVAS}' Carregados:")
    st.dataframe(current_df_ativas, use_container_width=True)
else:
    add_app_message("warning", f"Nenhum dado da tabela '{DB_TABLE_NAME_ATIVAS}' disponível para exibição.")

if current_df_inativas is not None:
    st.subheader(f"Dados de '{DB_TABLE_NAME_INATIVAS}' Carregados:")
    st.dataframe(current_df_inativas, use_container_width=True)
else:
    add_app_message("warning", f"Nenhum dado da tabela '{DB_TABLE_NAME_INATIVAS}' disponível para exibição.")

st.markdown("---") # Separador visual simples

# --- Seção de Métricas em Cartão ---
st.subheader("📊 Resumo das Métricas")

# Adiciona uma quarta coluna para as ligas inativas
col1, col2, col3, col4 = st.columns(4) 

# Cartões para Ligas Ativas (Temporada 2025 e 2026)
if current_df_ativas is not None:
    if 'Temporada' in current_df_ativas.columns and 'name' in current_df_ativas.columns: 
        df_ligas_2025 = current_df_ativas[current_df_ativas['Temporada'] == "2025"]
        df_ligas_2026 = current_df_ativas[current_df_ativas['Temporada'] == "2026"]
        
        count_2025 = df_ligas_2025.shape[0]
        count_2026 = df_ligas_2026.shape[0]

        with col1:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric(label="Ligas Ativas Temporada 2025", value=count_2025)
            if not df_ligas_2025.empty:
                league_names_2025 = df_ligas_2025['name'].to_list()
                st.markdown("<h5 style='text-align:center; color:#555;'>Nomes das Ligas:</h5>", unsafe_allow_html=True)
                st.markdown(f"<ol class='league-list'>" + "".join([f"<li>{name}</li>" for name in league_names_2025]) + "</ol>", unsafe_allow_html=True)
            else:
                st.markdown('<p class="card-title-text">Nenhuma liga encontrada para 2025.</p>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with col2:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric(label="Ligas Ativas Temporada 2026", value=count_2026)
            if not df_ligas_2026.empty:
                league_names_2026 = df_ligas_2026['name'].to_list()
                st.markdown("<h5 style='text-align:center; color:#555;'>Nomes das Ligas:</h5>", unsafe_allow_html=True)
                st.markdown(f"<ol class='league-list'>" + "".join([f"<li>{name}</li>" for name in league_names_2026]) + "</ol>", unsafe_allow_html=True)
            else:
                st.markdown('<p class="card-title-text">Nenhuma liga encontrada para 2026.</p>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
    else:
        # Fallback se as colunas 'Temporada' ou 'name' não existirem para ligas ativas
        with col1:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric(label="Ligas Ativas 2025", value="N/A")
            st.caption("Colunas 'Temporada' ou 'name' não encontradas em ligas ativas.")
            st.markdown('</div>', unsafe_allow_html=True)
        with col2:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric(label="Ligas Ativas 2026", value="N/A")
            st.caption("Colunas 'Temporada' ou 'name' não encontradas em ligas ativas.")
            st.markdown('</div>', unsafe_allow_html=True)
else:
    # Fallback se o dataframe de ligas ativas não estiver disponível
    with col1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric(label="Ligas Ativas 2025", value="N/A")
        st.caption("Dados de ligas ativas não disponíveis.")
        st.markdown('</div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric(label="Ligas Ativas 2026", value="N/A")
        st.caption("Dados de ligas ativas não disponíveis.")
        st.markdown('</div>', unsafe_allow_html=True)

# NOVO CARTÃO: Ligas Inativas
with col3:
    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
    if current_df_inativas is not None:
        if 'name' in current_df_inativas.columns:
            count_inativas = current_df_inativas.shape[0]
            st.metric(label="Total de Ligas Inativas", value=count_inativas)
            if not current_df_inativas.empty:
                league_names_inativas = current_df_inativas['name'].to_list()
                st.markdown("<h5 style='text-align:center; color:#555;'>Nomes das Ligas:</h5>", unsafe_allow_html=True)
                st.markdown(f"<ol class='league-list'>" + "".join([f"<li>{name}</li>" for name in league_names_inativas]) + "</ol>", unsafe_allow_html=True)
            else:
                st.markdown('<p class="card-title-text">Nenhuma liga inativa encontrada.</p>', unsafe_allow_html=True)
        else:
            st.metric(label="Total de Ligas Inativas", value="N/A")
            st.caption("Coluna 'name' não encontrada em ligas inativas.")
    else:
        st.metric(label="Total de Ligas Inativas", value="N/A")
        st.caption("Dados de ligas inativas não disponíveis.")
    st.markdown('</div>', unsafe_allow_html=True)


# Cartão para Total de Ligas Ativas (agora em col4)
with col4:
    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
    if current_df_ativas is not None:
        st.metric(label="Total de ligas ativas", value=current_df_ativas.shape[0])
    else:
        st.metric(label="Total de ligas ativas", value="N/A")
        st.caption("Dados não disponíveis.")
    st.markdown('</div>', unsafe_allow_html=True)
            
st.markdown("---") # Separador visual simples

# --- Seção do Contador Decrescente ---
st.subheader("⏳ Status da Sessão de Dados para esta Página")

# Contador para ligas ativas
if st.session_state.get(f"{PAGE_SESSION_STATE_PREFIX_ATIVAS}last_loaded", 0) > 0 and current_df_ativas is not None:
    last_loaded_timestamp_ativas = st.session_state[f"{PAGE_SESSION_STATE_PREFIX_ATIVAS}last_loaded"]
    expiration_timestamp_ativas = last_loaded_timestamp_ativas + CACHE_DURATION_SECONDS
    current_time = time.time()
    remaining_seconds_ativas = expiration_timestamp_ativas - current_time

    if remaining_seconds_ativas > 0:
        minutes = int(remaining_seconds_ativas // 60)
        seconds = int(remaining_seconds_ativas % 60)
        st.metric(label=f"Próxima atualização automática de '{DB_TABLE_NAME_ATIVAS}' em aproximadamente", value=f"{minutes:02d}m {seconds:02}s")
        st.caption(
            f"Os dados da tabela '{DB_TABLE_NAME_ATIVAS}' foram carregados pela última vez em: "
            f"**{datetime.datetime.fromtimestamp(last_loaded_timestamp_ativas).strftime('%d/%m/%Y %H:%M:%S')}**."
        )
    else:
        add_app_message("warning", f"O cache dos dados da tabela '{DB_TABLE_NAME_ATIVAS}' expirou. Os dados serão atualizados na próxima interação ou recarregamento da página.")
else:
    add_app_message("info", f"O contador do cache para '{DB_TABLE_NAME_ATIVAS}' será iniciado após o primeiro carregamento bem-sucedido dos dados.")

# Contador para ligas inativas (NOVO)
if st.session_state.get(f"{PAGE_SESSION_STATE_PREFIX_INATIVAS}last_loaded", 0) > 0 and current_df_inativas is not None:
    last_loaded_timestamp_inativas = st.session_state[f"{PAGE_SESSION_STATE_PREFIX_INATIVAS}last_loaded"]
    expiration_timestamp_inativas = last_loaded_timestamp_inativas + CACHE_DURATION_SECONDS
    current_time = time.time()
    remaining_seconds_inativas = expiration_timestamp_inativas - current_time

    if remaining_seconds_inativas > 0:
        minutes = int(remaining_seconds_inativas // 60)
        seconds = int(remaining_seconds_inativas % 60)
        st.metric(label=f"Próxima atualização automática de '{DB_TABLE_NAME_INATIVAS}' em aproximadamente", value=f"{minutes:02d}m {seconds:02}s")
        st.caption(
            f"Os dados da tabela '{DB_TABLE_NAME_INATIVAS}' foram carregados pela última vez em: "
            f"**{datetime.datetime.fromtimestamp(last_loaded_timestamp_inativas).strftime('%d/%m/%Y %H:%M:%S')}**."
        )
    else:
        add_app_message("warning", f"O cache dos dados da tabela '{DB_TABLE_NAME_INATIVAS}' expirou. Os dados serão atualizados na próxima interação ou recarregamento da página.")
else:
    add_app_message("info", f"O contador do cache para '{DB_TABLE_NAME_INATIVAS}' será iniciado após o primeiro carregamento bem-sucedido dos dados.")


# Botão para forçar recarregamento (agora limpa o cache de AMBAS as tabelas)
if st.button(f"Forçar Recarregamento de TODAS as tabelas (Limpar Cache) 🔄"):
    add_app_message("info", f"Forçando a limpeza do cache de dados para TODAS as tabelas e recarregamento...")
    
    # Limpa cache de ligas ativas
    if f"{PAGE_SESSION_STATE_PREFIX_ATIVAS}data" in st.session_state:
        del st.session_state[f"{PAGE_SESSION_STATE_PREFIX_ATIVAS}data"]
    if f"{PAGE_SESSION_STATE_PREFIX_ATIVAS}last_loaded" in st.session_state:
        del st.session_state[f"{PAGE_SESSION_STATE_PREFIX_ATIVAS}last_loaded"]
    
    # Limpa cache de ligas inativas (NOVO)
    if f"{PAGE_SESSION_STATE_PREFIX_INATIVAS}data" in st.session_state:
        del st.session_state[f"{PAGE_SESSION_STATE_PREFIX_INATIVAS}data"]
    if f"{PAGE_SESSION_STATE_PREFIX_INATIVAS}last_loaded" in st.session_state:
        del st.session_state[f"{PAGE_SESSION_STATE_PREFIX_INATIVAS}last_loaded"]
        
    if 'cert_temp_dir' in st.session_state and st.session_state.cert_temp_dir and os.path.exists(st.session_state.cert_temp_dir):
        try:
            shutil.rmtree(st.session_state.cert_temp_dir)
            add_app_message("info", f"Diretório temporário do certificado '{st.session_state.cert_temp_dir}' limpo.")
        except Exception as e:
            add_app_message("warning", f"Não foi possível limpar o diretório temporário do certificado: {e}")
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

# Limpa as mensagens após a exibição para que não se acumulem em reruns.
st.session_state['app_messages'] = []