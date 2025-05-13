import streamlit as st
import pandas as pd
import os
import tempfile
import requests
from sqlalchemy import create_engine
import time



df = pd.read_csv('CLEAN_FIFA23_official_data.csv')
# df

nomes = df['Name'].unique().tolist()
nomes.insert(0, "Todos")  # Adiciona a opção "Todos" no início da lista


Nome = st.sidebar.selectbox("Nome",nomes)

if Nome == "Todos":
    df = df
    df

else:
    df = df[df['Name'] == Nome]
    df


st.write('Teste')




username = os.getenv('username')
# password = os.getenv('password')
# host = os.getenv('host')
# port = os.getenv('port')
# database = os.getenv('database')
url = os.getenv('url')

st.write(username)
st.write(url)


def download_certificate():
    try:
        # Obtém a URL do certificado a partir da variável de ambiente
        url = os.getenv('URL_DO_CERTIFICADO')

        if not url:
            print("A variável de ambiente 'URL_DO_CERTIFICADO' não está definida.")
            return None

        response = requests.get(url)
        response.raise_for_status()

        # Cria um arquivo temporário
        temp_dir = tempfile.mkdtemp()
        cert_path = os.path.join(temp_dir, 'certificado.crt')

        # Salva o certificado no arquivo temporário
        with open(cert_path, 'wb') as cert_file:
            cert_file.write(response.content)

        print("Certificado baixado com sucesso!")
        return cert_path

    except requests.exceptions.RequestException as e:
        print(f"Erro ao baixar o certificado: {e}")
        return None

# Use a função para baixar o certificado
cert_path = download_certificate()



def load_data():
    # Informações de conexão e caminho do certificado
    username = os.getenv('username')
    password = os.getenv('password')
    host = os.getenv('host')
    port = os.getenv('port')
    database = os.getenv('database')

    # Configurações SSL
    ssl_args = {
        'ssl': {
            'ca': cert_path  # Certifique-se de que o caminho é válido
        }
    }

    # Criar a engine de conexão com o banco de dados
    engine = create_engine(
        f'mysql+pymysql://{username}:{password}@{host}:{port}/{database}',
        connect_args=ssl_args
    )
    
    df_liga_anos = pd.read_sql_table('t_ligas_anos', con=engine)
    df_times_anos = pd.read_sql_table('t_times_anos', con=engine)

    return df_liga_anos, df_times_anos

# Inicializar a sessão para armazenamento de dados
if "last_loaded" not in st.session_state:
    st.session_state["last_loaded"] = 0  # Inicializa com 0 ou outro valor conveniente

# Checar se os DataFrames estão na sessão e se precisam ser atualizados
if "data_ligas_anos" not in st.session_state or time.time() - st.session_state["last_loaded"] > 600:
    df_liga_anos, df_times_anos = load_data()
    st.session_state["data_ligas_anos"] = df_liga_anos
    st.session_state["data_times_anos"] = df_times_anos
    st.session_state["last_loaded"] = time.time()

# Acesso e exibição do DataFrame df_ligas_anos
if "data_ligas_anos" in st.session_state:
    df_ligas_anos = st.session_state["data_ligas_anos"]
    # st.write("Dados das Ligas por Ano:")
    # st.write(df_ligas_anos)
else: 
    st.error("Os dados das ligas não foram carregados.")

# Acesso e exibição do DataFrame df_times_anos
if "data_times_anos" in st.session_state:
    df_times_anos = st.session_state["data_times_anos"]
    # st.write("Dados dos Times por Ano:")
    # st.write(df_times_anos)
else: 
    st.error("Os dados dos times não foram carregados.")
    

anos = df_ligas_anos['Ano'].unique().tolist()
anos.insert(0, "Todos")  # Adiciona a opção "Todos" no início da lista


temporada = st.sidebar.selectbox("Temporada",anos)


# Filtrar o DataFrame com base na seleção
if temporada == "Todos":
    df_filtrado_anos = df_ligas_anos
    ligas = df_ligas_anos["Campeonato"].unique().tolist()
    ligas.insert(0, "Todos")
    ligas = st.sidebar.selectbox("Liga_Seleção", ligas)
    if ligas == "Todos":
        # df_filtrado_anos
        pass
    else:
        df_filtrado_anos = df_ligas_anos[df_ligas_anos['Campeonato'] == ligas]
    #     df_filtrado_anos = df_ligas_anos[df_ligas_anos['temporada'] == temporada and df_liga_anos[df_liga_anos['liga'] == ligas]]
else:
    df_filtrado_anos = df_ligas_anos[df_ligas_anos['Ano'] == temporada]

    ligas = df_ligas_anos["Campeonato"].unique()
    # ligas.insert(0, "Todos")
    ligas = st.sidebar.selectbox("Liga_Seleção", ligas)
    df_filtrado_anos = df_filtrado_anos[df_filtrado_anos['Campeonato'] == ligas]

st.dataframe(df_filtrado_anos,
    column_config={ 
    "image_league": st.column_config.ImageColumn('Escudo'),
    })


st.write("teste")