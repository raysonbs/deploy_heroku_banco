import streamlit as st
import pandas as pd
import os
import tempfile
import requests
from sqlalchemy import create_engine
import time


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
    
    df_jogos_selecionados = pd.read_sql_table('temporadas_jogos_filtrados_2026', con=engine)
    # df_times_anos = pd.read_sql_table('t_times_anos', con=engine)

    return df_jogos_selecionados

# Inicializar a sessão para armazenamento de dados
if "last_loaded" not in st.session_state:
    st.session_state["last_loaded"] = 0  # Inicializa com 0 ou outro valor conveniente

# Checar se os DataFrames estão na sessão e se precisam ser atualizados
if "data_jogos_selecionados" not in st.session_state or time.time() - st.session_state["last_loaded"] > 600:
    df_jogos_selecionados = load_data()
    st.session_state["data_jogos_selecionados"] = df_jogos_selecionados
    # st.session_state["data_times_anos"] = df_times_anos
    st.session_state["last_loaded"] = time.time()

else: 
    st.error("Os dados das ligas não foram carregados.")


df_jogos_selecionados['liga_nome','data_horario','odds_ft_over05','home_name','away_name',
                      ]

# st.dataframe(df_filtrado_anos,
#     column_config={ 
#     "image_league": st.column_config.ImageColumn('Escudo'),
#     })

