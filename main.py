import streamlit as st
import pandas as pd
import os
import tempfile
import requests



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
